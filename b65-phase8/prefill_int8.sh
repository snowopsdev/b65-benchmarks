#!/usr/bin/env bash
# Phase 8: TensorFold XPU prefill, fp16 (default) vs XPU_PREFILL_INT8=1 (W4A8 prompt GEMMs), same server otherwise.
# Each mode: the Phase 7 speed sweep and coding suite on a fresh server; decode kernels are the same in both.
set -u
cd "$(dirname "$0")"
OUT=results/prefill-$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"
PY=$HOME/.local/share/unsloth-xpu/bin/python; TOK=$HOME/models/tokenizers/Qwen3.8-27B/tokenizer.json
TF=$HOME/src/TensorFold/zig-out/xpu/bin/tensorfold-native; PORT=8081
run_mode() { local label=$1; shift
  env XPU_DEVICE_ID=e222 "$@" "$TF" serve "$HOME/models/Qwen3.8-27B-GPTQ-g128" --drafter "$HOME/models/Qwen3.8-27B-DFlash2" \
    --parallel 1 --context 81920 --host 127.0.0.1 --port $PORT --name qwen > "$OUT/$label.server.log" 2>&1 &
  local pid=$!
  for _ in $(seq 1 80); do curl -sf http://127.0.0.1:$PORT/v1/models >/dev/null && break; kill -0 $pid 2>/dev/null || { echo "!! $label server died"; tail -3 "$OUT/$label.server.log"; return 1; }; sleep 3; done
  grep -E 'streams of' "$OUT/$label.server.log"
  local c=(--base http://127.0.0.1:$PORT --model qwen --label "$label" --out "$OUT")
  "$PY" ../b65-phase7/oai_bench.py speed "${c[@]}" --tokenizer "$TOK" --sizes 512,4096,8192,16384,32768,65536 --reps 3 --gen 256
  "$PY" ../b65-phase7/oai_bench.py coding "${c[@]}" --tries 3
  kill $pid 2>/dev/null; wait $pid 2>/dev/null; sleep 15   # VRAM lingers after exit
}
run_mode fp16
run_mode int8 XPU_PREFILL_INT8=1
"$PY" ../b65-phase7/oai_bench.py summary --out "$OUT"
journalctl -k --since '-90min' --no-pager | grep -E 'xe 0000:06.*(Timedout|Engine reset|CAT)' || echo "no GPU resets logged"
echo "OUT=$OUT"
