#!/usr/bin/env bash
# Phase 1 follow-up: Gemma-only llama-server rerun, to test the context-checkpoint penalty seen in p1-20261012-180308.
# Same server flags as phase1.sh (-ngl 99 -fa off -c 32768 -np 1) plus one variant flag each:
#   ckpt-off  --ctx-checkpoints 0
#   swa-full  --swa-full
#   default   (no extra flag; same-session control)
# Each variant: 30 s loaded idle + VRAM, then serve_bench.py (512/4K/16K prompts x 3 reps). Output: raw/p1-swa-<ts>/<variant>/
# Usage: B65_VK_INDEX=<idx> ./gemma_server_rerun.sh     Env: LLAMA_SERVER, CTX (32768), PORT (8099), VARIANTS
set -euo pipefail
cd "$(dirname "$0")"
LS="${LLAMA_SERVER:-../vendor/llama.cpp/build/bin/llama-server}"; LB="${LLAMA_BENCH:-../vendor/llama.cpp/build/bin/llama-bench}"
[ -n "${B65_VK_INDEX:-}" ] || { echo "Set B65_VK_INDEX"; exit 1; }
export GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX"
CTX="${CTX:-32768}"; PORT="${PORT:-8099}"; VARIANTS="${VARIANTS:-ckpt-off swa-full default}"; NAME=gemma-4-31b-qat
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }
DEVS=$("$LB" --list-devices 2>&1)
echo "$DEVS" | grep -q "BMG" && ! echo "$DEVS" | grep -q "NVIDIA" || { echo "!! Visible devices are not just the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1)
[ "${FREE:-0}" -ge 28000 ] || { echo "!! Only ${FREE:-?} MiB free on the B65. Unload LM Studio models (lms unload --all)."; exit 2; }
GLOB=$(grep "^$NAME|" models.conf | cut -d'|' -f3)
FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
[ -n "$FILE" ] || { echo "!! no file for $NAME"; exit 1; }
RUN_ID="p1-swa-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo "$$" > "$OUT/pid"
ENERGY=""
for h in /sys/class/hwmon/hwmon*; do
  [ "$(cat "$h/name" 2>/dev/null)" = "xe" ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done
done
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null)"; echo "omarchy=$(omarchy-version 2>/dev/null || echo unknown)"
  echo "llama_server=$("$LS" --version 2>&1 | grep -m1 version)"; echo "vk_visible=$GGML_VK_VISIBLE_DEVICES"
  echo "model=$NAME"; echo "fa=0"; echo "ctx=$CTX"; echo "variants=$VARIANTS"; echo "vram_free_mib=$FREE"
  echo "energy_file=${ENERGY:-none}"; echo "baseline_run=p1-20261012-180308"; } > "$OUT/env.txt"
sha256sum "$FILE" > "$OUT/models.sha256"
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }
proc_vram_mib() {
  local pid=$1
  for f in /proc/"$pid"/fdinfo/*; do grep -q 'drm-driver:.*xe' "$f" 2>/dev/null && cat "$f"; echo "--"; done 2>/dev/null |
    awk '/^drm-client-id:/ {id=$2} /^drm-resident-vram0:/ {v=$2; u=$3; k=(u=="MiB")?v*1024:(u=="GiB")?v*1048576:(u=="KiB")?v:v/1024; if (!(id in seen)) {seen[id]=1; tot+=k}}
         END {printf "%d", tot/1024}'
}
flag_of() { case "$1" in ckpt-off) echo "--ctx-checkpoints 0";; swa-full) echo "--swa-full";; default) echo "";; *) echo "?";; esac; }

echo "variant,flags,status,loaded_idle_w,vram_used_mib" > "$OUT/variants.csv"
for V in $VARIANTS; do
  F=$(flag_of "$V"); D="$OUT/$V"; mkdir -p "$D"; echo ">> server $NAME $V ${F:-(defaults)}"
  TP=""; [ -n "$ENERGY" ] && { trace "$D/power.csv" & TP=$!; }
  # shellcheck disable=SC2086
  "$LS" -m "$FILE" -ngl 99 -fa off -c "$CTX" --port "$PORT" --host 127.0.0.1 -np 1 --no-webui $F > "$D/server.log" 2>&1 &
  SPID=$!
  ok=0; for _ in $(seq 1 180); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { ok=1; break; }
    kill -0 $SPID 2>/dev/null || break; sleep 1; done
  if [ $ok = 0 ]; then
    st=fail; grep -qiE "out of memory|ErrorOutOfDeviceMemory|failed to allocate" "$D/server.log" && st=oom
    echo "!! server did not come up for $V ($st), see $D/server.log"; echo "$V,$F,$st,," >> "$OUT/variants.csv"
    kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true
    [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }; continue
  fi
  sleep 5
  e0=$(read_e); t0=$EPOCHREALTIME; sleep 30; e1=$(read_e); t1=$EPOCHREALTIME
  IW=$([ -n "$e0" ] && calc "($e1-$e0)/1000000/($t1-$t0)"); VR=$(proc_vram_mib $SPID)
  echo ">> requests $NAME $V"
  python3 serve_bench.py --port "$PORT" --model "$NAME" --out "$D" --energy "${ENERGY:-}" && st=ok || { st=fail; echo "!! serve_bench failed for $V"; }
  echo "$V,$F,$st,$IW,$VR" >> "$OUT/variants.csv"
  kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true
  [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }
done
python3 summarize_rerun.py "$OUT"
date -Iseconds > "$OUT/done"
echo "Done: $OUT"
