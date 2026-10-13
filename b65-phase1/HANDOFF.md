# Handoff: B65 benchmarks, Phase 1

You're the local agent on AJ's Omarchy machine running the Arc Pro B65 benchmarks in `~/Projects/b65-benchmarks`.
Phases 0 and 0.5 are done. Key result: **flash attention on Vulkan slows every model on this card, so everything now runs with flash attention off** (`-fa 0` / `-fa off`).

## Context
- GPU under test: Arc Pro B65 32 GB (PCI 8086:e222). The RTX 3080 drives the display and is NEVER benchmarked. Use the same `B65_VK_INDEX` as before.
- Software is pinned: llama.cpp build 11574 (`8bb3cf0d2`), Mesa 26.2.2, kernel 7.2.5-3-omarchy, Omarchy 4.0.4-1. Don't update anything. If something updates anyway, record it and rerun Qwen tg128 as a canary.
- Models (unchanged `models.conf`, all verified against Hugging Face):
  - Qwen 3.8 27B Q4_K_M, `lmstudio-community/Qwen3.8-27B-GGUF` at commit `5a7da681`
  - Gemma 4 31B QAT Q4_0, `lmstudio-community/gemma-4-31B-it-QAT-GGUF` at commit `12e5eae7`
  - Muse Glimmer 28B Q4_K_M, `lmstudio-community/Muse-Glimmer-30B-GGUF` at commit `c34cb737`
- Power is GPU board power from xe hwmon only. Never call it wall power.

## Steps
1. Copy `b65-phase1/` into the repo. Confirm `llama-server` is from the same build as `llama-bench` (`llama-server --version`).
2. Unload all models in LM Studio, then quit LM Studio so it isn't holding VRAM.
3. Dry run: `B65_VK_INDEX=<idx> DRY=1 ./phase1.sh`. It must find the Intel device, finish one tg128 test, start the server, and print one request line with a TTFT.
4. Full run: `B65_VK_INDEX=<idx> ./phase1.sh`. Don't use the GPU for anything else while it runs.

## Rules
- Write new runs to new `raw/p1-*` folders only. Never edit earlier raw data.
- An `oom` at 32k is a valid result (it means the model doesn't fit), not a failure. Don't retry it with lower settings.
- If the server fails to start for a model, keep `<model>.server.log`, continue with the next model, and report it.
- Retry a failed test once at most.
- If port 8099 is taken, set `PORT=` to something free.

## Report back (to AJ, who passes it to Forge)
Tar up `raw/p1-<timestamp>/` and send it along with the printed summary (also saved as `phase1_summary.md`).
Done when: every bench test shows ok or oom, `serve.csv` has 9 rows per model (3 prompt sizes × 3 reps), and `idle_loaded.csv` has a number for each model.
