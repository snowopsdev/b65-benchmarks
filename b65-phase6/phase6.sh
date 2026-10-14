#!/usr/bin/env bash
# Phase 6: A Qwen/Muse coding with thinking off | B regenerate+edit with checkpoints on/off | C canary vs ub2048 baseline
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin B65_VK_INDEX=1 [VK_BIN=...] ./phase6.sh   PARTS="A B C"  DRY=1
# Header (prechecks, energy, server/stop) carried over from the locally patched Phase 5 kit.
set -euo pipefail
cd "$(dirname "$0")"
: "${SYCL_BIN:?set SYCL_BIN}"; PARTS="${PARTS:-A B C}"; DRY="${DRY:-0}"; REPS=5; [ "$DRY" = 1 ] && REPS=1
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
VK_BIN="${VK_BIN:-$PWD/../vendor/llama.cpp/build/bin}"   # local: the pinned Vulkan build (no ~/src/llama.cpp/build-vulkan here)
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }   # local: no bc on this machine
DEVS=$("$SYCL_BIN/llama-bench" --list-devices 2>&1)   # local: SYCL0 must be the B65 with its VRAM free
echo "$DEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc)" || { echo "!! SYCL0 is not the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1); [ "${FREE:-0}" -ge 28000 ] || { echo "!! only ${FREE:-?} MiB free"; exit 2; }
RUN_ID="p6-$( [ "$DRY" = 1 ] && echo dry- )$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; PORT=8099; echo $$ > "$OUT/pid"
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat "$h/name" 2>/dev/null)" = xe ] || continue   # local: the "card" channel by label
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done; done
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }
stamp() { while IFS= read -r l; do echo "$EPOCHREALTIME $l"; done; }
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "mesa=$(pacman -Q mesa 2>/dev/null)"
  echo "oneapi=$(icpx --version 2>/dev/null | head -n1)"; echo "level_zero=$(pacman -Q level-zero-loader intel-compute-runtime 2>/dev/null | tr '\n' ' ')"
  echo "llama_sycl=$("$SYCL_BIN/llama-bench" --version 2>&1 | grep -m1 '^version:')"; echo "vk_bin=${VK_BIN:-none} vk_index=${B65_VK_INDEX:-none}"
  echo "sycl_device=$(echo "$DEVS" | grep -m1 SYCL0)"; echo "parts_list=$PARTS"
  echo "parts=$PARTS dry=$DRY reps=$REPS energy_file=${ENERGY:-none}"; } > "$OUT/env.txt"; cat "$OUT/env.txt"
mfile() { local g; g=$(grep "^$1|" models.conf | cut -d'|' -f3); find ~/.lmstudio ~/.cache/lm-studio -iname "$g" 2>/dev/null | grep -v mmproj | head -n1 || true; }   # local: || true
ALL="qwen3.8-27b gemma-4-31b-qat muse-glimmer"
for M in $ALL; do F=$(mfile $M); [ -n "$F" ] && sha256sum "$F" >> "$OUT/models.sha256"; done

server() { # be model label args... ; starts server, waits for health
  local be=$1 m=$2 lab=$3; shift 3; local F; F=$(mfile $m); local bin="$SYCL_BIN/llama-server"; local envp=()
  if [ "$be" = vulkan ]; then bin="${VK_BIN}/llama-server"; envp=(env GGML_VK_VISIBLE_DEVICES=$B65_VK_INDEX ONEAPI_DEVICE_SELECTOR=); fi
  "${envp[@]}" "$bin" -m "$F" -ngl 99 -c 32768 --port $PORT --host 127.0.0.1 -np 1 --no-webui --jinja "$@" > "$OUT/$m.$be.$lab.server.log" 2>&1 &
  SPID=$!; echo ">> server $be $m $lab"; for _ in $(seq 1 240); do curl -sf http://127.0.0.1:$PORT/health >/dev/null 2>&1 && return 0; kill -0 $SPID 2>/dev/null || break; sleep 1; done
  echo "!! server failed: $m $be $lab"; kill $SPID 2>/dev/null || true; return 1; }
