# Phase 2 summary: Vulkan vs SYCL (tok/s)

| Model | Test | vulkan/fa0 | sycl/fa0 | sycl/fa1 | SYCL best vs Vulkan |
|---|---|---|---|---|---|
| qwen3.8-27b | pp512 | 445.69 | 663.97 | 639.53 | +49% |
| qwen3.8-27b | tg128 | 19.04 | 23.69 | 23.68 | +24% |

## Board W over the timed reps (GPU board power, xe hwmon)

| Model | Test | vulkan/fa0 | sycl/fa0 | sycl/fa1 |
|---|---|---|---|---|
| qwen3.8-27b | pp512 | 149.4 | 182.7 | 181.8 |
| qwen3.8-27b | tg128 | 166.1 | 192.2 | 192.4 |
