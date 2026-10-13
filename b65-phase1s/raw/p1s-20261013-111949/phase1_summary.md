# Phase 1 summary (p1s-20261013-111949)

## Decode tok/s by context depth (sycl, fa=1; OOM = did not fit)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 22.45 | 20.42 | 19.77 | 18.28 | 16.07 |
| muse-glimmer | 25.69 | 24.64 | 24.32 | 23.56 | 22.28 |
| qwen3.8-27b | 23.67 | 22.22 | 20.80 | 18.63 | 15.27 |

## Decode board W (timed reps)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 174.8 | 174.2 | 173.9 | 171.6 | 168.8 |
| muse-glimmer | 197.6 | 196.1 | 195.8 | 193.5 | 190.2 |
| qwen3.8-27b | 191.3 | 187.5 | 184.0 | 176.7 | 164.5 |

## llama-server (median of reps)

| Model | Prompt tokens | TTFT s | Prompt tok/s | Gen tok/s | Board W |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 513 | 2.81 | 182 | 21.58 | 160 |
| gemma-4-31b-qat | 4097 | 14.13 | 290 | 19.92 | 159 |
| gemma-4-31b-qat | 16385 | 58.13 | 282 | 17.83 | 156 |
| muse-glimmer | 513 | 0.87 | 592 | 25.43 | 195 |
| muse-glimmer | 4097 | 6.78 | 605 | 24.52 | 185 |
| muse-glimmer | 16385 | 28.51 | 576 | 23.42 | 180 |
| qwen3.8-27b | 512 | 0.96 | 536 | 23.36 | 190 |
| qwen3.8-27b | 4096 | 6.94 | 591 | 22.08 | 183 |
| qwen3.8-27b | 16384 | 28.89 | 568 | 18.54 | 179 |

## Idle board power with model loaded (30 s)

| Model | W |
|---|---|
| qwen3.8-27b | 44.9 |
| gemma-4-31b-qat | 44.9 |
| muse-glimmer | 44.9 |