stop() { kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; sleep 3; }

# A: Phase 3 coding set (10 tasks), thinking off, 3 tries each (greedy + 2 seeded at temp 0.3). Qwen and Muse.
if [[ " $PARTS " == *" A "* ]]; then echo ">> part A coding, thinking off"
  for M in qwen3.8-27b muse-glimmer; do
    server sycl $M nothink -fa on -b 2048 -ub 2048 --reasoning-budget 0 || continue
    python3 p6tools.py coding --port $PORT --model $M --out "$OUT/A_coding.csv" --tries $([ "$DRY" = 1 ] && echo 1 || echo 3) $([ "$DRY" = 1 ] && echo --limit 2) || true
    stop; done; fi

# B: regenerate + edit. Build a 6-turn chat (~9K), then: regen (resend identical), edit turn 3, edit last user msg.
if [[ " $PARTS " == *" B "* ]]; then echo ">> part B regenerate/edit"
  for cfg in "gemma-4-31b-qat|sycl|ckpt-default|-fa on -b 2048 -ub 2048" "gemma-4-31b-qat|sycl|ckpt0|-fa on -b 2048 -ub 2048 --ctx-checkpoints 0" \
             "gemma-4-31b-qat|vulkan|ckpt-default|-fa off -b 2048 -ub 512" "gemma-4-31b-qat|vulkan|ckpt0|-fa off -b 2048 -ub 512 --ctx-checkpoints 0" \
             "qwen3.8-27b|sycl|ckpt-default|-fa on -b 2048 -ub 2048" "qwen3.8-27b|sycl|ckpt0|-fa on -b 2048 -ub 2048 --ctx-checkpoints 0" \
             "muse-glimmer|sycl|ckpt-default|-fa on -b 2048 -ub 2048" "muse-glimmer|sycl|ckpt0|-fa on -b 2048 -ub 2048 --ctx-checkpoints 0"; do
    IFS='|' read m be lab args <<< "$cfg"; [ "$be" = vulkan ] && [ -z "${B65_VK_INDEX:-}" ] && continue
    server $be $m $lab $args || continue
    python3 p6tools.py regen --port $PORT --label "$m,$be,$lab" --out "$OUT/B_regen.csv" --turns $([ "$DRY" = 1 ] && echo 2 || echo 6) || true
    stop; done; fi

# C: canary at ub 2048 against the Phase 5 baseline (llama-bench, SYCL fa1, Qwen + Muse, 5 reps)
if [[ " $PARTS " == *" C "* ]]; then echo ">> part C canary ub2048"; echo "model,test,tok_s" > "$OUT/C_canary.csv"
  for M in qwen3.8-27b muse-glimmer; do F=$(mfile $M); [ -n "$F" ] || continue
    for T in "pp512|-p 512 -n 0" "pp16384|-p 16384 -n 0" "tg128|-p 0 -n 128" "tg128@d16384|-p 0 -n 128 -d 16384"; do
      lab=${T%%|*}; a=${T#*|}; [ "$DRY" = 1 ] && [[ $lab == *16384* ]] && continue
      "$SYCL_BIN/llama-bench" -m "$F" -ngl 99 -fa 1 -r $REPS -b 2048 -ub 2048 $a -o jsonl > "$OUT/C.$M.$lab.jsonl" 2> "$OUT/C.$M.$lab.log" || { echo "$M,$lab,FAIL" >> "$OUT/C_canary.csv"; continue; }
      ts=$(python3 -c "import json,sys;print(round([json.loads(l) for l in open(sys.argv[1]) if l.startswith('{')][-1]['avg_ts'],2))" "$OUT/C.$M.$lab.jsonl")
      echo "$M,$lab,$ts" >> "$OUT/C_canary.csv"; echo "  $M $lab $ts"; done; done; fi

python3 p6tools.py summary "$OUT" > "$OUT/phase6_summary.md"; cat "$OUT/phase6_summary.md"; touch "$OUT/done"
echo "Done: $OUT  -> upload: tar czf $RUN_ID.tar.gz -C raw $RUN_ID"
