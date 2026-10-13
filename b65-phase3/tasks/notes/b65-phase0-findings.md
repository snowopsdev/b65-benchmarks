# Arc Pro B65 benchmark: Phase 0 findings

Run `20261012-140638`, 2026-10-12, 2:06 PM ET.

## Setup
- **GPU:** Intel Arc Pro B65, 32 GB (BMG G31, PCI ID 8086:e222). The RTX 3080 was excluded.
- **Host:** Ryzen 7 5700X, 46 GB RAM, CPU governor set to performance.
- **OS:** Omarchy, kernel 7.2.5-3-omarchy.
- **Driver:** Mesa 26.2.2 (vulkan-intel). Cooperative-matrix acceleration (KHR_coopmat) is available.
- **Engine:** llama.cpp llama-bench, build 11574 (commit `8bb3cf0d2`), on Vulkan.
- **Bench flags:** `-ngl 99 -fa on -r 5`. Each test gets 1 warmup run plus 5 measured runs, and the mean is reported.
- **PCIe:** 4.0 x4 upstream link behind a switch (the card can do 5.0 x16). ReBAR is on with a 32 GB BAR.
- **Power:** GPU board power only, read from the xe hwmon energy counter. The board power cap is 200 W. There's no wall meter.

## Models
| Model | Quant | File | sha256 |
|---|---|---|---|
| Qwen 3.8 27B | Q4_K_M | Qwen3.8-27B-Q4_K_M.gguf | `e00082f7…e520` |
| Gemma 4 31B QAT | Q4_0 | gemma-4-31B-it-QAT-Q4_0.gguf | `6f63619c…6a7b` |
| Muse Glimmer 28B | Q4_K_M | Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf | `4cc57c0f…f60e` |

All three files are from lmstudio-community. The Hugging Face commit for each one still needs to be recorded.

## Results (tokens per second, mean of 5 runs)
| Model | pp512 | pp4096 | pp16384 | tg128 | tg @4k depth | tg @16k depth |
|---|---|---|---|---|---|---|
| Qwen 3.8 27B | 434.2 | 358.1 | 221.1 | 19.02 | 18.75 | 17.33 |
| Gemma 4 31B QAT | 294.8 | 111.4 ⚠ | 38.0 ⚠ | 18.45 | 16.43 | 14.26 |
| Muse Glimmer 28B | 522.2 | 375.0 | 274.5 | 20.93 | 15.10 | 11.23 |

All 18 tests passed. Run-to-run variation was under 1% everywhere except Gemma's tg @16k, which varied by about 4.5%.

## Power (GPU board, average per test)
| Model | Prefill (W) | Decode (W) | Decode tokens per joule |
|---|---|---|---|
| Qwen 3.8 27B | 142–149 | 167–170 | 0.104–0.112 |
| Gemma 4 31B QAT | 143–152 | 164–179 | 0.087–0.103 |
| Muse Glimmer 28B | 136–156 | 130–175 | 0.086–0.119 |

The idle draw with no model loaded was 43.1 W.

## Findings
1. **The data is clean and publishable.** Device pinning was correct, every test passed, run-to-run variation is tiny, and the model hashes are recorded.
2. **Decode speed is close across models at short context:** 18.4 to 20.9 tok/s. At 16k context the order changes. Qwen loses only 9%, while Muse loses 46%.
3. **Gemma's prefill collapses, which is likely a software problem.** Prefill drops from 295 to 38 tok/s as the prompt grows, and the pp16384 test alone took 43 minutes. The other models only roughly halve over the same range. The likely cause is the Vulkan flash-attention path combined with Gemma's attention layout. **Don't publish Gemma prefill numbers until it's rerun with `-fa 0`.**
4. **Decode reaches about 55% of the memory-bandwidth ceiling.** The ceiling is 608 GB/s divided by about 17.7 GB of weights, or roughly 34 tok/s. That's typical for llama.cpp on Vulkan and gives an honest "headroom" angle for posts.
5. **Registry check (decode must be at least 15 tok/s):** Qwen passes at every depth. Gemma fails at 16k (14.3). Muse is borderline at 4k (15.1) and fails at 16k (11.2). Note that the registry measures with its own harness, not these llama-bench numbers.
6. **The PCIe 4.0 x4 link only affects model load time, not these speeds.** Mention it in the methodology section.
7. **Board power stays under the 200 W cap.** Decode draws more than prefill, at roughly 165 to 178 W.

## Gaps and next steps
- Rerun Gemma's pp4096 and pp16384 tests with `-fa 0`. Optionally rerun all three models with `-fa 0` as a control.
- Record each model's Hugging Face repo and commit, which the registry recipes need.
- Fix `report.py`, which leaves tok/J blank for the prefill rows.
- Record the Omarchy version, which came out as "unknown" in `env.txt`.
- Phase 1: serving and time-to-first-token runs, a table of which context sizes fit, and idle power with a model loaded.
- Phase 1.5: registry recipes, blocked until @0xSero answers whether llama.cpp Vulkan counts.

## Cleared for posting
- Cleared: decode speed for all three models, Qwen's full row, the power numbers, and the methodology.
- Hold: Gemma's prefill numbers.

---
# Phase 0.5 update (run p05-20261012-163413)

**Headline: flash attention on Vulkan slows every model on this card. Turning it off (`-fa 0`) is the default from now on.**

| Model | Test | fa=1 | fa=0 | Change |
|---|---|---|---|---|
| Qwen 3.8 27B | pp512 / pp4096 / pp16384 | 434 / 358 / 221 | 446 / 432 / 388 | +3% / +21% / +76% |
| Qwen 3.8 27B | tg128 @16k | 17.33 | 17.62 | +2% |
| Gemma 4 31B QAT | pp512 / pp4096 / pp16384 | 294 / 111 / 38* | 413 / 379 / 335 | +40% / +240% / **+783%** |
| Gemma 4 31B QAT | tg128 @16k | 14.57 | 15.99 | +10% |
| Muse Glimmer 28B | pp512 / pp4096 / pp16384 | 523 / 375 / 275 | 540 / 483 / 430 | +3% / +29% / +57% |
| Muse Glimmer 28B | tg128 @16k | 11.26 | 16.78 | **+49%** |

*The Gemma fa=1 pp16384 figure is from Phase 0. It was skipped this time on purpose.

- Gemma's prefill collapse was the flash-attention setting, not the card. Its prefill numbers are now cleared for posting with `-fa 0`.
- With `-fa 0`, all three models pass the registry's 15 tok/s decode check at 16k context: Qwen 17.6, Gemma 16.0, Muse 16.8.
- With `-fa 0`, prefill now drops off gently with longer prompts: 13% for Qwen, 19% for Gemma and 20% for Muse from 512 to 16k tokens.
- Efficiency improves too. Prefill tokens per joule goes up for every model, e.g. Gemma at pp4096 goes from 0.76 to 2.55.
- Provenance: all three model files match Hugging Face main.
  - Qwen: `lmstudio-community/Qwen3.8-27B-GGUF` at commit `5a7da681`
  - Gemma: `lmstudio-community/gemma-4-31B-it-QAT-GGUF` at commit `12e5eae7`
  - Muse: `lmstudio-community/Muse-Glimmer-30B-GGUF` at commit `c34cb737`
- Omarchy version: 4.0.4-1. All 23 tests passed, with 1 intentionally skipped.

**Follow-up:** Phase 0 decode at short and 4k context was run with fa=1. Rerun tg128 and tg128@d4096 with `-fa 0` (about 10 minutes total) so the published decode table uses one setting throughout. Phase 1 uses `-fa 0` for all models.
