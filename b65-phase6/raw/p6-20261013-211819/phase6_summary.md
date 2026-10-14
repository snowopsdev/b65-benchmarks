# Phase 6 summary (p6-20261013-211819)

```
run_id=p6-20261013-211819
date=2026-10-13T21:18:19-04:00
kernel=7.2.5-3-omarchy
mesa=mesa 1:26.2.2-1
oneapi=Intel(R) oneAPI DPC++/C++ Compiler 2026.0.0 (2026.0.0.20260331)
level_zero=level-zero-loader 1.32.0-1 intel-compute-runtime 26.31.39395.13-1 
llama_sycl=version: 0.6.0-dev (build 11574, commit 8bb3cf0d2)
vk_bin=/home/snowdesk/Projects/b65-benchmarks/b65-phase6/../vendor/llama.cpp/build/bin vk_index=1
sycl_device=  SYCL0: Intel(R) Arc(TM) Pro B65 Graphics (32656 MiB, 32583 MiB free)
parts_list=A B C
parts=A B C dry=0 reps=5 energy_file=/sys/class/hwmon/hwmon6/energy1_input
```

## A. Coding, thinking off (10 tasks x tries)

| model | pass | greedy pass | failed tasks | median tokens | total s |
|---|---|---|---|---|---|
| qwen3.8-27b | 30/30 | 10/10 | - | 130 | 203 |
| muse-glimmer | 30/30 | 10/10 | - | 440 | 531 |

## B. Regenerate / edit: tokens reprocessed (ttft s)

| model | backend | cfg | ctx | regen | regen2 | edit-last | edit-early | back-to-original |
|---|---|---|---|---|---|---|---|---|
| gemma-4-31b-qat | sycl | ckpt-default | 9386 | 1 (0.412) | 1 (0.354) | 14 (1.665) | 6236 (15.345) | 6236 (18.476) |
| gemma-4-31b-qat | sycl | ckpt0 | 9362 | 1 (0.089) | 1 (0.089) | 14 (1.202) | 9362 (17.991) | 9362 (18.267) |
| gemma-4-31b-qat | vulkan | ckpt-default | 9362 | 1 (49.375) | 1 (49.519) | 14 (99.071) | 5204 (135.502) | 5204 (135.364) |
| gemma-4-31b-qat | vulkan | ckpt0 | 9362 | 1 (0.093) | 1 (0.093) | 14 (0.84) | 9362 (78.355) | 9362 (78.543) |
| qwen3.8-27b | sycl | ckpt-default | 9413 | 4 (0.17) | 4 (0.168) | 1531 (2.215) | 6250 (10.062) | 1531 (3.172) |
| qwen3.8-27b | sycl | ckpt0 | 9413 | 9413 (11.339) | 9413 (11.322) | 9413 (11.322) | 9413 (11.517) | 9413 (11.656) |
| muse-glimmer | sycl | ckpt-default | 9502 | 1 (0.259) | 1 (0.259) | 8 (0.403) | 6292 (9.598) | 9 (0.723) |
| muse-glimmer | sycl | ckpt0 | 9502 | 1 (0.203) | 1 (0.203) | 8 (0.326) | 9502 (11.662) | 9502 (11.691) |

## C. Canary at ub 2048 vs Phase 5 baseline (flag > 5%)

| model | test | baseline | now | drift | flag |
|---|---|---|---|---|---|
| qwen3.8-27b | pp512 | 639.98 | 640.0 | +0.0% | ok |
| qwen3.8-27b | pp16384 | 824.33 | 824.13 | -0.0% | ok |
| qwen3.8-27b | tg128 | 23.69 | 23.69 | +0.0% | ok |
| qwen3.8-27b | tg128@d16384 | 18.86 | 18.86 | +0.0% | ok |
| muse-glimmer | pp512 | 690.81 | 690.87 | +0.0% | ok |
| muse-glimmer | pp16384 | 820.67 | 820.72 | +0.0% | ok |
| muse-glimmer | tg128 | 25.64 | 25.64 | +0.0% | ok |
| muse-glimmer | tg128@d16384 | 23.44 | 23.44 | +0.0% | ok |
