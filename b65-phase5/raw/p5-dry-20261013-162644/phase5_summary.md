# Phase 5 summary (p5-dry-20261013-162644)

```
run_id=p5-dry-20261013-162644
date=2026-10-13T16:26:44-04:00
kernel=7.2.5-3-omarchy
mesa=mesa 1:26.2.2-1
oneapi=Intel(R) oneAPI DPC++/C++ Compiler 2026.0.0 (2026.0.0.20260331)
level_zero=level-zero-loader 1.32.0-1 intel-compute-runtime 26.31.39395.13-1 
llama_sycl=version: 0.6.0-dev (build 11574, commit 8bb3cf0d2)
vk_bin=/home/snowdesk/Projects/b65-benchmarks/b65-phase5/../vendor/llama.cpp/build/bin vk_index=1
sycl_device=  SYCL0: Intel(R) Arc(TM) Pro B65 Graphics (32656 MiB, 32583 MiB free)
parts_list=A B C D
parts=A B C D dry=1 reps=1 energy_file=/sys/class/hwmon/hwmon6/energy1_input
```

## A. New baseline (SYCL fa1, ub 2048)

| model | test | tok_s | W |
|---|---|---|---|
| qwen3.8-27b | pp512 | 639.03 | 178.0 |
| qwen3.8-27b | tg128 | 23.7 | 191.4 |
| gemma-4-31b-qat | pp512 | 410.74 | 164.2 |
| gemma-4-31b-qat | tg128 | 22.51 | 173.3 |
| muse-glimmer | pp512 | 677.65 | 177.8 |
| muse-glimmer | tg128 | 25.63 | 195.3 |

## B. Gemma TTFT, median of reps (cached=1 means identical prompt reused)

| backend | cfg | prompt_tokens | cached | ttft_s | server_prompt_ms |
|---|---|---|---|---|---|
| sycl | ub512 | 16 | 0 | 1.523 | 1522.200 |
| sycl | ub512 | 16 | 1 | 0.113 | 112.000 |
| sycl | ub512 | 64 | 0 | 1.138 | 1137.100 |
| sycl | ub512 | 64 | 1 | 0.157 | 156.500 |
| sycl | ub2048 | 16 | 0 | 1.522 | 1521.200 |
| sycl | ub2048 | 16 | 1 | 0.113 | 111.800 |
| sycl | ub2048 | 64 | 0 | 1.139 | 1138.000 |
| sycl | ub2048 | 64 | 1 | 0.140 | 139.100 |
| sycl | ub2048-nowarm | 16 | 0 | 1.520 | 1519.700 |
| sycl | ub2048-nowarm | 16 | 1 | 0.112 | 111.500 |
| sycl | ub2048-nowarm | 64 | 0 | 1.138 | 1137.400 |
| sycl | ub2048-nowarm | 64 | 1 | 0.139 | 137.800 |
| vulkan | ub512 | 16 | 0 | 0.748 | 747.000 |
| vulkan | ub512 | 16 | 1 | 0.722 | 721.600 |
| vulkan | ub512 | 64 | 0 | 0.559 | 558.400 |
| vulkan | ub512 | 64 | 1 | 0.537 | 536.400 |

## C. Multi-turn: tokens reprocessed per turn

| model | backend | cfg | turns | reprocessed/turn (t2+) | last ttft_s | last ctx |
|---|---|---|---|---|---|---|
| qwen3.8-27b | sycl | ckpt-default | 2 | 1533 | 2.109 | 3121 |
| qwen3.8-27b | sycl | ckpt0 | 2 | 1533 | 1.865 | 3121 |
| qwen3.8-27b | vulkan | ckpt-default | 2 | 1533 | 3.937 | 3131 |
| qwen3.8-27b | vulkan | ckpt0 | 2 | 1533 | 3.638 | 3130 |
| muse-glimmer | sycl | ckpt-default | 2 | 1626 | 2.687 | 3178 |
| muse-glimmer | sycl | ckpt0 | 2 | 3178 | 3.796 | 3178 |
| muse-glimmer | vulkan | ckpt-default | 2 | 1626 | 7.259 | 3178 |
| muse-glimmer | vulkan | ckpt0 | 2 | 3178 | 7.017 | 3178 |
| gemma-4-31b-qat | sycl | ckpt-default | 2 | 1570 | 5.615 | 3115 |
| gemma-4-31b-qat | sycl | ckpt0 | 2 | 1568 | 3.098 | 3113 |
| gemma-4-31b-qat | vulkan | ckpt-default | 2 | 1568 | 124.186 | 3113 |
| gemma-4-31b-qat | vulkan | ckpt0 | 2 | 1568 | 5.065 | 3113 |

## D. Qwen c08 thinking

| variant | pass | hit cap | median tokens | median s |
|---|---|---|---|---|
| think-4k | 0/1 | 1 | 4096.000 | 180.800 |
| think-8k | 0/1 | 1 | 8192.000 | 371.700 |
| think-16k | 1/1 | 0 | 9402.000 | 430.500 |
| think-8k-pp1.5 | 1/1 | 0 | 7443.000 | 339.600 |
| think-8k-qwen-sampler | 0/1 | 1 | 8192.000 | 371.800 |
| nothink | 1/1 | 0 | 615.000 | 27.600 |

