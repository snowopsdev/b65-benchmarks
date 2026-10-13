#!/usr/bin/env bash
# B65 Bench Phase 1 (Vulkan, flash attention OFF for everything).
#  A) decode cleanup: tg128, tg128@d4096 with -fa 0 (replaces Phase 0 fa=1 decode)
#  B) context table: decode at depth 8k/16k/32k (fits = ran without OOM)
#  C) llama-server: TTFT + decode for 512/4k/16k-token prompts, 3 reps, streamed
#  D) loaded-idle board power (server up, model in VRAM, no requests), 30 s
# Usage: B65_VK_INDEX=<idx> ./phase1.sh     DRY=1 for a quick check (one model, A only + 1 server request)
# Env: LLAMA_BENCH, LLAMA_SERVER, REPS (5), CTX (32768), PORT (8099)
set -euo pipefail
cd "$(dirname "$0")"
LB="${LLAMA_BENCH:-../vendor/llama.cpp/build/bin/llama-bench}"; LS="${LLAMA_SERVER:-../vendor/llama.cpp/build/bin/llama-server}"
for b in "$LB" "$LS"; do command -v "$b" >/dev/null || { echo "$b not found"; exit 1; }; done
[ -n "${B65_VK_INDEX:-}" ] || { echo "Set B65_VK_INDEX"; exit 1; }
export GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX"
REPS="${REPS:-5}"; CTX="${CTX:-32768}"; PORT="${PORT:-8099}"; DRY="${DRY:-0}"
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }   # local: no bc on this machine
# local: only the B65 visible, and its VRAM free (LM Studio models unloaded)
DEVS=$("$LB" --list-devices 2>&1)
echo "$DEVS" | grep -q "BMG" && ! echo "$DEVS" | grep -q "NVIDIA" || { echo "!! Visible devices are not just the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1)
[ "${FREE:-0}" -ge 28000 ] || { echo "!! Only ${FREE:-?} MiB free on the B65. Unload LM Studio models (lms unload --all)."; exit 2; }
RUN_ID="p1-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo "$$" > "$OUT/pid"

{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null)"; echo "omarchy=$(omarchy-version 2>/dev/null || echo unknown)"
  echo "llama_bench=$("$LB" --version 2>&1 | grep -m1 version)"; echo "llama_server=$("$LS" --version 2>&1 | grep -m1 version)"
  echo "vk_visible=$GGML_VK_VISIBLE_DEVICES"; echo "fa=0"; echo "reps=$REPS"; echo "ctx=$CTX"; echo "vram_free_mib=$FREE"; } > "$OUT/env.txt"

ENERGY=""
for h in /sys/class/hwmon/hwmon*; do   # local: pick the xe "card" channel by label
  [ "$(cat "$h/name" 2>/dev/null)" = "xe" ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done
done
echo "energy_file=${ENERGY:-none}" >> "$OUT/env.txt"
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
watts() { [ -n "$1" ] && calc "($2-$1)/1000000/($4-$3)" || echo ""; }
# local: 10 Hz energy trace + time-stamped --progress lines -> board W over the timed reps (same method as Phase 0/0.5)
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }
stamp() { while IFS= read -r l; do echo "$EPOCHREALTIME $l"; done; }
# local: VRAM held by a process, from the xe DRM fdinfo (resident vram0, summed over unique clients), in MiB
proc_vram_mib() {
  local pid=$1
  for f in /proc/"$pid"/fdinfo/*; do grep -q 'drm-driver:.*xe' "$f" 2>/dev/null && cat "$f"; echo "--"; done 2>/dev/null |
    awk '/^drm-client-id:/ {id=$2} /^drm-resident-vram0:/ {v=$2; u=$3; k=(u=="MiB")?v*1024:(u=="GiB")?v*1048576:(u=="KiB")?v:v/1024; if (!(id in seen)) {seen[id]=1; tot+=k}}
         END {printf "%d", tot/1024}'
}

BENCH=( "tg128|-p 0 -n 128" "tg128@d4096|-p 0 -n 128 -d 4096"
        "tg128@d8192|-p 0 -n 128 -d 8192" "tg128@d16384|-p 0 -n 128 -d 16384" "tg128@d32768|-p 0 -n 128 -d 32768" )
[ "$DRY" = 1 ] && BENCH=( "tg128|-p 0 -n 128" )

echo "section,test,model,status,energy_j,seconds,t_end" > "$OUT/energy.csv"
echo "model,loaded_idle_w,vram_used_mib" > "$OUT/idle_loaded.csv"
while IFS='|' read -r NAME QUANT GLOB; do
  [[ -z "$NAME" || "$NAME" == \#* ]] && continue
  FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$FILE" ] || { echo "!! no file for $NAME"; continue; }
  sha256sum "$FILE" >> "$OUT/models.sha256"

  # A + B: llama-bench decode, fa=0
  for T in "${BENCH[@]}"; do
    LABEL="${T%%|*}"; ARGS="${T#*|}"; echo ">> bench $NAME $LABEL"
    TP=""; [ -n "$ENERGY" ] && { trace "$OUT/$NAME.$LABEL.power.csv" & TP=$!; }
    e0=$(read_e); t0=$EPOCHREALTIME; st=ok
    # shellcheck disable=SC2086
    "$LB" -m "$FILE" -ngl 99 -fa 0 -r "$REPS" $ARGS -o jsonl --progress \
      > "$OUT/$NAME.$LABEL.jsonl" 2> >(stamp > "$OUT/$NAME.$LABEL.log") || st=fail
    e1=$(read_e); t1=$EPOCHREALTIME
    [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }
    wait   # trace is gone; this lets the stderr stamper flush
    grep -qiE "out of memory|ErrorOutOfDeviceMemory|failed to allocate" "$OUT/$NAME.$LABEL.log" && st=oom
    echo "bench,$LABEL,$NAME,$st,$( [ -n "$e0" ] && calc "($e1-$e0)/1000000"),$(calc "$t1-$t0"),$t1" >> "$OUT/energy.csv"
    [ $st != ok ] && echo "!! $NAME $LABEL: $st, see $OUT/$NAME.$LABEL.log"
    # local: device check on every successful test
    if [ $st = ok ] && ! grep -q '"gpu_info": *"[^"]*BMG' "$OUT/$NAME.$LABEL.jsonl"; then echo "!! not the B65, aborting"; exit 2; fi
  done

  # C + D: llama-server
  echo ">> server $NAME"
  "$LS" -m "$FILE" -ngl 99 -fa off -c "$CTX" --port "$PORT" --host 127.0.0.1 -np 1 --no-webui > "$OUT/$NAME.server.log" 2>&1 &
  SPID=$!
  ok=0; for _ in $(seq 1 180); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { ok=1; break; }; sleep 1; done
  if [ $ok = 0 ]; then echo "!! server did not come up for $NAME"; kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; continue; fi
  sleep 5
  e0=$(read_e); t0=$EPOCHREALTIME; sleep 30; e1=$(read_e); t1=$EPOCHREALTIME
  echo "$NAME,$(watts "$e0" "$e1" "$t0" "$t1"),$(proc_vram_mib $SPID)" >> "$OUT/idle_loaded.csv"   # local: VRAM from xe fdinfo
  python3 serve_bench.py --port "$PORT" --model "$NAME" --out "$OUT" --energy "${ENERGY:-}" $( [ "$DRY" = 1 ] && echo --dry ) || echo "!! serve_bench failed for $NAME"
  kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true
  [ "$DRY" = 1 ] && break
done < models.conf

python3 summarize1.py "$OUT"
date -Iseconds > "$OUT/done"
echo "Done: $OUT"
