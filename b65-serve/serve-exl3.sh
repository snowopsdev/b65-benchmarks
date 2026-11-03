#!/usr/bin/env bash
# Serve Qwen3.8-27B (EXL3 4 bpw) from the B65 as an OpenAI-compatible API for coding agents (T3 Code via Pi or OpenCode).
# Engine: 0xSero's exl3xpu image with its own model config (256K context, fp8 KV, prefix caching, MTP k=3), plus tool calls.
# Runs in the foreground; b65-llm.service starts it. Listens on 127.0.0.1:$PORT; `tailscale serve` puts it on the tailnet.
set -euo pipefail
PORT="${PORT:-8100}"; NAME=b65-llm; B65_PCI=0000:06:00.0
IMG=ghcr.io/0xsero/exl3xpu@sha256:21412bdd7535e9c653eeb3d099dce3bc79a83d440def2cd9556111c79c870fa8
MODEL=$HOME/models/Qwen3.8-27B-exl3-4.00bpw
CARD=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-card); REND=$(readlink -f /dev/dri/by-path/pci-$B65_PCI-render)   # renderD128 is the 3080
# oneCCL opens every node listed in /dev/dri/by-path; give the container a by-path dir holding only the B65's links
BYPATH=${XDG_STATE_HOME:-$HOME/.local/state}/b65-llm/bypath; mkdir -p "$BYPATH"
ln -sfn "../$(basename "$CARD")" "$BYPATH/pci-$B65_PCI-card"; ln -sfn "../$(basename "$REND")" "$BYPATH/pci-$B65_PCI-render"
docker rm -f $NAME >/dev/null 2>&1 || true
exec docker run --rm --name $NAME --device "$CARD" --device "$REND" -v "$BYPATH:/dev/dri/by-path:ro" \
  --group-add "$(getent group render | cut -d: -f3)" --group-add "$(getent group video | cut -d: -f3)" --shm-size 32g \
  -p 127.0.0.1:$PORT:8000 -v "$MODEL:/models:ro" -e HF_HUB_OFFLINE=1 $IMG \
  models/qwen3.8-27b-exl3-4.00bpw --gpu 0 --port 8000 --model-path /models \
  --set served_model_name=qwen3.8-27b \
  --set vllm.gpu_memory_utilization=0.94 \
  --set vllm.enable_auto_tool_choice=true --set vllm.tool_call_parser=qwen3_coder --set vllm.reasoning_parser=qwen3
