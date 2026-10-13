# B65 Phase 2 findings: Vulkan vs SYCL

Run p2-20261013-091509. llama.cpp commit 8bb3cf0d2, Vulkan fa0 vs SYCL (oneAPI, JIT, F16) fa0/fa1. Mean of 5 reps after 1 warmup. Power is GPU board power from xe hwmon.

## Verdict
SYCL with flash attention on becomes the default. It clears the 10% decode rule on all three models at short and mid context (+17-24% tg128). The one exception is Qwen decode at 32k: -6% (15.26 vs 16.16). Per the plan, Phase 1 reruns on SYCL fa1.

## Key points
- Flash attention reverses on SYCL: it helps, especially at depth (Gemma tg@32k 9.99 fa0 -> 16.06 fa1; Muse 15.74 -> 22.29).
- Biggest wins: Qwen pp16384 +56% (388 -> 606), Muse tg@32k +51% (14.7 -> 22.3).
- Gemma's long-context decode problem mostly closes: 16.06 tok/s at 32k vs 12.84 on Vulkan.
- SYCL draws ~10-30 W more (up to 199 W, cap 200), but tokens per joule still improve (e.g. Muse tg128 0.129 vs 0.119 tok/J).
- Output check: same-prompt temp-0 answers match (Qwen and Muse identical; Gemma coherent, with a small wording drift expected from FA arithmetic order).

## Open
- Qwen 32k decode regression on SYCL.
- Gemma server checkpoint flag and decode gap need re-checking on SYCL in the Phase 1 rerun.
- Power is near the 200 W cap, so watch for throttling.


| Model | Test | vulkan/fa0 | sycl/fa0 | sycl/fa1 | SYCL best vs Vulkan |
|---|---|---|---|---|---|
| gemma-4-31b-qat | pp512 | 414.48 | 468.64 | 410.75 | +13% |
| gemma-4-31b-qat | tg128 | 19.16 | 22.18 | 22.45 | +17% |
| gemma-4-31b-qat | pp4096 | 378.54 | 418.36 | 414.44 | +11% |
| gemma-4-31b-qat | pp16384 | 335.29 | 384.63 | 397.37 | +19% |
| gemma-4-31b-qat | tg128@d4096 | 17.39 | 17.09 | 20.46 | +18% |
| gemma-4-31b-qat | tg128@d16384 | 16.00 | 13.37 | 18.29 | +14% |
| gemma-4-31b-qat | tg128@d32768 | 12.84 | 9.99 | 16.06 | +25% |
| muse-glimmer | pp512 | 539.92 | 688.19 | 691.22 | +28% |
| muse-glimmer | tg128 | 20.94 | 25.15 | 25.66 | +23% |
| muse-glimmer | pp4096 | 483.03 | 580.08 | 651.98 | +35% |
| muse-glimmer | pp16384 | 429.73 | 508.84 | 608.70 | +42% |
| muse-glimmer | tg128@d4096 | 18.71 | 21.07 | 24.64 | +32% |
| muse-glimmer | tg128@d16384 | 16.79 | 18.41 | 23.56 | +40% |
| muse-glimmer | tg128@d32768 | 14.73 | 15.74 | 22.29 | +51% |
| qwen3.8-27b | pp512 | 445.55 | 663.55 | 639.96 | +49% |
| qwen3.8-27b | tg128 | 19.08 | 23.69 | 23.68 | +24% |
| qwen3.8-27b | pp4096 | 431.84 | 635.10 | 645.52 | +49% |
| qwen3.8-27b | pp16384 | 388.17 | 571.17 | 606.15 | +56% |
| qwen3.8-27b | tg128@d4096 | 18.84 | 21.87 | 22.22 | +18% |
| qwen3.8-27b | tg128@d16384 | 17.69 | 17.79 | 18.63 | +5% |
| qwen3.8-27b | tg128@d32768 | 16.16 | 14.11 | 15.26 | -6% |

## Board W over the timed reps (GPU board power, xe hwmon)

| Model | Test | vulkan/fa0 | sycl/fa0 | sycl/fa1 |
|---|---|---|---|---|
| gemma-4-31b-qat | pp512 | 144.1 | 170.7 | 168.2 |
| gemma-4-31b-qat | tg128 | 181.9 | 175.8 | 176.1 |
| gemma-4-31b-qat | pp4096 | 147.5 | 169.1 | 162.8 |
| gemma-4-31b-qat | pp16384 | 151.6 | 170.1 | 164.3 |
| gemma-4-31b-qat | tg128@d4096 | 178.8 | 166.2 | 174.7 |
| gemma-4-31b-qat | tg128@d16384 | 181.3 | 164.6 | 171.7 |
| gemma-4-31b-qat | tg128@d32768 | 180.9 | 166.0 | 168.9 |
| muse-glimmer | pp512 | 159.0 | 183.1 | 184.6 |
| muse-glimmer | tg128 | 175.5 | 197.7 | 199.4 |
| muse-glimmer | pp4096 | 159.9 | 178.4 | 181.8 |
| muse-glimmer | pp16384 | 161.7 | 176.2 | 181.8 |
| muse-glimmer | tg128@d4096 | 171.0 | 186.2 | 197.0 |
| muse-glimmer | tg128@d16384 | 168.2 | 179.8 | 193.6 |
| muse-glimmer | tg128@d32768 | 165.4 | 173.3 | 190.0 |
| qwen3.8-27b | pp512 | 151.5 | 185.4 | 184.9 |
| qwen3.8-27b | tg128 | 170.2 | 195.1 | 194.9 |
| qwen3.8-27b | pp4096 | 153.2 | 186.2 | 185.6 |
| qwen3.8-27b | pp16384 | 155.9 | 184.9 | 185.6 |
| qwen3.8-27b | tg128@d4096 | 171.3 | 190.8 | 189.5 |
| qwen3.8-27b | tg128@d16384 | 173.0 | 181.8 | 176.4 |
| qwen3.8-27b | tg128@d32768 | 175.8 | 177.4 | 164.6 |
