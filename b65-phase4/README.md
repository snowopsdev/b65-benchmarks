# Phase 4 kit: canary (Forge kit, local changes)

Plan and how to read results: `HANDOFF.md`. Runs: `raw/p4-*` (smoke tests: `raw/p4-dry-*`). Live view: `/p4`. Share cards: Phase 4 tab.

    SYCL_BIN=~/src/llama.cpp/build-sycl/bin UBCHECK=1 B65_VK_INDEX=1 ./canary.sh   # first run (+ micro-batch check)
    SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./canary.sh                           # routine, after any update
    SYCL_BIN=~/src/llama.cpp/build-sycl/bin DRY=1 ./canary.sh                     # smoke test: first model, 1 rep

## Local changes to `canary.sh`
- **Watts with awk instead of `bc`.** `bc` isn't installed, and under `set -e` the failed watts line would have ended the script on its first test.
- **Board W over the timed reps only** (10 Hz trace plus stamped `--progress`, via `../powerwin.py`). This is the same method as the Phase 2 baseline. The whole-invocation average, which includes model load, is kept as `invocation_w`. In the dry run, pp512 read 176.8 W over the timed reps against 73.7 W invocation-average.
- **Energy** from the xe `card` channel, chosen by label.
- **Checks:**
  - A precheck that SYCL0 is the B65 with at least 28 GB VRAM free.
  - A strict per-test check that `gpu_info` names the B65 and never NVIDIA. The old check matched "intel" anywhere, on the first test only.
- **The Vulkan comparison** uses the pinned vendor build (`../vendor/llama.cpp/build/bin/llama-bench`), since there's no `llama-bench` on PATH here.
- **Run markers and records:**
  - `pid` and `done` markers and `>>` progress lines for the dashboard.
  - `env.txt` also records the device, reps, models, ubcheck and vk_index.
  - `DRY=1` smoke-test mode.

## Dry run (`raw/p4-dry-20261013-150059`, Qwen, 1 rep)
pp512, pp16384, tg128 and tg128@d16384 were all within 0.1% of the baseline. 0 flagged.

## First canary (`raw/p4-20261013-150339`)
- All 20 tests ran; 0 flagged (all within 0.1%).
- **Finalized by hand:** `canary.sh` was edited while running (the `vk_index` line), which broke its last lines after the tests were done. The summary and `done` were then written by hand; see `NOTE-finalized-by-hand.txt`.
- `compare4.py` now leaves tests without a baseline (pp4096) out of the drift table.
- `raw/p4-recheck-20261013-154203`: Muse Vulkan pp16384 at ub 2048 vs 512, rerun in a fresh process. It reproduced (272.0 vs 429.7 tok/s).

## Phase 6 update: the canary at ub 2048
- `./canary.sh` now runs its main rows at `UB=2048` (the SYCL default since Phase 4) and compares them with `baseline_ub2048.json`. That file comes from Phase 5 part A, run `p5-20261013-171039`. `UB=512 ./canary.sh` compares with the original `baseline.json`.
- `compare4.py` is Forge's Phase 6 version, which picks the baseline by each row's ub. Local change: the micro-batch table only appears when there's something to compare.
- Fix: the Vulkan loop in `UBCHECK` used `UB` as its loop variable, which overwrote the main ub for the next model. It's now `VUB`.
- The `/p4` page and its card follow the run's ub (`ub=` in env.txt; runs without it ran at 512).
