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
