# Phase 6 summary (p6-dry-20261013-205752)

```
run_id=p6-dry-20261013-205752
date=2026-10-13T20:57:52-04:00
kernel=7.2.5-3-omarchy
mesa=mesa 1:26.2.2-1
oneapi=Intel(R) oneAPI DPC++/C++ Compiler 2026.0.0 (2026.0.0.20260331)
level_zero=level-zero-loader 1.32.0-1 intel-compute-runtime 26.31.39395.13-1 
llama_sycl=version: 0.6.0-dev (build 11574, commit 8bb3cf0d2)
vk_bin=/home/snowdesk/Projects/b65-benchmarks/b65-phase6/../vendor/llama.cpp/build/bin vk_index=1
sycl_device=  SYCL0: Intel(R) Arc(TM) Pro B65 Graphics (32656 MiB, 32583 MiB free)
parts_list=A B C
parts=A B C dry=1 reps=1 energy_file=/sys/class/hwmon/hwmon6/energy1_input
```

## A. Coding, thinking off (10 tasks x tries)

| model | pass | greedy pass | failed tasks | median tokens | total s |
|---|---|---|---|---|---|
| qwen3.8-27b | 2/2 | 2/2 | - | 124 | 9 |
| muse-glimmer | 2/2 | 2/2 | - | 571 | 32 |

## B. Regenerate / edit: tokens reprocessed (ttft s)

| model | backend | cfg | ctx | regen | regen2 | edit-last | edit-early | back-to-original |
|---|---|---|---|---|---|---|---|---|
| gemma-4-31b-qat | sycl | ckpt-default | 3115 | 1 (0.593) | 1 (0.653) | 14 (1.795) | 15 (1.874) | 15 (1.924) |
| gemma-4-31b-qat | sycl | ckpt0 | 3113 | 1 (0.065) | 1 (0.065) | 14 (1.164) | 15 (1.088) | 15 (1.088) |
| gemma-4-31b-qat | vulkan | ckpt-default | 3113 | 1 (49.015) | 1 (49.409) | 14 (98.887) | 15 (98.579) | 15 (97.117) |
| gemma-4-31b-qat | vulkan | ckpt0 | 3113 | 1 (0.07) | 1 (0.069) | 14 (0.784) | 15 (0.772) | 15 (0.776) |
| qwen3.8-27b | sycl | ckpt-default | 3121 | 4 (0.219) | 4 (0.217) | 1531 (2.12) | 1531 (2.121) | 1531 (2.12) |
| qwen3.8-27b | sycl | ckpt0 | 3121 | 3121 (3.833) | 3121 (3.812) | 3121 (3.814) | 3121 (3.814) | 3121 (3.814) |
| muse-glimmer | sycl | ckpt-default | 3146 | 1 (0.204) | 1 (0.204) | 8 (0.34) | 9 (0.361) | 9 (0.361) |
| muse-glimmer | sycl | ckpt0 | 3146 | 1 (0.177) | 1 (0.176) | 8 (0.296) | 9 (0.578) | 9 (0.574) |

## C. Canary at ub 2048 vs Phase 5 baseline (flag > 5%)

| model | test | baseline | now | drift | flag |
|---|---|---|---|---|---|
| qwen3.8-27b | pp512 | 639.98 | 639.27 | -0.1% | ok |
| qwen3.8-27b | tg128 | 23.69 | 23.67 | -0.1% | ok |
| muse-glimmer | pp512 | 690.81 | 689.71 | -0.2% | ok |
| muse-glimmer | tg128 | 25.64 | 25.7 | +0.2% | ok |
