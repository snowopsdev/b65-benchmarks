# Phase 1 summary

## Decode tok/s by context depth (fa=0; OOM = did not fit)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 19.16 | 17.39 | 16.94 | 16.00 | 12.84 |
| muse-glimmer | 20.94 | 18.71 | 18.03 | 16.79 | 14.73 |
| qwen3.8-27b | 19.08 | 18.85 | 18.43 | 17.67 | 16.14 |

## Decode board W (timed reps)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 180.8 | 179.1 | 179.1 | 181.9 | 181.5 |
| muse-glimmer | 173.8 | 170.5 | 170.3 | 168.7 | 166.2 |
| qwen3.8-27b | 167.9 | 170.6 | 172.0 | 173.8 | 176.4 |

## llama-server (median of reps)

| Model | Prompt tokens | TTFT s | Prompt tok/s | Gen tok/s | Board W |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 513 | 25.25 | 20 | 17.58 | 86 |
| gemma-4-31b-qat | 4097 | 108.30 | 38 | 16.52 | 72 |
| gemma-4-31b-qat | 16385 | 146.58 | 112 | 13.64 | 93 |
| muse-glimmer | 513 | 1.71 | 301 | 20.12 | 161 |
| muse-glimmer | 4097 | 11.78 | 348 | 18.57 | 149 |
| muse-glimmer | 16385 | 41.65 | 394 | 16.22 | 157 |
| qwen3.8-27b | 512 | 1.31 | 391 | 18.97 | 166 |
| qwen3.8-27b | 4096 | 9.70 | 422 | 18.32 | 160 |
| qwen3.8-27b | 16384 | 42.22 | 388 | 16.33 | 158 |

## Idle board power with model loaded (30 s)

| Model | W |
|---|---|
| qwen3.8-27b | 44.9 |
| gemma-4-31b-qat | 44.9 |
| muse-glimmer | 45.0 |
