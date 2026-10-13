# Phase 1 summary (p1s-dry-20261013-111753)

## Decode tok/s by context depth (sycl, fa=1; OOM = did not fit)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| qwen3.8-27b | 23.68 | - | - | - | - |

## Decode board W (timed reps)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| qwen3.8-27b | 190.0 | - | - | - | - |

## llama-server (median of reps)

| Model | Prompt tokens | TTFT s | Prompt tok/s | Gen tok/s | Board W |
|---|---|---|---|---|---|
| qwen3.8-27b | 512 | 1.39 | 368 | 23.38 | 178 |

## Idle board power with model loaded (30 s)

| Model | W |
|---|---|
| qwen3.8-27b | 43.6 |
