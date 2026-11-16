#!/usr/bin/env bash
# Phase 9 part S: llama-server b11574 vs v1.0.0 on Qwen3.8-27B Q4_K_M through the Phase 7 client (b65-phase7/oai_bench.py),
# so the numbers sit next to Phase 7's A0 / A0m3 / A5 rows. llama.cpp only (no docker).
# Parts (prefix O = b11574 ~/src/llama.cpp/build-sycl, N = v1.0.0 ~/src/llama.cpp-1.0.0/build-sycl):
#   xA0    recipe flags, no speculative decoding: speed + conc + coding
#   xA0m3  + llama.cpp's own MTP (draft-mtp, 3 tokens): speed + conc + coding
#   xA0mkN the same with N draft tokens, coding only
# Usage: ./serve.sh  PARTS="OA0mk3 NA0 NA0m3 NA0mk2 NA0mk4 NA0mk5"  DRY=1
set -euo pipefail
cd "$(dirname "$0")"
P7="$(cd ../b65-phase7 && pwd)"
OLD_SYCL="${OLD_SYCL:-$HOME/src/llama.cpp/build-sycl/bin}"; NEW_SYCL="${NEW_SYCL:-$HOME/src/llama.cpp-1.0.0/build-sycl/bin}"
PARTS="${PARTS:-OA0mk3 NA0 NA0m3 NA0mk2 NA0mk4 NA0mk5}"; DRY="${DRY:-0}"
PY="${PY:-$HOME/.local/share/unsloth-xpu/bin/python}"      # has `tokenizers`; the client itself is stdlib only
PORT=18080
GGUF=$(find ~/.lmstudio/models -iname 'Qwen3.8-27B-Q4_K_M.gguf' | head -n1)
TOK=$HOME/models/tokenizers/Qwen3.8-27B/tokenizer.json
if [ "$DRY" = 1 ]; then SIZES=512,4096; REPS=1; GEN=64; LEVELS=1,2; TRIES=1; LIMIT=2
else SIZES=512,4096,16384,32768; REPS=3; GEN=256; LEVELS=1,2,4,8; TRIES=3; LIMIT=0; fi
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
DEVS=$("$NEW_SYCL/llama-bench" --list-devices 2>&1)
echo "$DEVS" | grep -qiE "SYCL0.*(B65|BMG|Arc|e222)" || { echo "!! SYCL0 is not the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1); [ "${FREE:-0}" -ge 28000 ] || { echo "!! only ${FREE:-?} MiB free on the B65"; exit 2; }
RUN_ID="p9s-$( [ "$DRY" = 1 ] && echo dry- )$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"; echo $$ > "$OUT/pid"
LOG="$PWD/$( [ "$DRY" = 1 ] && echo p9s-dry.log || echo p9s-run.log )"; exec > >(tee -a "$LOG") 2>&1
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat "$h/name" 2>/dev/null)" = xe ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done; done
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "level_zero=$(pacman -Q level-zero-loader intel-compute-runtime 2>/dev/null | tr '\n' ' ')"
  echo "old_sycl=$("$OLD_SYCL/llama-bench" --version 2>&1 | grep -m1 '^version:')"; echo "new_sycl=$("$NEW_SYCL/llama-bench" --version 2>&1 | grep -m1 '^version:')"
  echo "sycl_device=$(echo "$DEVS" | grep -m1 SYCL0)"; echo "gguf=$GGUF"; echo "parts_list=$PARTS"
  echo "sizes=$SIZES reps=$REPS gen=$GEN levels=$LEVELS tries=$TRIES limit=$LIMIT"
  echo "dry=$DRY energy_file=${ENERGY:-none}"; echo "kit_commit=$(git rev-parse HEAD)"; } > "$OUT/env.txt"; cat "$OUT/env.txt"
sha256sum "$GGUF" > "$OUT/models.sha256" &
echo "part,label,build,status,load_s,args" > "$OUT/engines.csv"
for P in $PARTS; do echo "$P"; done > "$OUT/plan.txt"

SPID=""; VWPID=""
cleanup() { for p in $SPID $VWPID; do kill $p 2>/dev/null || true; done; }
trap cleanup EXIT
VRAM_AWK='/^pos:/{xe=0;id=""} /^drm-driver:/{xe=($2=="xe")} /^drm-client-id:/{id=$2}
  /^drm-resident-vram0:/{if(xe && !(id in seen)){seen[id]=1;v=$2;u=$3;tot+=(u=="MiB")?v*1024:(u=="GiB")?v*1048576:(u=="KiB")?v:v/1024}} END{printf "%d",tot/1024}'
