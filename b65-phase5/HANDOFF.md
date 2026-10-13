# Phase 5 plan and handoff: open questions from Phases 3–4

**Goal:** Close the four loose ends and lock in the new defaults. Same machine, same versions as Phase 4 (build 11574, Mesa 26.2.2, kernel 7.2.5-3-omarchy). The 3080 stays out of it.

## Run
```
tar xzf b65-phase5.tar.gz && cd b65-phase5
export SYCL_BIN=~/src/llama.cpp/build-sycl/bin
export VK_BIN=~/src/llama.cpp/build-vulkan/bin B65_VK_INDEX=1   # optional, enables Vulkan rows in B and C
DRY=1 ./phase5.sh          # 5-min smoke test first; check every part prints rows
./phase5.sh                # full run, roughly 2–2.5 h (part D is most of it)
PARTS="B C" ./phase5.sh    # any subset
```
Upload: `tar czf p5-<id>.tar.gz -C raw p5-<id>` (the script prints the exact line).

## Parts
- **A. New baseline (~25 min).** llama-bench, SYCL fa1, `-b 2048 -ub 2048`, all three models: pp512, pp16384, tg128, tg128 at 16k depth, 5 reps, board power. Writes `baseline_ub2048.json`, which replaces the Phase 2 ub 512 baseline for the canary.
- **B. Gemma short-prompt TTFT (~15 min).** Server, prompts of exactly 16/64/256/1024/4096 tokens, 5 reps, each cold and then with the identical prompt reused from the cache. Configs: SYCL ub 512, SYCL ub 2048, SYCL ub 2048 with `--no-warmup`, Vulkan ub 512 reference. Question: is the 2.8 s vs 1.4 s gap a fixed per-request cost (same at 16 and 256 tokens), a ub-size effect, or first-request warmup?
- **C. Multi-turn cache (~30 min).** 8-turn chat growing by about 1.5k tokens a turn to ~12k, thinking off. Each model with context checkpoints at default vs `--ctx-checkpoints 0`, on SYCL (and Vulkan if set). The key column is tokens reprocessed per turn: it should be about 1.5k if the cache is reused and the full context if it's being thrown away.
- **D. Qwen thinking loops on c08 (~60–90 min).** Five tries each: thinking with caps of 4k, 8k and 16k tokens, 8k with presence penalty 1.5, 8k with Qwen's recommended sampler (temp 0.6, top_p 0.95, top_k 20), and thinking off (`--reasoning-budget 0`). Reports pass rate, how often it hits the cap, tokens and time.

## How to read it
- **A:** It should land on the Phase 4 ub 2048 numbers (Qwen pp16384 ≈ 824, Muse ≈ 821) within 3%. If so, commit `baseline_ub2048.json` as the canary baseline.
- **B:** If the SYCL-vs-Vulkan gap is flat across sizes, it's a per-request overhead, so the note is "Vulkan for tiny prompts". If `--no-warmup` or ub 512 changes it, that's the fix.
- **C:** If checkpoints-off reprocesses the whole context on SYCL, keep checkpoints on (the default) for chat. If both configs reprocess about 1.5k per turn, the setting doesn't matter on SYCL and we drop it from the docs.
- **D:** The recommended Qwen recipe is whichever variant passes 5/5 in the fewest tokens. If nothing beats thinking off, the recipe is "thinking off for coding tasks".

## Not in this phase
Round 2 blind writing ranks (still waiting on AJ) and Phase 1.5 (still blocked on @0xSero).
