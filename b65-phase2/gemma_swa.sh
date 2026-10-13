#!/usr/bin/env bash
# Phase 2 step 0: Gemma llama-server rerun to test whether the 25 s TTFT is the SWA/checkpoint path.
# Variants: baseline (Phase 1 flags), --swa-full, --swa-full + --ctx-checkpoints 0 (if supported). Vulkan, fa off, 32k ctx.
set -euo pipefail
cd "$(dirname "$0")"
LS="${LLAMA_SERVER:-llama-server}"; PORT="${PORT:-8099}"
[ -n "${B65_VK_INDEX:-}" ] || { echo "Set B65_VK_INDEX"; exit 1; }
export GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX"
OUT="raw/p2swa-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$OUT"
FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname '*gemma-4-31b*Q4_0*.gguf' | grep -v mmproj | head -n1)
ENERGY=$(for h in /sys/class/hwmon/hwmon*; do [ "$(cat $h/name)" = xe ] && ls $h/energy*_input 2>/dev/null | head -n1; done | head -n1)
{ echo "date=$(date -Iseconds)"; echo "llama_server=$("$LS" --version 2>&1 | grep -m1 version)"; } > "$OUT/env.txt"
VARIANTS=( "baseline|" "swa_full|--swa-full" )
"$LS" --help 2>&1 | grep -q -- "--ctx-checkpoints" && VARIANTS+=( "swa_full_nockpt|--swa-full --ctx-checkpoints 0" "nockpt|--ctx-checkpoints 0" )
for V in "${VARIANTS[@]}"; do
  NAME="${V%%|*}"; EXTRA="${V#*|}"; echo ">> gemma $NAME ($EXTRA)"
  # shellcheck disable=SC2086
  "$LS" -m "$FILE" -ngl 99 -fa off -c 32768 --port "$PORT" --host 127.0.0.1 -np 1 --no-webui $EXTRA > "$OUT/gemma.$NAME.server.log" 2>&1 &
  SPID=$!; ok=0
  for _ in $(seq 1 180); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && { ok=1; break; }; sleep 1; done
  if [ $ok = 1 ]; then sleep 5; python3 serve_bench.py --port "$PORT" --model "gemma-$NAME" --out "$OUT" --energy "$ENERGY" || echo "!! bench failed"
  else echo "!! server failed ($NAME), see log"; fi
  kill $SPID 2>/dev/null || true; wait $SPID 2>/dev/null || true
done
python3 - "$OUT" <<'PY'
import csv,sys,statistics as s,os
rows=list(csv.DictReader(open(os.path.join(sys.argv[1],"serve.csv")))); g={}
for r in rows: g.setdefault((r["model"],r["prompt_tokens"]),[]).append(float(r["ttft_s"]))
print("variant | prompt tokens | median TTFT s")
for (m,n),v in sorted(g.items()): print(f"{m} | {n} | {s.median(v):.2f}")
PY
echo "Done: $OUT"
