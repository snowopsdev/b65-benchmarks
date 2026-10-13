#!/usr/bin/env bash
# Phase 3: quality checks on SYCL, flash attention on, via llama-server (temp 0).
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./phase3.sh     DRY=1: first model, 2 items per section
set -euo pipefail
cd "$(dirname "$0")"
LS="${SYCL_BIN:?set SYCL_BIN}/llama-server"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
CTX="${CTX:-32768}"; PORT="${PORT:-8099}"; DRY="${DRY:-0}"
RUN_ID="p3-$( [ "$DRY" = 1 ] && echo dry- )$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "backend=sycl"; echo "fa=on"
  echo "server=$("$LS" --version 2>&1 | grep -m1 version)"; echo "ctx=$CTX"; } > "$OUT/env.txt"
while IFS='|' read -r NAME QUANT GLOB; do
  [[ -z "$NAME" || "$NAME" == \#* ]] && continue
  FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$FILE" ] || { echo "!! $NAME not found"; continue; }
  EXTRA=""; case "$NAME" in gemma*) EXTRA="--ctx-checkpoints 0";; esac
  echo "== $NAME"
  "$LS" -m "$FILE" -ngl 99 -fa on --jinja $EXTRA -c "$CTX" --port "$PORT" --host 127.0.0.1 -np 1 --no-webui > "$OUT/$NAME.server.log" 2>&1 &
  SP=$!; ok=0; for _ in $(seq 1 240); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { ok=1; break; }; sleep 1; done
  [ $ok = 1 ] && { grep -qi intel "$OUT/$NAME.server.log" || echo "!! no Intel device line in server log"; 
    python3 quality.py --port "$PORT" --model "$NAME" --out "$OUT" $( [ "$DRY" = 1 ] && echo --dry ) 2>&1 | tee "$OUT/$NAME.quality.log" || echo "!! quality failed for $NAME"; } \
    || echo "!! server for $NAME did not come up"
  kill $SP 2>/dev/null; wait $SP 2>/dev/null || true; sleep 5
  [ "$DRY" = 1 ] && break
done < models.conf
python3 summarize3.py "$OUT"
echo "Done: $OUT"
