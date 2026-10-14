# Arc Pro B65: Phase 5 findings (open questions from Phases 3–4)

Run `p5-20261013-171039`, 2026-10-13, 5:10–7:51 PM ET (2 h 41 min). All four parts completed with no errors. Package: `b65-phase5-p5-20261013-171039.tar.gz`.

- **Versions:** unchanged since Phase 2. Kernel 7.2.5-3-omarchy, Mesa 26.2.2, oneAPI DPC++ 2026.0, compute-runtime 26.31.39395.13, llama.cpp 11574 (`8bb3cf0d2`).
- **Builds:** SYCL `level_zero:0`, and the pinned vendor Vulkan build with `GGML_VK_VISIBLE_DEVICES=1`.
- **Kit:** Forge's, with the local fixes listed in `b65-phase5/README.md`.
- **Dry run:** `raw/p5-dry-20261013-162644` (1 rep or try, 2 turns). It isn't used below; see "Corrections" for what it got wrong.

## A. New canary baseline (SYCL, flash attention on, `-b 2048 -ub 2048`, llama-bench, 5 reps)

| Model | Prefill 512 | Prefill 16K | Decode @ 0 | Decode @ 16K |
|---|---|---|---|---|
| Qwen 3.8 27B | 639.98 (183 W) | 824.33 (196 W) | 23.69 (196 W) | 18.86 (181 W) |
| Gemma 4 31B QAT | 410.85 (169 W) | 616.92 (188 W) | 22.45 (177 W) | 18.06 (172 W) |
| Muse Glimmer 28B | 690.81 (186 W) | 820.67 (193 W) | 25.64 (200 W) | 23.44 (194 W) |

tok/s, with board W averaged over the timed reps.

**It reproduces earlier runs:**
- **Phase 4 at ub 2048:** Qwen 824.18 / 18.86 and Muse 820.69 / 23.44.
- **Gemma diagnostic:** Gemma pp16384 at 617.1.
- **The ub 512 baseline:** prefill 512 is unchanged, since a 512-token prompt fits in one micro-batch either way.

Every comparable number is within 0.03%, well inside Forge's 3% rule.

**Per the handoff, `baseline_ub2048.json` is now committed as the ub 2048 canary baseline** (`b65-phase4/baseline_ub2048.json`, the same format as `baseline.json`). `canary.sh` still compares its ub 512 rows to `baseline.json`. Comparing its ub 2048 rows to the new file needs a small `compare4.py` change, which is left for Forge's next kit.

## B. Gemma on short prompts: time to first token

Gemma 4 31B on llama-server, `--ctx-checkpoints 0`. Median of 5. "Cold" means the cache was off; "warm" means the identical prompt was sent again.

| Prompt | SYCL ub 512 | SYCL ub 2048 | SYCL ub 2048 `--no-warmup` | Vulkan ub 512 (FA off) | SYCL minus Vulkan |
|---|---|---|---|---|---|
| 16 tokens | 1.09 s | 1.09 s | 1.09 s | 0.72 s | +0.37 s |
| 64 | 1.13 s | 1.13 s | 1.13 s | 0.54 s | +0.60 s |
| 256 | 1.38 s | 1.38 s | 1.38 s | 1.08 s | +0.30 s |
| 1,024 | 3.79 s | **2.46 s** | 2.46 s | 2.65 s | −0.19 s |
| 4,096 | 14.54 s | **7.72 s** | 7.72 s | 11.05 s | −3.34 s |

1. **SYCL has a floor of about 1.1 s per request for Gemma, even for 16 tokens.** Vulkan answers tiny prompts 0.3–0.6 s sooner.
   - From 1,024 tokens up, SYCL at ub 2048 is faster, and at 4,096 tokens it's 3.3 s faster.
   - Under Forge's reading rule this is a per-request overhead, so the note is "Vulkan for tiny Gemma prompts". In practice the gap is under 0.6 s.
2. **Neither micro-batch size nor warm-up is the cause.**
   - ub 512, ub 2048 and `--no-warmup` give the same time, to the millisecond, up to 256 tokens. A prompt that small fits in one micro-batch either way.
   - ub 2048 only helps from 1,024 tokens up: 3.79 → 2.46 s, and 14.5 → 7.7 s at 4,096.
3. **Only the first request after a server starts is slower:** about 1.52 s at 16 tokens on all three SYCL configs (`--no-warmup` included), then 1.09 s from the second request on. The medians include that first request; with 5 reps it doesn't move the median.
4. **Warm cache (identical prompt resent):**
   - **SYCL:** it reuses the cache at every size (0.11–0.65 s; only 1–5 tokens reprocessed).
   - **Vulkan (`--ctx-checkpoints 0`):** it reprocesses the whole prompt at 16–1,024 tokens (warm = cold), and only reuses the cache at 4,096 tokens (0.07 s). The kit doesn't show why.

## C. Multi-turn chat: cache reuse and context checkpoints

An 8-turn chat adds about 1.5K tokens per turn, reaching about 12.5K tokens. The table gives the median time to first token for turns 2–8.
- **SYCL:** ub 2048, flash attention on.
- **Vulkan:** ub 512, flash attention off.
- SYCL vs Vulkan isn't a same-micro-batch comparison here; checkpoints on vs off is.

| Model | Engine | Checkpoints on (default) | Checkpoints off (`--ctx-checkpoints 0`) | Tokens reprocessed per turn |
|---|---|---|---|---|
| Qwen 3.8 27B | SYCL | 2.38 s | **2.00 s** | 1,533 both |
| | Vulkan | 4.34 s | **3.92 s** | 1,533 both |
| Gemma 4 31B QAT | SYCL | 5.96 s (5.3–10.3) | **3.24 s** | ~1,570 both |
| | Vulkan | **124.4 s** | **5.48 s** | ~1,566 both |
| Muse Glimmer 28B | SYCL | 2.90 s | **2.37 s** | ~1,620; off: 3,178 once at turn 2 |
| | Vulkan | 7.75 s | **4.48 s** | ~1,620; off: 3,178 once at turn 2 |

