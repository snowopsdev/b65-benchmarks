#!/usr/bin/env bash
# Phase 5: new ub2048 baseline (A), Gemma short-prompt TTFT (B), multi-turn cache w/ checkpoints (C), Qwen runaway thinking (D)
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin [VK_BIN=~/src/llama.cpp/build-vulkan/bin B65_VK_INDEX=1] ./phase5.sh
#   PARTS="A B C D" (default all)   DRY=1 quick smoke test (1 rep, tiny sizes)
set -euo pipefail
cd "$(dirname "$0")"
: "${SYCL_BIN:?set SYCL_BIN}"; PARTS="${PARTS:-A B C D}"; DRY="${DRY:-0}"; REPS=5; [ "$DRY" = 1 ] && REPS=1
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
RUN_ID="p5-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; PORT=8099
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat $h/name 2>/dev/null)" = xe ] && for f in $h/energy*_input; do [ -r "$f" ] && { ENERGY=$f; break 2; }; done; done
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "mesa=$(pacman -Q mesa 2>/dev/null)"
  echo "oneapi=$(icpx --version 2>/dev/null | head -n1)"; echo "level_zero=$(pacman -Q level-zero-loader intel-compute-runtime 2>/dev/null | tr '\n' ' ')"
  echo "llama_sycl=$("$SYCL_BIN/llama-bench" --version 2>&1 | grep -m1 version)"; echo "vk_bin=${VK_BIN:-none} vk_index=${B65_VK_INDEX:-none}"
  echo "parts=$PARTS dry=$DRY reps=$REPS energy_file=${ENERGY:-none}"; } > "$OUT/env.txt"; cat "$OUT/env.txt"
mfile() { local g; g=$(grep "^$1|" models.conf | cut -d'|' -f3); find ~/.lmstudio ~/.cache/lm-studio -iname "$g" 2>/dev/null | grep -v mmproj | head -n1; }
ALL="qwen3.8-27b gemma-4-31b-qat muse-glimmer"
for M in $ALL; do F=$(mfile $M); [ -n "$F" ] && sha256sum "$F" >> "$OUT/models.sha256"; done

server() { # be model label args... ; starts server, waits for health
  local be=$1 m=$2 lab=$3; shift 3; local F; F=$(mfile $m); local bin="$SYCL_BIN/llama-server"; local envp=()
  if [ "$be" = vulkan ]; then bin="${VK_BIN}/llama-server"; envp=(env GGML_VK_VISIBLE_DEVICES=$B65_VK_INDEX ONEAPI_DEVICE_SELECTOR=); fi
  "${envp[@]}" "$bin" -m "$F" -ngl 99 -c 32768 --port $PORT --host 127.0.0.1 -np 1 --no-webui --jinja "$@" > "$OUT/$m.$be.$lab.server.log" 2>&1 &
  SPID=$!; for _ in $(seq 1 240); do curl -sf http://127.0.0.1:$PORT/health >/dev/null 2>&1 && return 0; sleep 1; done
  echo "!! server failed: $m $be $lab"; kill $SPID 2>/dev/null || true; return 1; }
stop() { kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; sleep 3; }

