# Phase 1 summary

## Decode tok/s by context depth (fa=0; OOM = did not fit)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| qwen3.8-27b | 18.33 | - | - | - | - |

## Decode board W (timed reps)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| qwen3.8-27b | 161.7 | - | - | - | - |

## llama-server (median of reps)

| Model | Prompt tokens | TTFT s | Prompt tok/s | Gen tok/s | Board W |
|---|---|---|---|---|---|
| qwen3.8-27b | 512 | 1.54 | 333 | 18.97 | 160 |

## Idle board power with model loaded (30 s)

| Model | W |
|---|---|
| qwen3.8-27b | 43.9 |
