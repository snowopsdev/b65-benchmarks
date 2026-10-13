# Phase 5 kit: open questions from Phases 3–4 (Forge kit, local changes)

Plan, parts A–D and how to read them: `HANDOFF.md`. Runs: `raw/p5-*` (smoke tests: `raw/p5-dry-*`). Live view: `/p5`. Share cards: the Phase 5 tab.

    SYCL_BIN=~/src/llama.cpp/build-sycl/bin B65_VK_INDEX=1 DRY=1 ./phase5.sh   # smoke test
    SYCL_BIN=~/src/llama.cpp/build-sycl/bin B65_VK_INDEX=1 ./phase5.sh         # full run (A B C D)

## Local changes to `phase5.sh`
- **`mfile()` gets `|| true`.** `find` over the missing `~/.cache/lm-studio` fails under `pipefail`, which aborted the script at the first model lookup, before Part A.
- **Part A:**
  - awk instead of `bc`, which isn't installed.
  - Board W over the timed reps (10 Hz trace plus stamped `--progress`, via `../powerwin.py`). The old version averaged over the whole invocation, including model load. Every earlier baseline uses timed reps, so `baseline_ub2048.json` stays comparable.
  - A strict `gpu_info` check per test.
- **Energy** from the xe `card` channel, chosen by label.
- **Precheck:** SYCL0 must be the B65, with at least 28 GB VRAM free.
- **`VK_BIN`** defaults to the pinned vendor Vulkan build (`../vendor/llama.cpp/build/bin`); `~/src/llama.cpp/build-vulkan` doesn't exist here.
- **`server()`** fails fast if llama-server exits during load (OOM etc.), instead of waiting out the full 240 s.
- **Run markers:** `pid` and `done`, and `>>` progress lines for the dashboard. Dry runs go to `raw/p5-dry-*`.

## Timing note
Part D's estimate (60–90 min) assumes Qwen mostly stops early. In Phase 3 it ran 8,192 tokens without finishing (372 s at ub 512). If the 16K-cap variant hits its cap on all 5 tries, that variant alone is about an hour, so the full run could be 3–4 h.
