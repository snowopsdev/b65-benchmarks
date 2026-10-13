#!/usr/bin/env bash
# Phase 2: same llama-bench tests on Vulkan (fa 0) and SYCL (fa 0 and 1), same GGUFs, same commit.
# Usage: B65_VK_INDEX=<idx> SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./phase2.sh     (DRY=1: one model, pp512 + tg128 per backend)
set -euo pipefail
cd "$(dirname "$0")"
VK_LB="${LLAMA_BENCH:-llama-bench}"; SY_LB="${SYCL_BIN:?set SYCL_BIN}/llama-bench"
[ -n "${B65_VK_INDEX:-}" ] || { echo "Set B65_VK_INDEX"; exit 1; }
REPS="${REPS:-5}"; DRY="${DRY:-0}"
OUT="raw/p2-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$OUT"
ENERGY=$(for h in /sys/class/hwmon/hwmon*; do [ "$(cat $h/name)" = xe ] && ls $h/energy*_input 2>/dev/null | head -n1; done | head -n1)
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
{ echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "mesa=$(pacman -Q mesa 2>/dev/null)"
  echo "compute_runtime=$(pacman -Q intel-compute-runtime 2>/dev/null)"; echo "level_zero=$(pacman -Q level-zero-loader 2>/dev/null)"
  echo "oneapi=$(pacman -Q intel-oneapi-basekit 2>/dev/null)"
  echo "vulkan_bench=$("$VK_LB" --version 2>&1 | grep -m1 version)"
  echo "sycl_bench=$(bash -c "source /opt/intel/oneapi/setvars.sh --force >/dev/null; '$SY_LB' --version 2>&1 | grep -m1 version")"
  echo "energy_file=${ENERGY:-none}"; echo "reps=$REPS"; } > "$OUT/env.txt"

TESTS=( "pp512|-p 512 -n 0" "pp4096|-p 4096 -n 0" "pp16384|-p 16384 -n 0"
        "tg128|-p 0 -n 128" "tg128@d4096|-p 0 -n 128 -d 4096" "tg128@d16384|-p 0 -n 128 -d 16384" "tg128@d32768|-p 0 -n 128 -d 32768" )
[ "$DRY" = 1 ] && TESTS=( "pp512|-p 512 -n 0" "tg128|-p 0 -n 128" )
# backend|fa
RUNS=( "vulkan|0" "sycl|0" "sycl|1" )

run_one() {  # backend fa name file label args
  local B=$1 FA=$2 N=$3 F=$4 L=$5 A=$6 st=ok tag="$3.$1.fa$2.$5"
  local e0 t0 e1 t1; e0=$(read_e); t0=$(date +%s.%N)
  if [ "$B" = vulkan ]; then
    # shellcheck disable=SC2086
    GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX" "$VK_LB" -m "$F" -ngl 99 -fa "$FA" -r "$REPS" $A -o jsonl > "$OUT/$tag.jsonl" 2> "$OUT/$tag.log" || st=fail
  else
    bash -c "source /opt/intel/oneapi/setvars.sh --force >/dev/null
      export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
      exec '$SY_LB' -m '$F' -ngl 99 -fa $FA -r $REPS $A -o jsonl" > "$OUT/$tag.jsonl" 2> "$OUT/$tag.log" || st=fail
  fi
  grep -qiE "out of memory|ErrorOutOfDeviceMemory|failed to allocate|UR_RESULT_ERROR_OUT_OF" "$OUT/$tag.log" && st=oom
  e1=$(read_e); t1=$(date +%s.%N)
  echo "$B,$FA,$L,$N,$st,$( [ -n "$e0" ] && echo "($e1-$e0)/1000000" | bc -l),$(echo "$t1-$t0" | bc -l)" >> "$OUT/energy.csv"
  grep -qi -E "intel|B65|BMG|Arc" "$OUT/$tag.jsonl" "$OUT/$tag.log" || { echo "!! $tag did not run on the Intel card, aborting"; exit 2; }
}

echo "backend,fa,test,model,status,energy_j,seconds" > "$OUT/energy.csv"
while IFS='|' read -r NAME QUANT GLOB; do
  [[ -z "$NAME" || "$NAME" == \#* ]] && continue
  FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$FILE" ] || { echo "!! no file for $NAME"; continue; }
  sha256sum "$FILE" >> "$OUT/models.sha256"
  for R in "${RUNS[@]}"; do B="${R%%|*}"; FA="${R#*|}"
    for T in "${TESTS[@]}"; do L="${T%%|*}"; A="${T#*|}"; echo ">> $NAME $B fa=$FA $L"; run_one "$B" "$FA" "$NAME" "$FILE" "$L" "$A"; done
  done
  [ "$DRY" = 1 ] && break
done < models.conf
python3 summarize2.py "$OUT"; echo "Done: $OUT"
