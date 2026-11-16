# Phase 9 part L: llama.cpp b11574 vs v1.0.0 (p9l-dry-20261113-182206)

| backend | model | test | b11574 tok/s | v1.0.0 tok/s | change | b11574 W | v1.0.0 W |
|---|---|---|---:|---:|---:|---:|---:|
| sycl | qwen3.8-27b | pp512 | 639.86 ± 0.00 | 773.97 ± 0.00 | +21.0% | 176.5 | 189.8 |
| sycl | qwen3.8-27b | tg128 | 23.68 ± 0.00 | 10.90 ± 0.00 | -54.0% | 188.0 | 104.0 |
| vulkan | qwen3.8-27b | tg128 | 19.06 ± 0.00 | 19.09 ± 0.00 | +0.2% | 165.7 | 166.3 |

- sycl prefill: geometric mean +21.0% over 1 tests
- sycl decode: geometric mean -54.0% over 1 tests
- vulkan decode: geometric mean +0.2% over 1 tests
