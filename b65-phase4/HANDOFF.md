# Phase 4 plan and handoff: canary and ongoing checks

**Goal:** Catch it when an update quietly changes performance. After any Mesa, kernel, oneAPI/Level Zero, llama.cpp or LM Studio runtime update, run a short canary and compare against our baseline: Phase 2, SYCL with flash attention on, ub 512, build 11574. Anything that drifts more than 5% gets flagged.

## Run
```
tar xzf b65-phase4.tar.gz && cd b65-phase4
export SYCL_BIN=~/src/llama.cpp/build-sycl/bin
UBCHECK=1 B65_VK_INDEX=1 ./canary.sh                          # first run: canary + the micro-batch check (~25 min)
./canary.sh                                                    # routine canary: Qwen + Muse, ~10 min
MODELS="qwen3.8-27b muse-glimmer gemma-4-31b-qat" ./canary.sh  # all three
```
The script records the kernel, Mesa, oneAPI, Level Zero, llama.cpp and Omarchy versions in `env.txt`, so each run shows exactly what changed.

## What it measures
- **Canary (SYCL, fa1, ub 512, 5 reps):** pp512, pp16384, tg128 and tg128 at 16k depth, plus GPU board power for each test.
- **The micro-batch check (`UBCHECK=1`):**
  - Qwen and Muse at pp4096 and pp16384 with ub 512 vs 2048, and decode at 16k depth with ub 2048. This answers whether they gain from ub 2048 the way Gemma did (+55% in llama-bench).
  - With `B65_VK_INDEX` set, Vulkan pp16384 at ub 512 vs 2048 too, so the SYCL vs Vulkan comparison stays fair.

## How to read it
- **ok:** the result is within 5% of baseline.
- **!! on one test:** rerun once. If it repeats, record which version changed (diff `env.txt` against the previous run) and send me both summaries.
- **!! across many tests:** most likely a driver or runtime regression. Pin back to the old version and report it upstream with both `env.txt` files.
- **Micro-batch check:** if ub 2048 gains more than 10% on pp16384 without costing more than 5% decode, it becomes that model's default. Update `baseline.json` after the decision.

## Ongoing
- Rerun the canary after every update. It's cheap: about 10 minutes.
- Results repo (public): commit `raw/p4-*` and `canary_summary.md` with each run. Charts and cards are regenerated from raw data and never edited by hand.
- After big driver jumps, rerun Phase 3 quality and requalify the registry recipes (Phase 1.5).
- Before trusting any new number, the energy counter has to be present (`energy_file` in env.txt) and the run has to report the Intel device.

## Upload
Upload `raw/p4-*` as one tarball.
