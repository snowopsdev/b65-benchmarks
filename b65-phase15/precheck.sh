#!/usr/bin/env bash
# Phase 1.5 pre-check: the registry's six lab gates (load chat reasoning tools context speed) against our native
# SYCL llama-server on the recommended settings. Not a registry proof (that needs a pinned image), just a first pass.
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin LAB=~/src/ext/local-ai-registry-20261014/lab/lab.py ./precheck.sh   [MODELS="..."] [CTX=32768]
set -euo pipefail
cd "$(dirname "$0")"
: "${SYCL_BIN:?set SYCL_BIN}"; : "${LAB:?set LAB}"; CTX="${CTX:-32768}"
MODELS="${MODELS:-qwen3.8-27b gemma-4-31b-qat muse-glimmer}"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
DEVS=$("$SYCL_BIN/llama-bench" --list-devices 2>&1)
echo "$DEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc)" || { echo "!! SYCL0 is not the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1); [ "${FREE:-0}" -ge 28000 ] || { echo "!! only ${FREE:-?} MiB free"; exit 2; }
RUN_ID="p15pre-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; PORT=8099; echo $$ > "$OUT/pid"
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "level_zero=$(pacman -Q level-zero-loader intel-compute-runtime 2>/dev/null | tr '\n' ' ')"
  echo "llama_sycl=$("$SYCL_BIN/llama-bench" --version 2>&1 | grep -m1 '^version:')"; echo "sycl_device=$(echo "$DEVS" | grep -m1 SYCL0)"
  echo "lab=$LAB lab_commit=$(git -C "$(dirname "$LAB")" rev-parse HEAD)"; echo "ctx=$CTX models=$MODELS"; } > "$OUT/env.txt"; cat "$OUT/env.txt"
mfile() { local g; g=$(grep "^$1|" models.conf | cut -d'|' -f3); find ~/.lmstudio ~/.cache/lm-studio -iname "$g" 2>/dev/null | grep -v mmproj | head -n1 || true; }
for M in $MODELS; do
  F=$(mfile $M); [ -n "$F" ] || { echo "!! no file for $M"; continue; }; sha256sum "$F" >> "$OUT/models.sha256"
  echo ">> server $M ctx $CTX"
  "$SYCL_BIN/llama-server" -m "$F" -ngl 99 -c $CTX --port $PORT --host 127.0.0.1 -np 1 --no-webui --jinja \
    -fa on -b 2048 -ub 2048 --alias "$M" > "$OUT/$M.server.log" 2>&1 &
  SPID=$!; up=0
  for _ in $(seq 1 300); do curl -sf http://127.0.0.1:$PORT/health >/dev/null 2>&1 && { up=1; break; }; kill -0 $SPID 2>/dev/null || break; sleep 1; done
  if [ $up = 1 ]; then python3 -I gates.py --lab "$LAB" --endpoint http://127.0.0.1:$PORT --ctx $CTX --label "$M" --out "$OUT/$M.gates.json" || true
  else echo "!! server failed: $M"; fi
  kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; sleep 3
done
echo ">> done $RUN_ID"; rm -f "$OUT/pid"
