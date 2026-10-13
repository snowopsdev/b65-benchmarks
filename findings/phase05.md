# Arc Pro B65 benchmark: Phase 0.5 findings

Setup: llama.cpp llama-bench build 11574 (`8bb3cf0d2`), Vulkan, Mesa 26.2.2, kernel 7.2.5-3-omarchy, Omarchy 4.0.4-1. Each test ran 5 times and the mean is reported. Power is GPU board power from xe hwmon only, averaged over the timed runs (not model load), the same method as Phase 0. Run `p05-20261012-163413`, 16:34–17:30 ET.

**Headline: on this llama.cpp build (b11574, Vulkan), flash attention slows prompt processing for every model on this card, and decode for Gemma and Muse (Qwen's decode is a tie). Turning it off (`-fa 0`) is the default from now on.**

| Model | Test | fa=1 | fa=0 | Change |
|---|---|---|---|---|
| Qwen 3.8 27B | pp512 / pp4096 / pp16384 | 434 / 358 / 221 | 446 / 432 / 388 | +3% / +21% / +76% |
| Qwen 3.8 27B | tg128 @16k | 17.33 | 17.62 | +2% |
| Gemma 4 31B QAT | pp512 / pp4096 / pp16384 | 294 / 111 / 38* | 413 / 379 / 335 | +40% / +240% / **+783%** |
| Gemma 4 31B QAT | tg128 @16k | 14.57 | 15.99 | +10% |
| Muse Glimmer 28B | pp512 / pp4096 / pp16384 | 523 / 375 / 275 | 540 / 483 / 430 | +3% / +29% / +57% |
| Muse Glimmer 28B | tg128 @16k | 11.26 | 16.78 | **+49%** |

*The Gemma fa=1 pp16384 figure is from Phase 0. It was skipped this time on purpose.

- Gemma's prefill collapse was the flash-attention setting, not the card. Its prefill numbers are now cleared for posting with `-fa 0`. The flash-attention-on values (294 / 111 / 38) were released for posting too (AJ, 2026-10-12), so the before/after comparison can be published.
- With `-fa 0`, all three models pass the registry's 15 tok/s decode check at 16k context: Qwen 17.6, Gemma 16.0, Muse 16.8.
- With `-fa 0`, prefill now drops off gently with longer prompts: 13% for Qwen, 19% for Gemma and 20% for Muse from 512 to 16k tokens.
- Efficiency improves too. Prefill tokens per joule goes up for every model, e.g. Gemma at pp4096 goes from 0.76 to 2.55. Decode efficiency is mixed: Muse improves (0.087 → 0.099 tok/J), Gemma is flat (0.087 → 0.088), and Qwen is slightly lower (0.104 → 0.102), because it draws 173 W instead of 167 W for the same speed.
- Provenance: all three model files match Hugging Face main.
  - Qwen: `lmstudio-community/Qwen3.8-27B-GGUF` at commit `5a7da681`
  - Gemma: `lmstudio-community/gemma-4-31B-it-QAT-GGUF` at commit `12e5eae7`
  - Muse: `lmstudio-community/Muse-Glimmer-30B-GGUF` at commit `c34cb737`
- Omarchy version: 4.0.4-1. All 23 tests passed, with 1 intentionally skipped.
- The fa=1 reruns reproduce Phase 0 within 0.3% on every test except Gemma tg128 @16k (14.57 vs 14.26). That gap is Phase 0's cold first run; against Phase 0's median (14.52) it's 0.3%. So the differences come from the setting, not drift.
- Power runs a little warmer later in a sweep: Qwen fa=1 pp512 read 153 W here vs 149 W in Phase 0 at the same speed.

**Follow-up (done):** tg128 and tg128@d4096 were rerun with `-fa 0` (run `p05b-20261012-173906`, 17:39–17:48 ET, 6/6 ok), so the decode table below uses one setting throughout. Phase 1 uses `-fa 0` for all models.

## Power and efficiency with flash attention off
| Model | pp4096 W | pp4096 tok/J | tg@16k W | tg@16k tok/J |
|---|---|---|---|---|
| Qwen 3.8 27B | 152.8 | 2.83 | 173.4 | 0.102 |
| Gemma 4 31B QAT | 148.5 | 2.55 | 182.4 | 0.088 |
| Muse Glimmer 28B | 160.9 | 3.00 | 169.0 | 0.099 |

## Notes
- Naming: Muse Glimmer is "28B" in both findings files (llama.cpp counts 27.85B; the release name is 30B). The share cards and dashboards now say 28B to match.
- Package: `b65-phase05-p05-20261012-163413.tar.gz` (raw sweep, fa_sweep.csv, provenance.csv, printed table, regenerated Phase 0 results.csv, scripts as run).

## Decode with flash attention off (one setting throughout)
tok/s, mean of 5 runs. 0 and 4K context from the follow-up run; 16K from the main sweep. fa=1 shown for comparison
(0 and 4K from Phase 0, 16K from this sweep).

| Model | @0 ctx | @4K | @16K | Drop 0 → 16K | fa=1 drop |
|---|---|---|---|---|---|
| Qwen 3.8 27B | 19.08 | 18.85 | 17.62 | −8% | −9% |
| Gemma 4 31B QAT | 19.13 | 17.40 | 15.99 | −16% | −21% |
| Muse Glimmer 28B | 20.94 | 18.70 | 16.78 | −20% | −46% |

- At 0 context the setting barely matters for Qwen (19.08 vs 19.02) and Muse (20.94 vs 20.93); Gemma is 3.7% faster with it off (19.13 vs 18.45).
- Muse's 4K decode improves 24% with flash attention off (18.70 vs 15.10 in Phase 0).
- Board power at decode with fa=0: 167–180 W; decode tok/J 0.097–0.120 at 0 and 4K context.
- Gemma's fa=1 drop is −21% using this sweep's warm 16K value (14.57); Phase 0's findings said −23% because Phase 0's 16K figure (14.26) included a cold first run.