# A: new baseline at ub 2048 (SYCL fa1), all three models
if [[ " $PARTS " == *" A "* ]]; then echo "== A baseline ub2048"; echo "model,test,tok_s,board_w" > "$OUT/A_baseline.csv"
  for M in $ALL; do F=$(mfile $M); [ -n "$F" ] || { echo "!! $M missing"; continue; }
    for T in "pp512|-p 512 -n 0" "pp16384|-p 16384 -n 0" "tg128|-p 0 -n 128" "tg128@d16384|-p 0 -n 128 -d 16384"; do
      lab=${T%%|*}; args=${T#*|}; [ "$DRY" = 1 ] && [[ $lab == *16384* ]] && continue
      e0=""; [ -n "$ENERGY" ] && e0=$(cat $ENERGY); t0=$(date +%s.%N)
      "$SYCL_BIN/llama-bench" -m "$F" -ngl 99 -fa 1 -r $REPS -b 2048 -ub 2048 $args -o jsonl > "$OUT/A.$M.$lab.jsonl" 2> "$OUT/A.$M.$lab.log" || { echo "$M,$lab,FAIL," >> "$OUT/A_baseline.csv"; continue; }
      t1=$(date +%s.%N); w=""; [ -n "$e0" ] && w=$(echo "($(cat $ENERGY)-$e0)/1000000/($t1-$t0)" | bc -l | xargs printf %.1f)
      ts=$(python3 -c "import json,sys;print(round(json.loads(open(sys.argv[1]).readlines()[-1])['avg_ts'],2))" "$OUT/A.$M.$lab.jsonl")
      echo "$M,$lab,$ts,$w" >> "$OUT/A_baseline.csv"; echo "  $M $lab $ts tok/s ${w}W"; done; done
  python3 p5tools.py mkbaseline "$OUT/A_baseline.csv" "$OUT/baseline_ub2048.json"; fi

# B: Gemma short-prompt TTFT: ub 512 vs 2048 on SYCL, plus Vulkan ub 512 reference
if [[ " $PARTS " == *" B "* ]]; then echo "== B gemma short TTFT"
  for cfg in "sycl|ub512|-fa on -b 2048 -ub 512" "sycl|ub2048|-fa on -b 2048 -ub 2048" "sycl|ub2048-nowarm|-fa on -b 2048 -ub 2048 --no-warmup" "vulkan|ub512|-fa off -b 2048 -ub 512 --ctx-checkpoints 0"; do
    IFS='|' read be lab args <<< "$cfg"; [ "$be" = vulkan ] && { [ -z "${VK_BIN:-}" ] || [ -z "${B65_VK_INDEX:-}" ]; } && { echo "  skip vulkan (VK_BIN/B65_VK_INDEX unset)"; continue; }
    server $be gemma-4-31b-qat $lab $args || continue
    python3 p5tools.py ttft --port $PORT --label "gemma-4-31b-qat,$be,$lab" --out "$OUT/B_ttft.csv" --reps $REPS --sizes "${B_SIZES:-16 64 256 1024 4096}" $( [ "$DRY" = 1 ] && echo --dry ) || true
    stop; done; fi

# C: multi-turn chat, 8 turns growing to ~12k tokens, checkpoints default vs 0 (SYCL); Vulkan too if set
if [[ " $PARTS " == *" C "* ]]; then echo "== C multi-turn cache"
  for M in qwen3.8-27b muse-glimmer gemma-4-31b-qat; do
    for cfg in "sycl|ckpt-default|-fa on -b 2048 -ub 2048" "sycl|ckpt0|-fa on -b 2048 -ub 2048 --ctx-checkpoints 0" "vulkan|ckpt-default|-fa off -b 2048 -ub 512" "vulkan|ckpt0|-fa off -b 2048 -ub 512 --ctx-checkpoints 0"; do
      IFS='|' read be lab args <<< "$cfg"; [ "$be" = vulkan ] && { [ -z "${VK_BIN:-}" ] || [ -z "${B65_VK_INDEX:-}" ]; } && continue
      server $be $M $lab $args || continue
      python3 p5tools.py multiturn --port $PORT --label "$M,$be,$lab" --out "$OUT/C_multiturn.csv" --turns $([ "$DRY" = 1 ] && echo 2 || echo 8) || true
      stop; done; done; fi

# D: Qwen runaway thinking on c08: token budgets and sampler settings, 5 tries each
if [[ " $PARTS " == *" D "* ]]; then echo "== D qwen thinking"
  server sycl qwen3.8-27b think -fa on -b 2048 -ub 2048 || true
  python3 p5tools.py think --port $PORT --out "$OUT/D_think.csv" --tries $([ "$DRY" = 1 ] && echo 1 || echo 5) || true
  stop
  server sycl qwen3.8-27b nothink -fa on -b 2048 -ub 2048 --reasoning-budget 0 || true
  python3 p5tools.py think --port $PORT --out "$OUT/D_think.csv" --tries $([ "$DRY" = 1 ] && echo 1 || echo 5) --only nothink || true
  stop; fi

python3 p5tools.py summary "$OUT" > "$OUT/phase5_summary.md"; cat "$OUT/phase5_summary.md"
echo "Done: $OUT  -> upload: tar czf $RUN_ID.tar.gz -C raw $RUN_ID"
