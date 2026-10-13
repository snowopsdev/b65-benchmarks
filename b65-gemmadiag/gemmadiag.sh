#!/usr/bin/env bash
# Gemma SYCL server prefill diagnostic. Why does llama-server prefill Gemma at ~282 tok/s when llama-bench gets ~397?
# Usage: SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./gemmadiag.sh      DRY=1: first variant only, 1 request
set -euo pipefail
cd "$(dirname "$0")"
LS="${SYCL_BIN:?set SYCL_BIN}/llama-server"; LB="$SYCL_BIN/llama-bench"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
PORT="${PORT:-8099}"; DRY="${DRY:-0}"
RUN_ID="gd-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"
IFS='|' read -r NAME QUANT GLOB < <(grep -v '^#' models.conf | head -n1)
FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1)
[ -n "$FILE" ] || { echo "Gemma not found"; exit 1; }
ENERGY=""; for h in /sys/class/hwmon/hwmon*; do [ "$(cat $h/name 2>/dev/null)" = xe ] && for f in $h/energy*_input; do [ -r "$f" ] && { ENERGY=$f; break 2; }; done; done
{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "server=$("$LS" --version 2>&1 | grep -m1 version)"; echo "model=$FILE"; } > "$OUT/env.txt"

# 1) llama-bench reference: does micro-batch size alone explain it?
for UB in 512 2048; do
  "$LB" -m "$FILE" -ngl 99 -fa 1 -p 16384 -n 0 -ub $UB -b 2048 -r 3 -o jsonl > "$OUT/bench.ub$UB.jsonl" 2> "$OUT/bench.ub$UB.log" || echo "!! bench ub$UB failed"
  [ "$DRY" = 1 ] && break
done

# 2) server variants (label|flags)
VARIANTS=(
 "ckpt0|--ctx-checkpoints 0"
 "default|"
 "ckpt0_ub2048|--ctx-checkpoints 0 -b 2048 -ub 2048"
 "ckpt0_swafull_16k|--ctx-checkpoints 0 --swa-full"
 "ckpt0_ctx16k|--ctx-checkpoints 0"
)
for V in "${VARIANTS[@]}"; do
  LAB="${V%%|*}"; FL="${V#*|}"; CTX=32768; [[ "$LAB" == *16k ]] && CTX=17408
  echo "== $LAB (ctx $CTX) $FL"
  mkdir -p "$OUT/$LAB"
  "$LS" -m "$FILE" -ngl 99 -fa on -c $CTX $FL --port $PORT --host 127.0.0.1 -np 1 --no-webui > "$OUT/$LAB/server.log" 2>&1 &
  SP=$!; ok=0; for _ in $(seq 1 240); do curl -sf http://127.0.0.1:$PORT/health >/dev/null 2>&1 && { ok=1; break; }; sleep 1; done
  if [ $ok = 1 ]; then
    python3 serve_bench.py --port $PORT --model "gemma-$LAB" --out "$OUT/$LAB" --energy "$ENERGY" $( [ "$DRY" = 1 ] && echo --dry ) || echo "!! bench failed $LAB"
  else
    grep -iE "out of memory|failed to allocate" "$OUT/$LAB/server.log" && echo "$LAB: OOM" >> "$OUT/notes.txt" || echo "$LAB: server did not start" >> "$OUT/notes.txt"
  fi
  kill $SP 2>/dev/null; wait $SP 2>/dev/null || true; sleep 5
  [ "$DRY" = 1 ] && break
done
python3 - "$OUT" <<'PY'
import sys,glob,json,os,statistics as st
out=sys.argv[1]; L=["# Gemma SYCL diagnostic ("+os.path.basename(out)+")","","## llama-bench pp16384 (fa1)","","| ub | tok/s |","|---|---|"]
for p in sorted(glob.glob(out+"/bench.ub*.jsonl")):
    for line in open(p):
        try: d=json.loads(line); L.append(f"| {p.split('.ub')[1].split('.')[0]} | {d['avg_ts']:.1f} |")
        except Exception: pass
L+=["","## Server: see each variant's summary/CSV below",""]
for d in sorted(glob.glob(out+"/*/")):
    L.append("### "+os.path.basename(d.rstrip('/')))
    for f in sorted(glob.glob(d+"*.csv"))[:2]: L+=["```",open(f).read().strip(),"```"]
if os.path.exists(out+"/notes.txt"): L+=["","Notes:",open(out+"/notes.txt").read()]
open(out+"/gemmadiag_summary.md","w").write("\n".join(L)+"\n"); print("\n".join(L))
PY
echo "Done: $OUT"
