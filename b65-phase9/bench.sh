#!/usr/bin/env bash
# Phase 9 part L: llama.cpp b11574 (8bb3cf0d2) vs v1.0.0 (b12359, b1b770d90) with llama-bench, same session, same models.
# Every test runs old then new back to back, so driver/thermal drift hits both builds alike.
# SYCL: the recipe (fa on, -b 2048 -ub 2048), the canary tests plus pp4096. Vulkan: fa off, ub 512 (the Vulkan recipe).
# Usage: ./bench.sh   MODELS="qwen3.8-27b ..."  REPS=5  VULKAN=0 (skip Vulkan)  DRY=1 (first model, pp512 + tg128, 1 rep)
# Method as b65-phase4/canary.sh: board W over the timed reps (powerwin.py), strict device check per test.
set -euo pipefail
cd "$(dirname "$0")"
MAIN="${MAIN:-$HOME/Projects/b65-benchmarks}"
OLD_SYCL="${OLD_SYCL:-$HOME/src/llama.cpp/build-sycl/bin}"; NEW_SYCL="${NEW_SYCL:-$HOME/src/llama.cpp-1.0.0/build-sycl/bin}"
OLD_VK="${OLD_VK:-$MAIN/vendor/llama.cpp/build/bin}"; NEW_VK="${NEW_VK:-$HOME/src/llama.cpp-1.0.0/build-vulkan/bin}"
B65_VK_INDEX="${B65_VK_INDEX:-1}"
MODELS="${MODELS:-qwen3.8-27b muse-glimmer gemma-4-31b-qat}"; REPS="${REPS:-5}"; VULKAN="${VULKAN:-1}"; DRY="${DRY:-0}"
[ "$DRY" = 1 ] && { MODELS="${MODELS%% *}"; REPS=1; }
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }
for B in "$OLD_SYCL" "$NEW_SYCL"; do
  DEVS=$("$B/llama-bench" --list-devices 2>&1)
  echo "$DEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc|e222)" || { echo "!! SYCL0 is not the B65 ($B):"; echo "$DEVS"; exit 2; }
  FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1); [ "${FREE:-0}" -ge 28000 ] || { echo "!! only ${FREE:-?} MiB free"; exit 2; }
done
RUN_ID="p9l-$( [ "$DRY" = 1 ] && echo dry- )$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo $$ > "$OUT/pid"
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat "$h/name" 2>/dev/null)" = xe ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done; done
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }
stamp() { while IFS= read -r l; do echo "$EPOCHREALTIME $l"; done; }
ver() { "$1/llama-bench" --version 2>&1 | grep -m1 '^version:'; }
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null)"; echo "oneapi=$(icpx --version 2>/dev/null | head -n1)"
  echo "level_zero=$(pacman -Q level-zero-loader intel-compute-runtime 2>/dev/null | tr '\n' ' ')"
  echo "old_sycl=$(ver "$OLD_SYCL")"; echo "new_sycl=$(ver "$NEW_SYCL")"
  [ "$VULKAN" = 1 ] && { echo "old_vulkan=$(ver "$OLD_VK")"; echo "new_vulkan=$(ver "$NEW_VK")"; echo "vk_index=$B65_VK_INDEX"; }
  echo "sycl_device=$(echo "$DEVS" | grep -m1 SYCL0)"; echo "omarchy=$(omarchy-version 2>/dev/null || true)"
  echo "reps=$REPS"; echo "models=$MODELS"; echo "vulkan=$VULKAN"; echo "dry=$DRY"; echo "energy_file=${ENERGY:-none}"
  echo "kit_commit=$(git rev-parse HEAD)"; } > "$OUT/env.txt"
