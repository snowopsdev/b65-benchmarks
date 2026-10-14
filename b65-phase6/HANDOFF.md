# Phase 6 plan and handoff: confirming the Phase 5 recipes

**Goal:** Settle the two Phase 5 results that still rest on thin evidence, and move the canary to the ub 2048 baseline. Same machine and versions as Phase 5. The 3080 stays out of it.

## Run
```
tar xzf b65-phase6.tar.gz && cd b65-phase6
export SYCL_BIN=~/src/llama.cpp/build-sycl/bin B65_VK_INDEX=1   # VK_BIN defaults to ../vendor/llama.cpp/build/bin, as in Phase 5
DRY=1 ./phase6.sh     # ~5 min smoke test
./phase6.sh           # full run, ~45–60 min (Gemma Vulkan with checkpoints on is the slow row)
PARTS="A" ./phase6.sh # any subset
```
The header (precheck, card energy by label, `|| true` find guard, fast-fail server, pid/done markers) is copied from your agent's patched Phase 5 kit. `p5tools.py` and `quality.py` are included unchanged.

## Parts
- **A. Coding with thinking off (~10 min).** The full Phase 3 coding set (10 tasks), Qwen and Muse, `--reasoning-budget 0`, 4K cap. 3 tries each: greedy, then 2 seeded tries at temperature 0.3. Compare with Phase 3 (thinking on, 2K cap: Qwen 9/10, Muse 10/10).
- **B. Regenerate and edit (~30–40 min).** A 6-turn chat (~9.5K tokens), then 5 steps: resend identical (twice), edit the last user message, edit turn 3, and go back to the original chat. Tokens reprocessed and time to first token at each step. Gemma with checkpoints on vs off on SYCL and Vulkan; Qwen and Muse on SYCL.
- **C. Canary at ub 2048 (~10 min).** Qwen and Muse llama-bench at ub 2048, compared with `baseline_ub2048.json`.

## How to read it
- **A:** If Qwen with thinking off scores at least 9/10 on greedy and ≥ 27/30 overall, "thinking off for coding" becomes the Qwen recipe. If it drops below Phase 3, the recipe is "thinking on with a 16K cap", accepting minutes per answer.
- **B:** The expected cache reuse is: regen reprocesses a few tokens, edit-last about one turn (~1.5K), edit-early from turn 3 on (~6K), and back-to-original about one turn or less.
  - If **checkpoints off** shows the full context (~9.5K) on regen or edit-last for Gemma, while checkpoints on doesn't, then keep checkpoints on for Gemma in chat UIs. Use `--ctx-checkpoints 0` only for append-only agent loops.
  - If both match, `--ctx-checkpoints 0` becomes the default everywhere.
  - Qwen and Muse are the control.
- **C:** Every row should be within 5% (it should be within 0.1%). After that, use `canary/` as the routine canary.

## New canary (`canary/`)
- `canary.sh` now defaults to `UB=2048` and compares with `baseline_ub2048.json`. `UB=512 ./canary.sh` still compares with the old `baseline.json`.
- `compare4.py` picks the baseline by the ub of each row.
- **Note:** this is my Phase 4 `canary.sh` with the UB change only. Apply the same local fixes your agent made in Phase 4 and 5 (awk instead of bc, card energy by label, `|| true` find guard) or keep using its patched copy with the new `compare4.py` and `baseline_ub2048.json` dropped in.

## Upload
`tar czf p6-<id>.tar.gz -C raw p6-<id>`. The script prints the exact line.
