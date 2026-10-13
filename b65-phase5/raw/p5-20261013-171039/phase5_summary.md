# Phase 5 summary (p5-20261013-171039)

```
run_id=p5-20261013-171039
date=2026-10-13T17:10:39-04:00
kernel=7.2.5-3-omarchy
mesa=mesa 1:26.2.2-1
oneapi=Intel(R) oneAPI DPC++/C++ Compiler 2026.0.0 (2026.0.0.20260331)
level_zero=level-zero-loader 1.32.0-1 intel-compute-runtime 26.31.39395.13-1 
llama_sycl=version: 0.6.0-dev (build 11574, commit 8bb3cf0d2)
vk_bin=/home/snowdesk/Projects/b65-benchmarks/b65-phase5/../vendor/llama.cpp/build/bin vk_index=1
sycl_device=  SYCL0: Intel(R) Arc(TM) Pro B65 Graphics (32656 MiB, 32583 MiB free)
parts_list=A B C D
parts=A B C D dry=0 reps=5 energy_file=/sys/class/hwmon/hwmon6/energy1_input
```

## A. New baseline (SYCL fa1, ub 2048)

| model | test | tok_s | W |
|---|---|---|---|
| qwen3.8-27b | pp512 | 639.98 | 182.9 |
| qwen3.8-27b | pp16384 | 824.33 | 196.2 |
| qwen3.8-27b | tg128 | 23.69 | 195.6 |
| qwen3.8-27b | tg128@d16384 | 18.86 | 180.9 |
| gemma-4-31b-qat | pp512 | 410.85 | 169.1 |
| gemma-4-31b-qat | pp16384 | 616.92 | 188.0 |
| gemma-4-31b-qat | tg128 | 22.45 | 176.8 |
| gemma-4-31b-qat | tg128@d16384 | 18.06 | 171.9 |
| muse-glimmer | pp512 | 690.81 | 185.5 |
| muse-glimmer | pp16384 | 820.67 | 193.3 |
| muse-glimmer | tg128 | 25.64 | 199.5 |
| muse-glimmer | tg128@d16384 | 23.44 | 193.7 |

## B. Gemma TTFT, median of reps (cached=1 means identical prompt reused)

| backend | cfg | prompt_tokens | cached | ttft_s | server_prompt_ms |
|---|---|---|---|---|---|
| sycl | ub512 | 16 | 0 | 1.091 | 1090.400 |
| sycl | ub512 | 16 | 1 | 0.110 | 109.300 |
| sycl | ub512 | 64 | 0 | 1.134 | 1133.300 |
| sycl | ub512 | 64 | 1 | 0.139 | 138.100 |
| sycl | ub512 | 256 | 0 | 1.384 | 1382.300 |
| sycl | ub512 | 256 | 1 | 0.252 | 250.800 |
| sycl | ub512 | 1024 | 0 | 3.793 | 3788.900 |
| sycl | ub512 | 1024 | 1 | 0.645 | 642.100 |
| sycl | ub512 | 4096 | 0 | 14.536 | 14522.100 |
| sycl | ub512 | 4096 | 1 | 0.305 | 292.300 |
| sycl | ub2048 | 16 | 0 | 1.091 | 1090.300 |
| sycl | ub2048 | 16 | 1 | 0.110 | 109.200 |
| sycl | ub2048 | 64 | 0 | 1.134 | 1133.300 |
| sycl | ub2048 | 64 | 1 | 0.140 | 138.800 |
| sycl | ub2048 | 256 | 0 | 1.383 | 1381.500 |
| sycl | ub2048 | 256 | 1 | 0.252 | 250.700 |
| sycl | ub2048 | 1024 | 0 | 2.465 | 2460.600 |
| sycl | ub2048 | 1024 | 1 | 0.644 | 640.700 |
| sycl | ub2048 | 4096 | 0 | 7.715 | 7702.500 |
| sycl | ub2048 | 4096 | 1 | 0.286 | 274.400 |
| sycl | ub2048-nowarm | 16 | 0 | 1.091 | 1090.800 |
| sycl | ub2048-nowarm | 16 | 1 | 0.110 | 109.600 |
| sycl | ub2048-nowarm | 64 | 0 | 1.134 | 1133.400 |
| sycl | ub2048-nowarm | 64 | 1 | 0.139 | 137.900 |
| sycl | ub2048-nowarm | 256 | 0 | 1.384 | 1382.000 |
| sycl | ub2048-nowarm | 256 | 1 | 0.253 | 251.400 |
| sycl | ub2048-nowarm | 1024 | 0 | 2.464 | 2460.900 |
| sycl | ub2048-nowarm | 1024 | 1 | 0.645 | 641.000 |
| sycl | ub2048-nowarm | 4096 | 0 | 7.716 | 7704.000 |
| sycl | ub2048-nowarm | 4096 | 1 | 0.285 | 272.500 |
| vulkan | ub512 | 16 | 0 | 0.723 | 722.600 |
| vulkan | ub512 | 16 | 1 | 0.724 | 723.300 |
| vulkan | ub512 | 64 | 0 | 0.537 | 536.400 |
| vulkan | ub512 | 64 | 1 | 0.536 | 535.500 |
| vulkan | ub512 | 256 | 0 | 1.084 | 1082.500 |
| vulkan | ub512 | 256 | 1 | 1.086 | 1085.200 |
| vulkan | ub512 | 1024 | 0 | 2.654 | 2650.700 |
| vulkan | ub512 | 1024 | 1 | 2.654 | 2651.300 |
| vulkan | ub512 | 4096 | 0 | 11.053 | 11042.200 |
| vulkan | ub512 | 4096 | 1 | 0.071 | 61.300 |