1. **Every setup reuses its cache.** After turn 2, each turn reprocesses only the new turn (about 1.5–1.6K tokens), with checkpoints on or off, on both engines. Under Forge's reading rule ("both configs reprocess about 1.5K per turn"), **the setting doesn't matter for cache reuse on SYCL**, and "turn checkpoints off and you lose the cache" can be dropped from the docs.
2. **Muse with checkpoints off has one exception:** at turn 2 it reprocesses the whole chat once (3,178 tokens, on both engines), then reuses the cache for turns 3–8.
3. **Checkpoints off was faster in all 6 model and engine pairs,** by 0.4 s (Qwen) to 2.7 s (Gemma on SYCL) per turn. Gemma on Vulkan is the outlier:
   - With checkpoints on, every turn took 124–127 s (turn 1: 98 s), against 4.8–5.8 s with them off.
   - Each turn processed only the ~1,566 new tokens, so the time isn't spent re-reading the chat.
   - This is the same order of cost as the Phase 1 finding (about 25 s at 512 tokens, about 100 s per prompt in the rerun).
4. **Decode speed doesn't depend on the setting** (within 0.4 tok/s in every pair).
5. **Caveat:** this test only appends turns. Checkpoints exist for cases where the prompt changes earlier in the conversation, such as regenerating, editing or stripped reasoning. Those weren't tested.

## D. Qwen on the c08 coding task: budgets, samplers, thinking off

5 tries per setting.
- **Try 1** is greedy (temperature 0).
- **Tries 2–5** use temperature 0.3 with fixed seeds, except Qwen's own sampler (temperature 0.6, top-p 0.95, top-k 20).
- **Server:** SYCL, ub 2048.

| Setting | Passed | Hit the cap | Tokens per try | Median time |
|---|---|---|---|---|
| Thinking, 4K cap | 2/5 | 3 | 4,096 / 4,096 / 2,188 / 3,379 / 4,096 | 180 s |
| Thinking, 8K cap | 3/5 | 2 | 8,192 / 8,192 / 2,188 / 3,379 / 6,036 | 269 s |
| Thinking, 16K cap | **5/5** | 0 | 9,402 / 9,650 / 2,188 / 3,379 / 6,036 | 269 s |
| 8K + presence penalty 1.5 | 3/5 | 2 | 7,443 / 4,564 / 8,192 / 8,192 / 5,323 | 339 s |
| 8K + Qwen's sampler | 3/5 | 2 | 8,192 / 4,799 / 3,148 / 8,192 / 6,328 | 283 s |
| **Thinking off** | **5/5** | 0 | 615 / 322 / 253 / 295 / 283 | **12.7 s** |

1. **Thinking off is the recipe.** It's the only setting that passes 5/5 in a few hundred tokens: a median of 295 tokens and 12.7 s, against 6,036 tokens and 269 s for the 16K cap. Under Forge's rule, the recipe is **"thinking off for coding tasks"** (`--reasoning-budget 0`, or `enable_thinking: false`).
2. **The token caps only cut answers short.** Because the seeds are fixed, the 4K, 8K and 16K rows are the same 5 answers stopped at different caps.
   - Wherever a try wasn't cut off, it's identical to the token across caps (tries 3–5 at 2,188, 3,379 and 6,036).
   - Uncut, Qwen needs 2,188–9,650 tokens on this task, so 4K passes 2 tries and 8K passes 3.
   - A cap doesn't make Qwen think less; it just stops it.
3. **The samplers don't help.** A presence penalty of 1.5 and Qwen's recommended sampler each pass 3/5 at the 8K cap, the same as the plain 8K cap, with similar token counts.
4. **Correction to Phase 3:** Qwen's greedy answer on c08 isn't a loop. It ends on its own at 9,402 tokens (431 s) and passes. Phase 3 stopped it at 2,048 tokens, and the side check at 8,192 tokens. The reasoning does go round in circles, but it terminates.
5. **Caveat:** thinking off was tested on this one task only. Whether it costs quality on the other coding tasks hasn't been measured.

## Corrections to the dry-run reading

The dry run (1 try and 2 turns) was summarized to AJ before the full run. Three of those statements were wrong:
- **"Muse with checkpoints off re-reads the whole chat every turn":** wrong. It does it once, at turn 2. The dry run only had turn 2.
- **"Keep checkpoints on for chat":** wrong. Every setup reuses its cache, and checkpoints off was faster in all six pairs.
- **"Gemma on Vulkan with checkpoints shows the old re-read penalty":** the 124 s per turn is real, but it isn't a re-read. Only the new ~1,566 tokens are processed.

## Open, for Forge

The canary, C and D were settled in Phase 6 ([phase6.md](phase6.md)): the canary is wired, `--ctx-checkpoints 0` is withdrawn as a default for every model, and thinking off holds for Qwen across all 10 coding tasks.

- **The canary:** wire `baseline_ub2048.json` into `compare4.py` for the ub 2048 rows (A passed the 3% rule).
- **C, checkpoint setting:** whether to make `--ctx-checkpoints 0` the default for all three models on SYCL. It was faster in every pair here, but only append-only chats were tested.
- **D, Qwen recipe:** thinking off for coding; a rerun of Phase 3 coding with thinking off would show whether quality holds.
- **B, Gemma's floor:** the ~1.1 s floor on SYCL is a fixed cost per request. Why Vulkan with `--ctx-checkpoints 0` doesn't reuse the cache for identical prompts under 4K tokens is unexplained.
