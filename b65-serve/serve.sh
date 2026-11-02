#!/usr/bin/env bash
# Serve Qwen3.8-27B from the B65 as an OpenAI-compatible API for coding agents (T3 Code via Pi or OpenCode).
# Engine: Intel llm-scaler vLLM 1.5 with Phase 7's single-user winner (A5: sym_int4, MTP k=5, graphs on; 74.2 tok/s on code),
# plus tool calls, the reasoning parser and prefix caching (off in the benchmark; agents resend their whole context every turn).
# Runs in the foreground; b65-llm.service starts it. Listens on 127.0.0.1:$PORT; `tailscale serve` puts it on the tailnet.
# The exl3xpu alternative (256K context, 51 tok/s) is serve-exl3.sh.
set -euo pipefail
PORT="${PORT:-8100}"; NAME=b65-llm; B65_PCI=0000:06:00.0
MTP_K="${MTP_K:-5}"; CTX="${CTX:-81920}"   # the KV cache holds ~86K tokens; k=3 for several users at once (197 vs 137 tok/s at 8 requests)
IMG=intel/llm-scaler-vllm:1.5
MODEL=$HOME/models/Qwen3.8-27B   # BF16; quantized to 4-bit on load (5-8 min)
HERE=$(dirname "$(readlink -f "$0")")
CARD=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-card); REND=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-render)   # renderD128 is the 3080
# oneCCL opens every node listed in /dev/dri/by-path; give the container a by-path dir holding only the B65's links
BYPATH=${XDG_STATE_HOME:-$HOME/.local/state}/b65-llm/bypath; mkdir -p "$BYPATH"
ln -sfn "../$(basename "$CARD")" "$BYPATH/pci-$B65_PCI-card"; ln -sfn "../$(basename "$REND")" "$BYPATH/pci-$B65_PCI-render"
docker rm -f $NAME >/dev/null 2>&1 || true
# sym_int4.py: two logger.info_once calls break torch.compile, so graph mode never loads without this patch (+46% decode)
exec docker run --rm --name $NAME --device "$CARD" --device "$REND" -v "$BYPATH:/dev/dri/by-path:ro" \
  --group-add "$(getent group render | cut -d: -f3)" --group-add "$(getent group video | cut -d: -f3)" --shm-size 32g \
  -p 127.0.0.1:$PORT:8000 -v "$MODEL:/llm/models/Qwen3.8-27B:ro" \
  -v "$HERE/sym_int4.py:/opt/venv/lib/python3.12/site-packages/vllm/model_executor/layers/quantization/sym_int4.py:ro" \
  -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_WORKER_MULTIPROC_METHOD=spawn -e HF_HUB_OFFLINE=1 \
  --entrypoint vllm $IMG serve /llm/models/Qwen3.8-27B --served-model-name qwen3.8-27b --host 0.0.0.0 --port 8000 \
  --dtype float16 --trust-remote-code --language-model-only --quantization sym_int4 \
  --gpu-memory-utilization 0.9 --max-model-len "$CTX" --max-num-seqs 8 \
  --speculative-config "{\"method\":\"qwen3_5_mtp\",\"num_speculative_tokens\":$MTP_K}" \
  --enable-prefix-caching --mamba-cache-mode align \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3
