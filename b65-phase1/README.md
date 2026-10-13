# Phase 1: decode cleanup, context table, serving TTFT, loaded idle power

Flash attention is OFF for every test (Phase 0.5 showed it slows all three models on this card).

```
B65_VK_INDEX=<idx> DRY=1 ./phase1.sh   # ~5 min: one model, tg128 + one 512-token server request
B65_VK_INDEX=<idx> ./phase1.sh         # full run, roughly 1.5–2.5 h
```
Needs `llama-bench` and `llama-server` from the SAME llama.cpp build (11574), plus curl, bc, python3.

Per model:
- llama-bench decode at depth 0, 4k, 8k, 16k, 32k (5 reps). The 0 and 4k rows replace Phase 0's fa=1 decode numbers. A failed allocation is logged as `oom` = doesn't fit.
- llama-server at 32k context: 30 s loaded idle power, then streamed requests at 512 / 4k / 16k prompt tokens, 128 generated, 3 reps each, prompt cache off.

Outputs in `raw/p1-<timestamp>/`: jsonl/log per bench test, `serve.csv`, `idle_loaded.csv`, `energy.csv`, `env.txt`, `models.sha256`, server logs, and `phase1_summary.md`.

## Local changes (desktop-omarchy, before the first run)
- `llama-server` built from the same pinned commit as `llama-bench` (b11574, 8bb3cf0d2); both default to the repo's build.
- `bc` isn't installed: arithmetic uses awk, otherwise `idle_loaded.csv` power would be blank.
- `vram_used_mib` came from `mem_info_vram_used`, which only exists on AMD's driver; it now reads the server process's
  resident VRAM from the xe DRM fdinfo (`drm-resident-vram0`).
- Decode tests record a 10 Hz energy trace + time-stamped `--progress`, and the summary adds board W over the timed reps
  (same method as Phase 0/0.5). Device check on every test (BMG in gpu_info), >= 28 GB free VRAM precheck, xe `card`
  energy channel picked by label. `pid` and `done` markers in the run folder.
- summarize1.py: `rsplit` for the jsonl names (`qwen3.8-27b.tg128.jsonl` split on the first dot gave model `qwen3`).
- Removed the shipped `__pycache__/`.
