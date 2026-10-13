# Arc Pro B65 benchmark: Phase 4 findings (canary and micro-batch check)

> **Decision (Forge, 2026-10-13, after checking every number against canary.csv):**
> - `-b 2048 -ub 2048` is the SYCL default for all three models.
> - The canary stays at ub 512, so it stays comparable to its baseline. `baseline.json` is unchanged.
> - Vulkan stays at ub 512.

First canary `p4-20261013-150339`, 2026-10-13, 3:03–3:41 PM ET, run with `UBCHECK=1 B65_VK_INDEX=1` and the default models (Qwen and Muse). All 20 tests ok. Package: `b65-phase4-p4-20261013-150339.tar.gz`.

- **Versions:** the same as the Phase 2 baseline. Kernel 7.2.5-3-omarchy, Mesa 26.2.2, oneAPI DPC++ 2026.0, compute-runtime 26.31.39395.13, Level Zero 1.32.0, llama.cpp 11574 (`8bb3cf0d2`). Nothing has been updated, so this run is also a reproducibility check.
- **Method:** llama-bench, 5 reps, `-b 2048`. Board W is averaged over the timed reps, the same method as the baseline.

## Canary: drift vs the Phase 2 baseline (SYCL, flash attention on, ub 512)

| Model | Test | Baseline | Now | Drift | Board W |
|---|---|---|---|---|---|
| Qwen 3.8 27B | pp512 | 639.96 | 639.86 | −0.0% | 184.2 |
| | pp16384 | 606.15 | 605.94 | −0.0% | 185.7 |
| | tg128 | 23.68 | 23.69 | +0.0% | 195.4 |
| | tg128 @16K | 18.63 | 18.64 | +0.1% | 177.4 |
| Muse Glimmer 28B | pp512 | 691.22 | 690.61 | −0.1% | 184.0 |
| | pp16384 | 608.70 | 608.72 | +0.0% | 182.1 |
| | tg128 | 25.66 | 25.64 | −0.1% | 199.5 |
| | tg128 @16K | 23.56 | 23.56 | +0.0% | 194.3 |

**0 flagged.** Every test is within 0.1% of the baseline, which sets the noise floor the 5% bar has to clear.

## Micro-batch check (ub 512 vs 2048)

| Model | Backend | pp4096 | pp16384 | tg128 @16K |
|---|---|---|---|---|
| Qwen 3.8 27B | SYCL, FA on | 645.5 → 890.7 (**+38%**) | 605.9 → 824.2 (**+36%**) | 18.64 → 18.86 (+1.2%) |
| Muse Glimmer 28B | SYCL, FA on | 652.1 → 906.8 (**+39%**) | 608.7 → 820.7 (**+35%**) | 23.56 → 23.44 (−0.5%) |
| Qwen 3.8 27B | Vulkan, FA off | | 388.2 → 428.7 (+10%) | |
| Muse Glimmer 28B | Vulkan, FA off | | 429.8 → 274.0 (**−36%**) | |
| Gemma 4 31B QAT (Gemma diagnostic) | SYCL, FA on | | 397.4 → 617.1 (+55%) | server decode −5% |

## Findings
1. **Nothing has drifted.** With unchanged versions, the canary reproduces Phase 2 within 0.1% on all 8 tests, so future flags will mean something.
2. **`-ub 2048` speeds up SYCL prefill for every model:** Qwen +36%, Muse +35% at 16K (Gemma +55%). Decode is unchanged (+1.2% and −0.5%). Both clear the handoff's rule (more than +10% prefill, no more than 5% decode cost), so under that rule **ub 2048 becomes the SYCL default for all three models**.
   - Board power is 10–12 W higher during prefill at ub 2048 (about 195 W against 184 W), and prefill tokens per joule still improve by 27–29%.
3. **On Vulkan, the micro-batch effect depends on the model.** Qwen gains 10%; Muse loses 36% (430 → 274 tok/s), with board power falling to 122 W. A recheck in a fresh process (`raw/p4-recheck-20261013-154203`, same model file) reproduced it: 272.0 vs 429.7 tok/s, five reps each within 1 tok/s. It's a Vulkan-path behaviour for Muse at that batch size, not noise. Keep Vulkan at the default ub 512.
4. **SYCL's prefill lead over Vulkan grows with ub 2048.** At 16K, each engine at its best setting: Qwen 824 vs 429 tok/s (1.9×, both at ub 2048) and Muse 821 vs 430 (1.9×, Vulkan at ub 512).

## Notes on this run
- **The summary was finalized by hand.** I edited `canary.sh` (adding a `vk_index` line to `env.txt`) while the run was going. Bash reads scripts incrementally, so the edit broke the script's last lines after all 20 tests had completed. `canary_summary.md` and `done` were then written by running `compare4.py` and touching `done` by hand (`NOTE-finalized-by-hand.txt`). No measurement was affected. Lesson: never edit a kit script while a run is using it.
- **`compare4.py` fix:** tests without a baseline, such as pp4096 from the micro-batch check, were listed as "+0.0% ok" in the drift table. They're now left out of it and appear only in the micro-batch table.

## Next
- **Decided:** ub 2048 is the SYCL default for all three; the canary and `baseline.json` stay at ub 512. Qwen and Muse server time to first token at ub 2048 hasn't been measured yet; llama-bench predicts about 35% faster prefill.
- **The Muse Vulkan ub 2048 drop** is a candidate llama.cpp Vulkan issue, if Vulkan stays relevant.
- **Routine:** run `./canary.sh` (about 10 minutes) after any Mesa, kernel, oneAPI, llama.cpp or LM Studio update.
