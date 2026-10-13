# Phase 4 canary (p4-dry-20261013-150059)

```
run_id=p4-dry-20261013-150059
date=2026-10-13T15:00:59-04:00
kernel=7.2.5-3-omarchy
mesa=mesa 1:26.2.2-1
oneapi=Intel(R) oneAPI DPC++/C++ Compiler 2026.0.0 (2026.0.0.20260331)
level_zero=level-zero-loader 1.32.0-1 intel-compute-runtime 26.31.39395.13-1 
llama_sycl=version: 0.6.0-dev (build 11574, commit 8bb3cf0d2)
omarchy=4.0.4-1
sycl_device=  SYCL0: Intel(R) Arc(TM) Pro B65 Graphics (32656 MiB, 32583 MiB free)
reps=1
models=qwen3.8-27b
ubcheck=0
dry=1
energy_file=/sys/class/hwmon/hwmon6/energy1_input
```

## Drift vs baseline (SYCL fa1, ub 512; flag = more than 5%)

| Model | Test | Baseline | Now | Drift | W | Flag |
|---|---|---|---|---|---|---|
| qwen3.8-27b | pp512 | 639.96 | 639.22 | -0.1% | 176.8 | ok |
| qwen3.8-27b | pp16384 | 606.15 | 605.99 | -0.0% | 182.5 | ok |
| qwen3.8-27b | tg128 | 23.68 | 23.70 | +0.1% | 192.5 | ok |
| qwen3.8-27b | tg128@d16384 | 18.63 | 18.64 | +0.1% | 175.4 | ok |

**0 flagged.** Nothing drifted more than 5%.
