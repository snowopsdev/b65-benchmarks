#!/usr/bin/env bash
# Phase 2: same llama-bench tests on Vulkan (fa 0) and SYCL (fa 0 and 1), same GGUFs, same commit.
# Usage: B65_VK_INDEX=<idx> SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./phase2.sh     (DRY=1: one model, pp512 + tg128 per backend)
# Local changes (see README.md): vendor Vulkan build by default, awk instead of bc, B65-only + VRAM precheck,
# xe "card" energy channel by label, 10 Hz trace + stamped --progress for board W over the timed reps,
# strict per-test device check (gpu_info), pid/done markers for the dashboard, t_end column.
set -euo pipefail
cd "$(dirname "$0")"
VK_LB="${LLAMA_BENCH:-../vendor/llama.cpp/build/bin/llama-bench}"; SY_LB="${SYCL_BIN:?set SYCL_BIN}/llama-bench"
[ -n "${B65_VK_INDEX:-}" ] || { echo "Set B65_VK_INDEX"; exit 1; }
for b in "$VK_LB" "$SY_LB"; do [ -x "$b" ] || { echo "$b not found"; exit 1; }; done
ONEAPI_ENV="${ONEAPI_ENV:-/opt/intel/oneapi/setvars.sh}"; [ -f "$ONEAPI_ENV" ] || { echo "!! $ONEAPI_ENV not found"; exit 1; }
REPS="${REPS:-5}"; DRY="${DRY:-0}"
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }   # local: no bc on this machine
sycl_env() { echo "source '$ONEAPI_ENV' --force >/dev/null 2>&1; export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1"; }
# local: only the B65 visible to Vulkan, its VRAM free, and SYCL level_zero:0 is the B65
DEVS=$(GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX" "$VK_LB" --list-devices 2>&1)
echo "$DEVS" | grep -q "BMG" && ! echo "$DEVS" | grep -q "NVIDIA" || { echo "!! Vulkan devices are not just the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1)
[ "${FREE:-0}" -ge 28000 ] || { echo "!! Only ${FREE:-?} MiB free on the B65. Unload LM Studio models (lms unload --all)."; exit 2; }
SDEVS=$(bash -c "$(sycl_env); '$SY_LB' --list-devices" 2>&1)
echo "$SDEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc|Graphics)" || { echo "!! SYCL device 0 is not the B65:"; echo "$SDEVS"; exit 2; }

RUN_ID="p2-$(date +%Y%m%d-%H%M%S)"; [ "$DRY" = 1 ] && RUN_ID="p2-dry-$(date +%Y%m%d-%H%M%S)"
OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo "$$" > "$OUT/pid"
ENERGY=""
for h in /sys/class/hwmon/hwmon*; do   # local: pick the xe "card" channel by label
  [ "$(cat "$h/name" 2>/dev/null)" = "xe" ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done
done
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }
stamp() { while IFS= read -r l; do echo "$EPOCHREALTIME $l"; done; }
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "mesa=$(pacman -Q mesa 2>/dev/null)"
  echo "omarchy=$(omarchy-version 2>/dev/null || echo unknown)"
  echo "compute_runtime=$(pacman -Q intel-compute-runtime 2>/dev/null)"; echo "level_zero=$(pacman -Q level-zero-loader 2>/dev/null)"
  echo "oneapi=$(pacman -Q intel-oneapi-basekit intel-oneapi-dpcpp-cpp intel-oneapi-mkl-sycl 2>/dev/null | tr '\n' ' ')"
  echo "igc=$(pacman -Q intel-graphics-compiler 2>/dev/null)"
  echo "vulkan_bench=$("$VK_LB" --version 2>&1 | grep -m1 version)"
  echo "sycl_bench=$(bash -c "$(sycl_env); '$SY_LB' --version" 2>&1 | grep -m1 '^version:')"
  echo "sycl_device=$(echo "$SDEVS" | grep -m1 SYCL0)"
  echo "vk_visible=$B65_VK_INDEX"; echo "vram_free_mib=$FREE"; echo "energy_file=${ENERGY:-none}"; echo "reps=$REPS"; echo "dry=$DRY"; } > "$OUT/env.txt"

TESTS=( "pp512|-p 512 -n 0" "pp4096|-p 4096 -n 0" "pp16384|-p 16384 -n 0"
        "tg128|-p 0 -n 128" "tg128@d4096|-p 0 -n 128 -d 4096" "tg128@d16384|-p 0 -n 128 -d 16384" "tg128@d32768|-p 0 -n 128 -d 32768" )
[ "$DRY" = 1 ] && TESTS=( "pp512|-p 512 -n 0" "tg128|-p 0 -n 128" )
[ -n "${TESTS_SPEC:-}" ] && IFS=';' read -r -a TESTS <<< "$TESTS_SPEC"   # local: optional override
# backend|fa
RUNS=( "vulkan|0" "sycl|0" "sycl|1" )
[ -n "${RUNS_SPEC:-}" ] && read -r -a RUNS <<< "$RUNS_SPEC"

run_one() {  # backend fa name file label args
  local B=$1 FA=$2 N=$3 F=$4 L=$5 A=$6 st=ok tag="$3.$1.fa$2.$5" TP=""
  local e0 t0 e1 t1
  [ -n "$ENERGY" ] && { trace "$OUT/$tag.power.csv" & TP=$!; }
  e0=$(read_e); t0=$EPOCHREALTIME
  if [ "$B" = vulkan ]; then
    # shellcheck disable=SC2086
    GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX" "$VK_LB" -m "$F" -ngl 99 -fa "$FA" -r "$REPS" $A -o jsonl --progress \
      > "$OUT/$tag.jsonl" 2> >(stamp > "$OUT/$tag.log") || st=fail
  else
    bash -c "$(sycl_env); exec '$SY_LB' -m '$F' -ngl 99 -fa $FA -r $REPS $A -o jsonl --progress" \
      > "$OUT/$tag.jsonl" 2> >(stamp > "$OUT/$tag.log") || st=fail
  fi
  e1=$(read_e); t1=$EPOCHREALTIME
  [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }
  wait   # trace is gone; this lets the stderr stamper flush
  grep -qiE "out of memory|ErrorOutOfDeviceMemory|failed to allocate|UR_RESULT_ERROR_OUT_OF|OUT_OF_DEVICE_MEMORY" "$OUT/$tag.log" && st=oom
  echo "$B,$FA,$L,$N,$st,$( [ -n "$e0" ] && calc "($e1-$e0)/1000000"),$(calc "$t1-$t0"),$t1" >> "$OUT/energy.csv"
  [ $st != ok ] && echo "!! $tag: $st, see $OUT/$tag.log"
  # local: strict device check on every successful test (gpu_info names the B65 / BMG / Arc, never NVIDIA)
  if [ $st = ok ]; then
    grep -q '"gpu_info"' "$OUT/$tag.jsonl" && ! grep -qi 'nvidia' "$OUT/$tag.jsonl" && grep -qiE '"gpu_info": *"[^"]*(BMG|B65|Arc|Intel)' "$OUT/$tag.jsonl" \
      || { echo "!! $tag did not run on the B65, aborting"; exit 2; }
  fi
  return 0
}

echo "backend,fa,test,model,status,energy_j,seconds,t_end" > "$OUT/energy.csv"
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
python3 summarize2.py "$OUT"
date -Iseconds > "$OUT/done"
echo "Done: $OUT"