cat "$OUT/env.txt"
echo "backend,build,model,test,ub,tok_s,sd,board_w,invocation_w" > "$OUT/results.csv"
run() { # backend build bindir model file label ub args...
  local be=$1 bu=$2 bin=$3 m=$4 f=$5 lab=$6 ub=$7; shift 7
  local e0="" e1="" t0 t1 fa=1 TP="" tag="$m.$be.$bu.$lab" ok=1; [ "$be" = vulkan ] && fa=0
  echo ">> $be $bu $m $lab ub$ub"; echo "$m|$be $bu $lab|$EPOCHREALTIME" > "$OUT/current"
  [ -n "$ENERGY" ] && { trace "$OUT/$tag.power.csv" & TP=$!; }
  t0=$EPOCHREALTIME; [ -n "$ENERGY" ] && e0=$(cat "$ENERGY")
  "$bin/llama-bench" -m "$f" -ngl 99 -fa $fa -r "$REPS" -b 2048 -ub "$ub" "$@" -o jsonl --progress > "$OUT/$tag.jsonl" 2> >(stamp > "$OUT/$tag.log") || ok=0
  t1=$EPOCHREALTIME; [ -n "$ENERGY" ] && e1=$(cat "$ENERGY")
  [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }; wait
  if [ $ok = 0 ] || ! grep -q '^{' "$OUT/$tag.jsonl"; then echo "$be,$bu,$m,$lab,$ub,FAIL,,," >> "$OUT/results.csv"; echo "!! $tag failed, see $OUT/$tag.log"; return 0; fi
  grep -qiE '"gpu_info": *"[^"]*(B65|BMG|Arc|e222)' "$OUT/$tag.jsonl" && ! grep -qi nvidia "$OUT/$tag.jsonl" || { echo "!! $tag did not run on the B65, aborting"; exit 2; }
  local ts sd w iw=""
  read -r ts sd < <(python3 -c "import json,sys;j=[json.loads(l) for l in open(sys.argv[1]) if l.startswith('{')][-1];print(round(j['avg_ts'],2),round(j['stddev_ts'],2))" "$OUT/$tag.jsonl")
  w=$(python3 -c "
import json,sys; sys.path.insert(0,sys.argv[5]); from powerwin import test_watts
j=[json.loads(l) for l in open(sys.argv[1]+'.jsonl') if l.startswith('{')][-1]; w=test_watts(sys.argv[2], sys.argv[3], sys.argv[4], j)
print(f'{w:.1f}' if w else '')" "$OUT/$tag" "$OUT" "$m.$be.$bu" "$lab" "$MAIN" 2>/dev/null || true)
  [ -n "$e0" ] && iw=$(calc "($e1-$e0)/1000000/($t1-$t0)" | xargs printf %.1f)
  echo "$be,$bu,$m,$lab,$ub,$ts,$sd,$w,$iw" >> "$OUT/results.csv"; echo "   $ts ± $sd tok/s ${w}W"
}
SYCL_TESTS=( "pp512|-p 512 -n 0" "pp4096|-p 4096 -n 0" "pp16384|-p 16384 -n 0" "tg128|-p 0 -n 128" "tg128@d16384|-p 0 -n 128 -d 16384" )
VK_TESTS=( "pp512|-p 512 -n 0" "pp16384|-p 16384 -n 0" "tg128|-p 0 -n 128" )
[ "$DRY" = 1 ] && { SYCL_TESTS=( "pp512|-p 512 -n 0" "tg128|-p 0 -n 128" ); VK_TESTS=( "tg128|-p 0 -n 128" ); }
for M in $MODELS; do
  GLOB=$(grep "^$M|" ../models.conf | cut -d'|' -f3)
  F=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$F" ] || { echo "!! $M not found"; continue; }
  echo "== $M ($F)"; sha256sum "$F" >> "$OUT/models.sha256"
  # untimed priming per build: the dry run's first-ever v1.0.0 decode gave 10.9 tok/s (23.7 old) and 24.4 on rerun, i.e.
  # one-time JIT of the new kernels; this keeps that out of the timed tests
  for B in "$OLD_SYCL" "$NEW_SYCL"; do "$B/llama-bench" -m "$F" -ngl 99 -fa 1 -b 2048 -ub 2048 -p 512 -n 32 -r 1 > /dev/null 2>&1 || true; done
  for T in "${SYCL_TESTS[@]}"; do L="${T%%|*}"; A="${T#*|}"
    # shellcheck disable=SC2086
    { run sycl old "$OLD_SYCL" "$M" "$F" "$L" 2048 $A; run sycl new "$NEW_SYCL" "$M" "$F" "$L" 2048 $A; }
  done
  if [ "$VULKAN" = 1 ]; then for T in "${VK_TESTS[@]}"; do L="${T%%|*}"; A="${T#*|}"
    for BU in old new; do BIN=$OLD_VK; [ $BU = new ] && BIN=$NEW_VK
      # shellcheck disable=SC2086
      GGML_VK_VISIBLE_DEVICES=$B65_VK_INDEX ONEAPI_DEVICE_SELECTOR= run vulkan $BU "$BIN" "$M" "$F" "$L" 512 $A; done; done; fi
  # spot-check: greedy 96 tokens on both SYCL builds, to catch fast-but-garbage output
  for BU in old new; do BIN=$OLD_SYCL; [ $BU = new ] && BIN=$NEW_SYCL
    "$BIN/llama-completion" -m "$F" -ngl 99 -fa on -c 2048 -n 96 --temp 0 --seed 1 -no-cnv \
      -p "Explain in three sentences why GPU memory bandwidth matters for LLM token generation." \
      > "$OUT/$M.sycl.$BU.spotcheck.txt" 2> "$OUT/$M.sycl.$BU.spotcheck.log" < /dev/null || echo "!! $M $BU spot-check failed"; done
done
rm -f "$OUT/current"; python3 summarize.py "$OUT" | tee "$OUT/summary.md" || true
date -Iseconds > "$OUT/done"; echo "Done: $OUT"
