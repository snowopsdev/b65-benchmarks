# Phase 6 kit: confirming the Phase 5 recipes (Forge kit, local changes)

Plan, parts A–C and how to read them: `HANDOFF.md`. Runs: `raw/p6-*` (smoke tests: `raw/p6-dry-*`). Live view: `/p6`. Share cards: the Phase 6 tab.

    SYCL_BIN=~/src/llama.cpp/build-sycl/bin B65_VK_INDEX=1 DRY=1 ./phase6.sh   # smoke test
    SYCL_BIN=~/src/llama.cpp/build-sycl/bin B65_VK_INDEX=1 ./phase6.sh         # full run (A B C)

## Local changes
- **`p6tools.py coding`:**
  - **System prompt:** sends Phase 3's coding system message ("Reply with only one ```python code block…", from `quality.py`). The kit sent the user prompt alone, so the scores wouldn't have been comparable with Phase 3.
  - **Failed requests:** a failed request is recorded as a fail instead of ending that model's run.
  - **Reasoning length:** records `reasoning_chars`, the length of the separate reasoning, so the CSV shows whether thinking was actually off. The dry run showed that Muse produced the same token counts as in Phase 3 with thinking on.
- **`p6tools.py regen`:** if no token arrives, the time to first token prints as −1 instead of crashing.
- **`phase6.sh`, Part C:**
  - A strict `gpu_info` check (the B65, never NVIDIA).
  - A malformed jsonl becomes a FAIL row instead of stopping the run under `set -e`.
- **`phase6.sh`, markers:** `>> coding <model>` and `>> bench <model> <test>` progress markers for the dashboard, and `done` holds a timestamp.
- **The canary:** Forge's `canary/` is kept as received. The routine canary stays `b65-phase4/canary.sh`, Phase 4's patched copy. That copy keeps the local fixes (awk, board W over the timed reps, card energy, precheck, strict `gpu_info`) and the run history, and the `/p4` page reads from it. It gets Forge's change:
  - **`UB` setting:** `UB` defaults to 2048 and compares with `b65-phase4/baseline_ub2048.json` (identical to the kit's). `UB=512` still compares with `baseline.json`.
  - **`compare4.py`:** Forge's new version, which picks the baseline by each row's ub. The micro-batch table only appears when there's something to compare.
  - **Bug fix:** the Vulkan micro-batch loop variable is renamed `VUB`. With `UB=512 UBCHECK=1`, it overwrote `UB`, so the second model's main rows would have run at 2048.
