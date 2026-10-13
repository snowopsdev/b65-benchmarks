# Phase 4 canary (p4-20261013-150339)

```
run_id=p4-20261013-150339
date=2026-10-13T15:03:39-04:00
kernel=7.2.5-3-omarchy
mesa=mesa 1:26.2.2-1
oneapi=Intel(R) oneAPI DPC++/C++ Compiler 2026.0.0 (2026.0.0.20260331)
level_zero=level-zero-loader 1.32.0-1 intel-compute-runtime 26.31.39395.13-1 
llama_sycl=version: 0.6.0-dev (build 11574, commit 8bb3cf0d2)
omarchy=4.0.4-1
sycl_device=  SYCL0: Intel(R) Arc(TM) Pro B65 Graphics (32656 MiB, 32583 MiB free)
reps=5
models=qwen3.8-27b muse-glimmer
ubcheck=1
dry=0
energy_file=/sys/class/hwmon/hwmon6/energy1_input
```

## Drift vs baseline (SYCL fa1, ub 512; flag = more than 5%)

| Model | Test | Baseline | Now | Drift | W | Flag |
|---|---|---|---|---|---|---|
| qwen3.8-27b | pp512 | 639.96 | 639.86 | -0.0% | 184.2 | ok |
| qwen3.8-27b | pp16384 | 606.15 | 605.94 | -0.0% | 185.7 | ok |
| qwen3.8-27b | tg128 | 23.68 | 23.69 | +0.0% | 195.4 | ok |
| qwen3.8-27b | tg128@d16384 | 18.63 | 18.64 | +0.1% | 177.4 | ok |
| muse-glimmer | pp512 | 691.22 | 690.61 | -0.1% | 184.0 | ok |
| muse-glimmer | pp16384 | 608.7 | 608.72 | +0.0% | 182.1 | ok |
| muse-glimmer | tg128 | 25.66 | 25.64 | -0.1% | 199.5 | ok |
| muse-glimmer | tg128@d16384 | 23.56 | 23.56 | +0.0% | 194.3 | ok |

## Micro-batch check

| Backend | Model | Test | ub | tok/s | W |
|---|---|---|---|---|---|
| sycl | qwen3.8-27b | pp4096 | 2048 | 890.74 | 197.0 |
| sycl | qwen3.8-27b | pp16384 | 2048 | 824.18 | 196.5 |
| sycl | qwen3.8-27b | tg128@d16384 | 2048 | 18.86 | 180.8 |
| vulkan | qwen3.8-27b | pp16384 | 512 | 388.16 | 156.8 |
| vulkan | qwen3.8-27b | pp16384 | 2048 | 428.7 | 166.8 |
| sycl | muse-glimmer | pp4096 | 2048 | 906.82 | 194.9 |
| sycl | muse-glimmer | pp16384 | 2048 | 820.69 | 193.5 |
| sycl | muse-glimmer | tg128@d16384 | 2048 | 23.44 | 193.9 |
| vulkan | muse-glimmer | pp16384 | 512 | 429.82 | 162.5 |
| vulkan | muse-glimmer | pp16384 | 2048 | 274.01 | 122.0 |
- qwen3.8-27b pp4096: ub2048 vs ub512 = +38.0%
- qwen3.8-27b pp16384: ub2048 vs ub512 = +36.0%
- qwen3.8-27b tg128@d16384: ub2048 vs ub512 = +1.2%
- muse-glimmer pp4096: ub2048 vs ub512 = +39.1%
- muse-glimmer pp16384: ub2048 vs ub512 = +34.8%
- muse-glimmer tg128@d16384: ub2048 vs ub512 = -0.5%

**0 flagged.** Nothing drifted more than 5%.