## C. Multi-turn: tokens reprocessed per turn

| model | backend | cfg | turns | reprocessed/turn (t2+) | last ttft_s | last ctx |
|---|---|---|---|---|---|---|
| qwen3.8-27b | sycl | ckpt-default | 8 | 1533/1533/1533/1533/1533/1533/1533 | 2.693 | 12559 |
| qwen3.8-27b | sycl | ckpt0 | 8 | 1533/1533/1533/1533/1533/1533/1533 | 2.101 | 12559 |
| qwen3.8-27b | vulkan | ckpt-default | 8 | 1533/1533/1533/1533/1533/1533/1533 | 4.729 | 12599 |
| qwen3.8-27b | vulkan | ckpt0 | 8 | 1533/1533/1533/1533/1533/1533/1533 | 4.2 | 12592 |
| muse-glimmer | sycl | ckpt-default | 8 | 1626/1620/1620/1620/1620/1620/1620 | 3.057 | 12904 |
| muse-glimmer | sycl | ckpt0 | 8 | 3178/1620/1620/1620/1620/1620/1620 | 2.45 | 12904 |
| muse-glimmer | vulkan | ckpt-default | 8 | 1626/1620/1620/1620/1620/1620/1620 | 8.743 | 12904 |
| muse-glimmer | vulkan | ckpt0 | 8 | 3178/1620/1526/1620/1620/1620/1620 | 4.67 | 12904 |
| gemma-4-31b-qat | sycl | ckpt-default | 8 | 1570/1571/1572/1573/1571/1571/1571 | 6.102 | 12520 |
| gemma-4-31b-qat | sycl | ckpt0 | 8 | 1568/1566/1567/1566/1566/1566/1566 | 3.367 | 12486 |
| gemma-4-31b-qat | vulkan | ckpt-default | 8 | 1568/1566/1567/1566/1566/1566/1566 | 127.226 | 12486 |
| gemma-4-31b-qat | vulkan | ckpt0 | 8 | 1568/1566/1567/1566/1566/1566/1566 | 5.823 | 12486 |

## D. Qwen c08 thinking

| variant | pass | hit cap | median tokens | median s |
|---|---|---|---|---|
| think-4k | 2/5 | 3 | 4096.000 | 179.800 |
| think-8k | 3/5 | 2 | 6036.000 | 269.100 |
| think-16k | 5/5 | 0 | 6036.000 | 269.000 |
| think-8k-pp1.5 | 3/5 | 2 | 7443.000 | 339.200 |
| think-8k-qwen-sampler | 3/5 | 2 | 6328.000 | 283.000 |
| nothink | 5/5 | 0 | 295.000 | 12.700 |

