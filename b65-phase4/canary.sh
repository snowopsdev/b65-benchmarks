#!/usr/bin/env bash
# Canary: rerun after any Mesa / kernel / oneAPI / llama.cpp / LM Studio update. Flags >5% drift.
# Phase 6 update (Forge): default UB=2048 vs baseline_ub2048.json; UB=512 ./canary.sh compares with the old baseline.json.
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./canary.sh
#   MODELS="qwen3.8-27b muse-glimmer" (default; add gemma-4-31b-qat for all 3)
#   UBCHECK=1  also run pp4096/pp16384 at ub 2048 on SYCL (and on Vulkan if B65_VK_INDEX is set)
#   DRY=1      local: smoke test (first model, REPS=1, canary tests only) into raw/p4-dry-*
# Local changes (README.md): awk not bc, board W over the timed reps (trace + stamped --progress, same method as the
# baseline), xe "card" energy by label, SYCL0/VRAM precheck, strict gpu_info check, vendor Vulkan llama-bench, pid/done.
set -euo pipefail
cd "$(dirname "$0")"
LB="${SYCL_BIN:?set SYCL_BIN}/llama-bench"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
MODELS="${MODELS:-qwen3.8-27b muse-glimmer}"; REPS="${REPS:-5}"; UBCHECK="${UBCHECK:-0}"; DRY="${DRY:-0}"; UB="${UB:-2048}"
[ "$DRY" = 1 ] && { MODELS="${MODELS%% *}"; REPS=1; UBCHECK=0; }
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }   # local: no bc on this machine
DEVS=$("$LB" --list-devices 2>&1)   # local: SYCL0 must be the B65 with its VRAM free
echo "$DEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc)" || { echo "!! SYCL0 is not the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1); [ "${FREE:-0}" -ge 28000 ] || { echo "!! only ${FREE:-?} MiB free"; exit 2; }
RUN_ID="p4-$( [ "$DRY" = 1 ] && echo dry- )$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo $$ > "$OUT/pid"
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat "$h/name" 2>/dev/null)" = xe ] || continue   # local: the "card" channel by label
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done; done
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }
stamp() { while IFS= read -r l; do echo "$EPOCHREALTIME $l"; done; }
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null || glxinfo 2>/dev/null | grep -m1 'OpenGL version')"
  echo "oneapi=$(icpx --version 2>/dev/null | head -n1)"; echo "level_zero=$(pacman -Q level-zero-loader intel-compute-runtime 2>/dev/null | tr '\n' ' ')"
  echo "llama_sycl=$("$LB" --version 2>&1 | grep -m1 '^version:')"; echo "omarchy=$(omarchy-version 2>/dev/null || true)"
  echo "sycl_device=$(echo "$DEVS" | grep -m1 SYCL0)"; echo "reps=$REPS"; echo "models=$MODELS"; echo "ub=$UB"; echo "ubcheck=$UBCHECK"; echo "dry=$DRY"; echo "vk_index=${B65_VK_INDEX:-}"
  echo "energy_file=${ENERGY:-none}"; } > "$OUT/env.txt"
cat "$OUT/env.txt"
echo "backend,model,test,ub,tok_s,board_w,invocation_w" > "$OUT/canary.csv"
run() { # backend bin model file label ub args...
  local be=$1 bin=$2 m=$3 f=$4 lab=$5 ub=$6; shift 6
  local e0="" e1="" t0 t1 fa=1 TP="" tag="$m.$be.$lab.ub$ub" ok=1; [ "$be" = vulkan ] && fa=0
  echo ">> $be $m $lab ub$ub"
  [ -n "$ENERGY" ] && { trace "$OUT/$tag.power.csv" & TP=$!; }
  t0=$EPOCHREALTIME; [ -n "$ENERGY" ] && e0=$(cat "$ENERGY")
  "$bin" -m "$f" -ngl 99 -fa $fa -r "$REPS" -b 2048 -ub "$ub" "$@" -o jsonl --progress > "$OUT/$tag.jsonl" 2> >(stamp > "$OUT/$tag.log") || ok=0
  t1=$EPOCHREALTIME; [ -n "$ENERGY" ] && e1=$(cat "$ENERGY")
  [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }; wait
  if [ $ok = 0 ] || ! grep -q '^{' "$OUT/$tag.jsonl"; then echo "$be,$m,$lab,$ub,FAIL,," >> "$OUT/canary.csv"; echo "!! $tag failed, see $OUT/$tag.log"; return 0; fi
  # local: strict device check on every test (gpu_info names the B65 / BMG / Arc, never NVIDIA)
  grep -qiE '"gpu_info": *"[^"]*(B65|BMG|Arc)' "$OUT/$tag.jsonl" && ! grep -qi nvidia "$OUT/$tag.jsonl" || { echo "!! $tag did not run on the B65, aborting"; exit 2; }
  local ts w iw=""; ts=$(python3 -c "import json,sys;print(round([json.loads(l) for l in open(sys.argv[1]) if l.startswith('{')][-1]['avg_ts'],2))" "$OUT/$tag.jsonl")
  # local: board W over the timed reps only (same method as the Phase 2 baseline); invocation average kept alongside
  w=$(python3 -c "
import json,sys; sys.path.insert(0,'..'); from powerwin import test_watts
j=[json.loads(l) for l in open(sys.argv[1]+'.jsonl') if l.startswith('{')][-1]; w=test_watts(sys.argv[2], sys.argv[3], sys.argv[4], j)
print(f'{w:.1f}' if w else '')" "$OUT/$tag" "$OUT" "$m.$be.$lab" "ub$ub")
  [ -n "$e0" ] && iw=$(calc "($e1-$e0)/1000000/($t1-$t0)" | xargs printf %.1f)
  echo "$be,$m,$lab,$ub,$ts,$w,$iw" >> "$OUT/canary.csv"; echo "  $be $m $lab ub$ub: $ts tok/s ${w}W"
}
for M in $MODELS; do
  GLOB=$(grep "^$M|" models.conf | cut -d'|' -f3)
  F=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$F" ] || { echo "!! $M not found"; continue; }
  echo "== $M"; sha256sum "$F" >> "$OUT/models.sha256"
  run sycl "$LB" "$M" "$F" pp512 $UB -p 512 -n 0
  run sycl "$LB" "$M" "$F" pp16384 $UB -p 16384 -n 0
  run sycl "$LB" "$M" "$F" tg128 $UB -p 0 -n 128
  run sycl "$LB" "$M" "$F" tg128@d16384 $UB -p 0 -n 128 -d 16384
  if [ "$UBCHECK" = 1 ]; then
    run sycl "$LB" "$M" "$F" pp4096 512 -p 4096 -n 0
    for T in 4096 16384; do run sycl "$LB" "$M" "$F" pp$T 2048 -p $T -n 0; done
    run sycl "$LB" "$M" "$F" tg128@d16384 2048 -p 0 -n 128 -d 16384
    if [ -n "${B65_VK_INDEX:-}" ]; then
      VK="${LLAMA_BENCH:-../vendor/llama.cpp/build/bin/llama-bench}"   # local: the pinned Vulkan build
      for VUB in 512 2048; do GGML_VK_VISIBLE_DEVICES=$B65_VK_INDEX ONEAPI_DEVICE_SELECTOR= run vulkan "$VK" "$M" "$F" pp16384 $VUB -p 16384 -n 0; done   # local: VUB, so the loop cannot overwrite UB
    fi
  fi
done
python3 compare4.py "$OUT"
date -Iseconds > "$OUT/done"; echo "Done: $OUT"
