#!/usr/bin/env bash
# Serve Qwen3.8-27B from the B65 as an OpenAI-compatible API for coding agents (Pi / OpenCode provider "b65").
# Engine: llama.cpp 1.0.0 (b12359) SYCL llama-server, Q4_K_M + its own MTP draft layer, k=5: Phase 9's winner on code
# (78.4 tok/s, 30/30; vLLM A5 74.2 in Phase 7). Same port and model id as the vLLM setup, so clients only see a context change.
# Runs in the foreground; b65-llm.service starts it. Listens on 127.0.0.1:$PORT; `tailscale serve` puts it on the tailnet.
# The vLLM setup is serve-vllm.sh, exl3xpu is serve-exl3.sh (point b65-llm.service's ExecStart at either to switch back).
set -euo pipefail
PORT="${PORT:-8100}"; MTP_K="${MTP_K:-5}"; CTX="${CTX:-131072}"; NP="${NP:-2}"
BIN="${BIN:-$HOME/src/llama.cpp-1.0.0/build-sycl/bin}"
GGUF="${GGUF:-$HOME/.lmstudio/models/lmstudio-community/Qwen3.8-27B-GGUF/Qwen3.8-27B-Q4_K_M.gguf}"
set +u; source /opt/intel/oneapi/setvars.sh --force >/dev/null; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1 ZES_ENABLE_SYSMAN=1
# -np 2 -kvu: two slots sharing one CTX-sized KV pool, so a side request (titles, compaction) doesn't queue behind a long turn.
# Sampling = the model's generation_config.json (what vLLM applied by default); clients may still override per request.
# Reasoning comes back as reasoning_content (--reasoning-format deepseek); thinking on/off via chat_template_kwargs.enable_thinking.
exec "$BIN/llama-server" -m "$GGUF" --alias qwen3.8-27b --host 127.0.0.1 --port "$PORT" --no-webui --jinja \
  -ngl 99 -fa on -b 2048 -ub 2048 -c "$CTX" -np "$NP" -kvu \
  --spec-type draft-mtp --spec-draft-n-max "$MTP_K" \
  --temp 1.0 --top-k 20 --top-p 0.95 --min-p 0 \
  --reasoning-format deepseek --metrics
