# Phase 0.5: flash-attention sweep + provenance

```
B65_VK_INDEX=<idx> DRY=1 ./phase05.sh   # ~2 min sanity check
B65_VK_INDEX=<idx> ./phase05.sh         # full sweep
```
Per model: flash attention 0 and 1 × pp512, pp4096, pp16384, tg128@d16384, 5 reps.
Gemma fa=1 pp16384 is skipped by default (already measured in Phase 0, 43 min); set SKIP_SLOW=0 to redo it.
Expect roughly 1.5–2.5 h total depending on how slow fa=0 is at 16k.

Outputs in `raw/p05-<timestamp>/`: jsonl+log per test, energy.csv, env.txt, models.sha256,
`provenance.csv` (HF repo, commit, sha256 match), `fa_sweep.csv` (tok/s, board W, tok/J for prefill and decode).
The terminal prints a fa=0 vs fa=1 table with the faster setting per model/test.

## Local changes (desktop-omarchy, before the first run)
- `bc` isn't installed: arithmetic uses awk (`calc`), otherwise `set -e` would stop the script at the first energy reading.
- `board_w` / `tok_per_j` now cover only the timed reps (10 Hz energy trace + time-stamped `--progress` lines, via the
  repo's `powerwin.py`), the same method as Phase 0. The original whole-invocation average is kept as `invocation_w`.
- Device check runs on every test and requires the BMG device in `gpu_info`; it also checks for >= 28 GB free VRAM and
  picks the xe `card` energy channel by label. `LLAMA_BENCH` defaults to the repo's pinned build.
- Writes `pid` and `done` markers in the run folder. Removed the shipped `__pycache__/`.
- Follow-up runs: `RUN_PREFIX`, `TESTS_SPEC` ("label|args;label|args") and `FA_LIST` override the run-folder prefix,
  test list and flash-attention settings without touching the defaults.
