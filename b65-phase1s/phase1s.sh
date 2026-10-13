#!/usr/bin/env bash
# B65 Bench Phase 1 (Vulkan, flash attention OFF for everything).
#  A) decode cleanup: tg128, tg128@d4096 with -fa 1 on SYCL
#  B) context table: decode at depth 8k/16k/32k (fits = ran without OOM)
#  C) llama-server: TTFT + decode for 512/4k/16k-token prompts, 3 reps, streamed
#  D) loaded-idle board power (server up, model in VRAM, no requests), 30 s
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./phase1s.sh  (GEMMA_CKPT=32 for the default-checkpoint control)     DRY=1 for a quick check (one model, A only + 1 server request)
# Env: LLAMA_BENCH, LLAMA_SERVER, REPS (5), CTX (32768), PORT (8099)
set -euo pipefail
cd "$(dirname "$0")"
LB="${SYCL_BIN:?set SYCL_BIN}/llama-bench"; LS="$SYCL_BIN/llama-server"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
for b in "$LB" "$LS"; do command -v "$b" >/dev/null || { echo "$b not found"; exit 1; }; done
REPS="${REPS:-5}"; CTX="${CTX:-32768}"; PORT="${PORT:-8099}"; DRY="${DRY:-0}"
RUN_ID="p1s-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"

{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null)"; echo "omarchy=$(omarchy-version 2>/dev/null || echo unknown)"
  echo "llama_bench=$("$LB" --version 2>&1 | grep -m1 version)"; echo "llama_server=$("$LS" --version 2>&1 | grep -m1 version)"
  echo "backend=sycl"; echo "sycl_bin=$SYCL_BIN"; echo "selector=$ONEAPI_DEVICE_SELECTOR"; echo "fa=1"; echo "reps=$REPS"; echo "ctx=$CTX"; } > "$OUT/env.txt"

ENERGY=""
for h in /sys/class/hwmon/hwmon*; do
  [ "$(cat "$h/name" 2>/dev/null)" = "xe" ] && for f in "$h"/energy*_input; do [ -r "$f" ] && { ENERGY="$f"; break 2; }; done
done
echo "energy_file=${ENERGY:-none}" >> "$OUT/env.txt"
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
watts() { [ -n "$1" ] && echo "($2-$1)/1000000/($4-$3)" | bc -l || echo ""; }

BENCH=( "tg128|-p 0 -n 128" "tg128@d4096|-p 0 -n 128 -d 4096"
        "tg128@d8192|-p 0 -n 128 -d 8192" "tg128@d16384|-p 0 -n 128 -d 16384" "tg128@d32768|-p 0 -n 128 -d 32768" )
[ "$DRY" = 1 ] && BENCH=( "tg128|-p 0 -n 128" )

echo "section,test,model,status,energy_j,seconds" > "$OUT/energy.csv"
echo "model,loaded_idle_w,vram_used_mib" > "$OUT/idle_loaded.csv"
first=1
while IFS='|' read -r NAME QUANT GLOB; do
  [[ -z "$NAME" || "$NAME" == \#* ]] && continue
  FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$FILE" ] || { echo "!! no file for $NAME"; continue; }
  sha256sum "$FILE" >> "$OUT/models.sha256"

  EXTRA_SRV=""; case "$NAME" in gemma*) EXTRA_SRV="--ctx-checkpoints ${GEMMA_CKPT:-0}";; esac
  # A + B: llama-bench decode, fa=1
  for T in "${BENCH[@]}"; do
    LABEL="${T%%|*}"; ARGS="${T#*|}"; echo ">> bench $NAME $LABEL"
    e0=$(read_e); t0=$(date +%s.%N); st=ok
    # shellcheck disable=SC2086
    "$LB" -m "$FILE" -ngl 99 -fa 1 -r "$REPS" $ARGS -o jsonl > "$OUT/$NAME.$LABEL.jsonl" 2> "$OUT/$NAME.$LABEL.log" || st=fail
    grep -qiE "out of memory|ErrorOutOfDeviceMemory|failed to allocate" "$OUT/$NAME.$LABEL.log" && st=oom
    e1=$(read_e); t1=$(date +%s.%N)
    echo "bench,$LABEL,$NAME,$st,$( [ -n "$e0" ] && echo "($e1-$e0)/1000000" | bc -l),$(echo "$t1-$t0" | bc -l)" >> "$OUT/energy.csv"
    if [ $first = 1 ]; then grep -qi intel "$OUT/$NAME.$LABEL.jsonl" "$OUT/$NAME.$LABEL.log" || { echo "!! not the B65"; exit 2; }; first=0; fi
  done

  # C + D: llama-server
  echo ">> server $NAME"
  "$LS" -m "$FILE" -ngl 99 -fa on $EXTRA_SRV -c "$CTX" --port "$PORT" --host 127.0.0.1 -np 1 --no-webui > "$OUT/$NAME.server.log" 2>&1 &
  SPID=$!
  ok=0; for _ in $(seq 1 180); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { ok=1; break; }; sleep 1; done
  if [ $ok = 0 ]; then echo "!! server did not come up for $NAME"; kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; continue; fi
  sleep 5
  e0=$(read_e); t0=$(date +%s.%N); sleep 30; e1=$(read_e); t1=$(date +%s.%N)
  echo "$NAME,$(watts "$e0" "$e1" "$t0" "$t1"),$(cat /sys/class/drm/card*/device/mem_info_vram_used 2>/dev/null | head -n1 | awk '{print int($1/1048576)}')" >> "$OUT/idle_loaded.csv"
  python3 serve_bench.py --port "$PORT" --model "$NAME" --out "$OUT" --energy "${ENERGY:-}" $( [ "$DRY" = 1 ] && echo --dry ) || echo "!! serve_bench failed for $NAME"
  kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true
  [ "$DRY" = 1 ] && break
done < models.conf

python3 summarize1.py "$OUT"
echo "Done: $OUT"
