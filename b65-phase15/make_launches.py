#!/usr/bin/env python3
"""Write the B65 llama.cpp SYCL launches into a local-ai-registry clone (registry/launches/), one per model.
Same official image as the registry's B390 SYCL recipe (server-intel b11515); flags = findings/recommended-settings.md.
Usage: make_launches.py <registry clone> [model ...]"""
import json, os, sys

IMAGE = "ghcr.io/ggml-org/llama.cpp@sha256:86b37d266ce85b485127adea68c9dc6d04d0ec9a64b0979844d5bbd8d66c53c5"  # server-intel-b11515
CARD, CTX = "intel-arc-pro-b65-32gb", 32768
# weights pinned to the Hugging Face commits whose files match our local sha256 byte for byte (checked 2026-10-14)
MODELS = {
    "qwen3.8-27b": dict(repo="lmstudio-community/Qwen3.8-27B-GGUF", rev="5a7da681f60570ab5b439a587e912d2e5eddb582",
                        file="Qwen3.8-27B-Q4_K_M.gguf", bytes=16810714336, name="Qwen3.8-27B", family="qwen", quant="Q4_K_M",
                        served="Qwen3.8-27B-GGUF", short="qwen38-27b-q4km"),
    "gemma-4-31b": dict(repo="lmstudio-community/gemma-4-31B-it-QAT-GGUF", rev="12e5eae7a583b0a8bac91919fa99ae1fb27e6de4",
                        file="gemma-4-31B-it-QAT-Q4_0.gguf", bytes=17651001280, name="Gemma 4 31B", family="gemma", quant="QAT Q4_0",
                        served="gemma-4-31B-it-QAT-GGUF", short="gemma4-31b-qat-q40"),
    "muse-glimmer-30b": dict(repo="lmstudio-community/Muse-Glimmer-30B-GGUF", rev="c34cb7372a72fd3bec29e3a21e6c8e04e337d5ae",
                             file="Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf", bytes=16756683904, name="Muse Glimmer 30B", family="muse",
                             quant="Q4_K_M", served="Muse-Glimmer-30B-GGUF", short="muse-glimmer-30b-q4km"),
}

def launch_id(model):
    m = MODELS[model]
    return f"llama.cpp-sycl-{model}-{m['quant'].lower().replace(' ', '-').replace('_', '-')}-{CTX // 1024}k-arc-pro-b65"

def launch(model):
    m = MODELS[model]; gb = round(m["bytes"] / 1e9, 2)
    return {
        "id": launch_id(model), "engine": "llama.cpp",
        "about": f"{m['name']} (GGUF · {m['quant']}) on SYCL (official server-intel image, b11515), Intel Arc Pro B65 32 GB: "
                 "flash attention on, batch and micro-batch 2048, all layers on the GPU",
        "image": IMAGE, "backend": "intel-xpu", "port": 8080, "entrypoint": None,
        "args": ["-m", f"/models/{m['file']}", "--alias", m["served"], "--host", "0.0.0.0", "--port", "8080",
                 "--ctx-size", str(CTX), "--n-gpu-layers", "999", "--parallel", "1", "--flash-attn", "on",
                 "--batch-size", "2048", "--ubatch-size", "2048", "--jinja", "--reasoning-format", "deepseek",
                 "--no-mmproj", "--metrics"],
        "env": {"ONEAPI_DEVICE_SELECTOR": "level_zero:0", "UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS": "1"},
        "shm": "8g",
        "weights": [{"repo": m["repo"], "revision": m["rev"], "at": "/models", "layout": "dir", "files": m["file"]}],
        "config": None, "ctx": CTX, "seqs": 1, "vision": False, "cards": 1,
        "plugin": {"name": m["name"], "family": m["family"], "format": f"GGUF · {m['quant']}", "engine": "llama.cpp",
                   "servedName": m["served"], "sizeGb": gb, "minDriver": "", "scratch": None,
                   "capabilities": {"chat": True, "reasoning": True, "tools": True, "video": False, "vision": False},
                   "serving": {"ctxTokens": CTX, "kvTokens": 0},
                   "weights": [{"dir": "", "files": m["file"], "layout": "dir", "mountPath": "/models", "sizeGb": gb}], "asset": None},
        "ids": {CARD: f"{m['short']}-arcprob65-llamacpp-sycl"},
    }

if __name__ == "__main__":
    reg, models = sys.argv[1], sys.argv[2:] or list(MODELS)
    for mo in models:
        p = os.path.join(reg, "registry", "launches", launch_id(mo) + ".json")
        with open(p, "w") as f:
            json.dump(launch(mo), f, indent=2, ensure_ascii=False); f.write("\n")
        print(p)
