#!/usr/bin/env bash
# Canary (Phase 6 update: default UB=2048 vs baseline_ub2048.json; UB=512 for the old baseline): rerun after any Mesa / kernel / oneAPI / llama.cpp / LM Studio update. Flags >5% drift vs baseline.json.
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./canary.sh
#   MODELS="qwen3.8-27b muse-glimmer" (default; add gemma-4-31b-qat for all 3)
#   UBCHECK=1  also run pp4096/pp16384 at ub 2048 on SYCL (and on Vulkan if B65_VK_INDEX is set)
set -euo pipefail
cd "$(dirname "$0")"
LB="${SYCL_BIN:?set SYCL_BIN}/llama-bench"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
MODELS="${MODELS:-qwen3.8-27b muse-glimmer}"; REPS="${REPS:-5}"; UBCHECK="${UBCHECK:-0}"; UB="${UB:-2048}"
RUN_ID="p4-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat $h/name 2>/dev/null)" = xe ] && for f in $h/energy*_input; do [ -r "$f" ] && { ENERGY=$f; break 2; }; done; done
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null || glxinfo 2>/dev/null | grep -m1 'OpenGL version')"
  echo "oneapi=$(icpx --version 2>/dev/null | head -n1)"; echo "level_zero=$(pacman -Q level-zero-loader intel-compute-runtime 2>/dev/null | tr '\n' ' ')"
  echo "llama_sycl=$("$LB" --version 2>&1 | grep -m1 version)"; echo "omarchy=$(omarchy-version 2>/dev/null || true)"
  echo "energy_file=${ENERGY:-none}"; } > "$OUT/env.txt"
cat "$OUT/env.txt"
echo "backend,model,test,ub,tok_s,board_w" > "$OUT/canary.csv"
run() { # backend bin model file label ub args...
  local be=$1 bin=$2 m=$3 f=$4 lab=$5 ub=$6; shift 6
  local e0="" e1="" t0 t1 fa=1; [ "$be" = vulkan ] && fa=0
  t0=$(date +%s.%N); [ -n "$ENERGY" ] && e0=$(cat $ENERGY)
  "$bin" -m "$f" -ngl 99 -fa $fa -r "$REPS" -b 2048 -ub "$ub" "$@" -o jsonl > "$OUT/$m.$be.$lab.ub$ub.jsonl" 2> "$OUT/$m.$be.$lab.ub$ub.log" || { echo "$be,$m,$lab,$ub,FAIL," >> "$OUT/canary.csv"; return; }
  t1=$(date +%s.%N); [ -n "$ENERGY" ] && e1=$(cat $ENERGY)
  local ts w=""; ts=$(python3 -c "import json,sys;print(round(json.loads(open(sys.argv[1]).readlines()[-1])['avg_ts'],2))" "$OUT/$m.$be.$lab.ub$ub.jsonl")
  [ -n "$e0" ] && w=$(echo "($e1-$e0)/1000000/($t1-$t0)" | bc -l | xargs printf %.1f)
  echo "$be,$m,$lab,$ub,$ts,$w" >> "$OUT/canary.csv"; echo "  $be $m $lab ub$ub: $ts tok/s ${w}W"
}
first=1
for M in $MODELS; do
  GLOB=$(grep "^$M|" models.conf | cut -d'|' -f3)
  F=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$F" ] || { echo "!! $M not found"; continue; }
  echo "== $M"; sha256sum "$F" >> "$OUT/models.sha256"
  run sycl "$LB" "$M" "$F" pp512 $UB -p 512 -n 0
  if [ $first = 1 ]; then grep -qi intel "$OUT/$M.sycl.pp512.ub$UB.log" "$OUT/$M.sycl.pp512.ub$UB.jsonl" || { echo "!! not the B65"; exit 2; }; first=0; fi
  run sycl "$LB" "$M" "$F" pp16384 $UB -p 16384 -n 0
  run sycl "$LB" "$M" "$F" tg128 $UB -p 0 -n 128
  run sycl "$LB" "$M" "$F" tg128@d16384 $UB -p 0 -n 128 -d 16384
  if [ "$UBCHECK" = 1 ]; then
    run sycl "$LB" "$M" "$F" pp4096 512 -p 4096 -n 0
    for T in 4096 16384; do run sycl "$LB" "$M" "$F" pp$T 2048 -p $T -n 0; done
    run sycl "$LB" "$M" "$F" tg128@d16384 2048 -p 0 -n 128 -d 16384
    if [ -n "${B65_VK_INDEX:-}" ]; then
      VK="${LLAMA_BENCH:-llama-bench}"
      for UB in 512 2048; do GGML_VK_VISIBLE_DEVICES=$B65_VK_INDEX ONEAPI_DEVICE_SELECTOR= run vulkan "$VK" "$M" "$F" pp16384 $UB -p 16384 -n 0; done
    fi
  fi
done
python3 compare4.py "$OUT"
echo "Done: $OUT"
