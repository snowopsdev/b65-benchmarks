#!/usr/bin/env bash
# llama-server rerun for Qwen and Muse at the new SYCL default -b 2048 -ub 2048 (Forge's Phase 4 decision).
# Same method as Phase 1S (SYCL, fa on, ctx 32768, 512/4K/16K prompts x 3 reps, prompt cache off, 30 s loaded idle + VRAM);
# the only change is the micro-batch. Gemma at ub 2048 was already measured in the Gemma diagnostic (gd-20261013-123933).
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./ubserve.sh      MODELS="qwen3.8-27b muse-glimmer" (default)
set -euo pipefail
cd "$(dirname "$0")"
LS="${SYCL_BIN:?set SYCL_BIN}/llama-server"; LB="$SYCL_BIN/llama-bench"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
MODELS="${MODELS:-qwen3.8-27b muse-glimmer}"; CTX=32768; PORT="${PORT:-8099}"
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }
DEVS=$("$LB" --list-devices 2>&1)
echo "$DEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc)" || { echo "!! SYCL0 is not the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1); [ "${FREE:-0}" -ge 28000 ] || { echo "!! only ${FREE:-?} MiB free"; exit 2; }
RUN_ID="us-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo $$ > "$OUT/pid"
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat "$h/name" 2>/dev/null)" = xe ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done; done
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
proc_vram_mib() {
  for f in /proc/"$1"/fdinfo/*; do grep -q 'drm-driver:.*xe' "$f" 2>/dev/null && cat "$f"; echo "--"; done 2>/dev/null |
    awk '/^drm-client-id:/ {id=$2} /^drm-resident-vram0:/ {v=$2; u=$3; k=(u=="MiB")?v*1024:(u=="GiB")?v*1048576:(u=="KiB")?v:v/1024; if (!(id in seen)) {seen[id]=1; tot+=k}} END {printf "%d", tot/1024}'
}
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "backend=sycl"; echo "fa=on"; echo "ctx=$CTX"
  echo "server_flags=-ngl 99 -fa on -c $CTX -np 1 -b 2048 -ub 2048"; echo "llama_server=$("$LS" --version 2>&1 | grep -m1 '^version:')"
  echo "sycl_device=$(echo "$DEVS" | grep -m1 SYCL0)"; echo "compute_runtime=$(pacman -Q intel-compute-runtime 2>/dev/null)"; echo "oneapi=$(pacman -Q intel-oneapi-dpcpp-cpp 2>/dev/null)"
  echo "models=$MODELS"; echo "energy_file=${ENERGY:-none}"; echo "baseline_run=p1s-20261013-111949"; } > "$OUT/env.txt"
echo "model,loaded_idle_w,vram_used_mib" > "$OUT/idle_loaded.csv"
for NAME in $MODELS; do
  GLOB=$(grep "^$NAME|" models.conf | cut -d'|' -f3)
  FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$FILE" ] || { echo "!! no file for $NAME"; continue; }
  sha256sum "$FILE" >> "$OUT/models.sha256"
  echo ">> server $NAME"
  "$LS" -m "$FILE" -ngl 99 -fa on -c "$CTX" -b 2048 -ub 2048 --port "$PORT" --host 127.0.0.1 -np 1 --no-webui > "$OUT/$NAME.server.log" 2>&1 &
  SPID=$!; ok=0; for _ in $(seq 1 240); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { ok=1; break; }; kill -0 $SPID 2>/dev/null || break; sleep 1; done
  if [ $ok = 0 ]; then echo "!! server did not come up for $NAME"; kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; continue; fi
  sleep 5; e0=$(read_e); t0=$EPOCHREALTIME; sleep 30; e1=$(read_e); t1=$EPOCHREALTIME
  echo "$NAME,$( [ -n "$e0" ] && calc "($e1-$e0)/1000000/($t1-$t0)"),$(proc_vram_mib $SPID)" >> "$OUT/idle_loaded.csv"
  echo ">> requests $NAME"
  python3 serve_bench.py --port "$PORT" --model "$NAME" --out "$OUT" --energy "${ENERGY:-}" || echo "!! serve_bench failed for $NAME"
  kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; sleep 5
done
date -Iseconds > "$OUT/done"; echo "Done: $OUT"