echo "t,part,b65_vram_mib" > "$OUT/vram.csv"
vram_watch() { local part=$1; while :; do local v=""
    [ -s "$OUT/.spid" ] && v=$(cat /proc/$(<"$OUT/.spid")/fdinfo/* 2>/dev/null | awk "$VRAM_AWK")
    [ -n "$v" ] && echo "$(date +%s),$part,$v" >> "$OUT/vram.csv"; sleep 1; done; }
current() { echo "$1|$2|$(date +%s)" > "$OUT/current"; echo ">> step $1 $2"; }
healthy() { curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; }
start_llama() { local P=$1 bin=$2; shift 2
  "$bin/llama-server" -m "$GGUF" --port $PORT --host 127.0.0.1 --no-webui --jinja --alias qwen "$@" > "$OUT/$P.server.log" 2>&1 &
  SPID=$!; echo $SPID > "$OUT/.spid"; for _ in $(seq 1 300); do healthy && return 0; kill -0 $SPID 2>/dev/null || break; sleep 1; done
  kill $SPID 2>/dev/null || true; SPID=""; return 1; }
stop_llama() { [ -n "$SPID" ] && { kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true; }; SPID=""; rm -f "$OUT/.spid"; sleep 3; }

BASE="-ngl 99 -fa on -b 2048 -ub 2048 -c 65536 -np 8 -kvu"   # Phase 7 A0 recipe
for P in $PARTS; do
  case $P in O*) BU=b11574; BIN=$OLD_SYCL ;; N*) BU=v1.0.0; BIN=$NEW_SYCL ;; *) echo "!! unknown part $P"; continue ;; esac
  R=${P#?}; CODING_ONLY=0
  case $R in
    A0) ARGS="$BASE"; LAB="$P llama.cpp $BU SYCL Q4_K_M" ;;
    A0m[2-9]) k=${R#A0m}; ARGS="$BASE --spec-type draft-mtp --spec-draft-n-max $k"; LAB="$P llama.cpp $BU SYCL Q4_K_M + MTP k=$k" ;;
    A0mk[2-9]) k=${R#A0mk}; CODING_ONLY=1; ARGS="$BASE --spec-type draft-mtp --spec-draft-n-max $k"; LAB="$P llama.cpp $BU SYCL Q4_K_M + MTP k=$k" ;;
    *) echo "!! unknown part $P"; continue ;;
  esac
  echo ">> part $P ($LAB): $ARGS"; current $P loading; vram_watch $P & VWPID=$!; t0=$(date +%s)
  # shellcheck disable=SC2086
  if start_llama $P "$BIN" $ARGS; then
    dt=$(( $(date +%s) - t0 )); echo "$P,$LAB,$BU,ok,$dt,\"$ARGS\"" >> "$OUT/engines.csv"; echo ">> $P up in ${dt}s"
    c=(--base "http://127.0.0.1:$PORT" --model qwen --label "$LAB" --out "$OUT")
    if [ $CODING_ONLY = 0 ]; then
      current $P speed; "$PY" "$P7/oai_bench.py" speed "${c[@]}" --tokenizer "$TOK" --energy "$ENERGY" --sizes "$SIZES" --reps $REPS --gen $GEN || echo "!! $P speed failed"
      current $P conc;  "$PY" "$P7/oai_bench.py" conc "${c[@]}" --tokenizer "$TOK" --energy "$ENERGY" --levels $LEVELS --reps $REPS --gen $GEN || echo "!! $P conc failed"
    fi
    current $P coding; "$PY" "$P7/oai_bench.py" coding "${c[@]}" --tries $TRIES --limit $LIMIT || echo "!! $P coding failed"
  else
    dt=$(( $(date +%s) - t0 )); echo "$P,$LAB,$BU,fail,$dt,\"$ARGS\"" >> "$OUT/engines.csv"; echo "!! $P failed to load"; tail -n 8 "$OUT/$P.server.log" | sed 's/^/   /' || true
  fi
  stop_llama; kill $VWPID 2>/dev/null || true; VWPID=""
done
wait
"$PY" "$P7/oai_bench.py" summary --out "$OUT" > /dev/null || true
rm -f "$OUT/current"; date -Iseconds > "$OUT/done"; echo ">> done $RUN_ID"
