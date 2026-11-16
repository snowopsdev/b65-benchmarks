# Phase 9 part L: llama.cpp b11574 vs v1.0.0 (p9l-20261113-183511)

| backend | model | test | b11574 tok/s | v1.0.0 tok/s | change | b11574 W | v1.0.0 W |
|---|---|---|---:|---:|---:|---:|---:|
| sycl | qwen3.8-27b | pp512 | 640.98 ± 0.15 | 774.96 ± 0.41 | +20.9% | 182.8 | 193.7 |
| sycl | qwen3.8-27b | pp4096 | 891.97 ± 0.24 | 951.33 ± 1.97 | +6.7% | 195.3 | 198.9 |
| sycl | qwen3.8-27b | pp16384 | 824.26 ± 0.29 | 878.62 ± 0.26 | +6.6% | 195.9 | 199.2 |
| sycl | qwen3.8-27b | tg128 | 23.68 ± 0.02 | 24.49 ± 0.00 | +3.4% | 195.1 | 186.0 |
| sycl | qwen3.8-27b | tg128@d16384 | 18.77 ± 0.00 | 19.19 ± 0.01 | +2.2% | 179.7 | 171.2 |
| vulkan | qwen3.8-27b | pp512 | 445.52 ± 0.24 | 491.06 ± 0.23 | +10.2% | 153.4 | 158.7 |
| vulkan | qwen3.8-27b | pp16384 | 388.17 ± 0.04 | 422.54 ± 0.04 | +8.9% | 156.3 | 161.3 |
| vulkan | qwen3.8-27b | tg128 | 19.07 ± 0.01 | 19.08 ± 0.02 | +0.1% | 170.2 | 170.4 |
| sycl | muse-glimmer | pp512 | 691.03 ± 0.28 | 860.45 ± 1.01 | +24.5% | 183.5 | 196.3 |
| sycl | muse-glimmer | pp4096 | 905.63 ± 2.82 | 982.99 ± 0.63 | +8.5% | 192.3 | 198.3 |
| sycl | muse-glimmer | pp16384 | 811.19 ± 11.47 | 890.07 ± 0.27 | +9.7% | 190.9 | 198.1 |
| sycl | muse-glimmer | tg128 | 25.68 ± 0.02 | 26.92 ± 0.02 | +4.8% | 199.5 | 193.1 |
| sycl | muse-glimmer | tg128@d16384 | 23.60 ± 0.20 | 24.57 ± 0.23 | +4.1% | 193.8 | 187.4 |
| vulkan | muse-glimmer | pp512 | 540.08 ± 0.85 | 583.20 ± 0.62 | +8.0% | 160.9 | 165.5 |
| vulkan | muse-glimmer | pp16384 | 429.70 ± 0.05 | 457.57 ± 0.11 | +6.5% | 161.7 | 166.6 |
| vulkan | muse-glimmer | tg128 | 20.93 ± 0.01 | 20.98 ± 0.00 | +0.2% | 175.4 | 175.7 |

- sycl prefill: geometric mean +12.6% over 6 tests
- sycl decode: geometric mean +3.6% over 4 tests
- vulkan prefill: geometric mean +8.4% over 4 tests
- vulkan decode: geometric mean +0.1% over 2 tests
