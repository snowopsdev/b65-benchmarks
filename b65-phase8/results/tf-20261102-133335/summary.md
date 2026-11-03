# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| T1 | 512 | 0.4 | 1267.3 | 79.0 | – | 0 |
| T1 | 4096 | 3.0 | 1356.1 | 64.5 | – | 0 |
| T1 | 8192 | 6.2 | 1329.2 | 56.4 | – | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| T1 | 1 | 105.8 | 126.6 | 0.4 |
| T1 | 2 | 117.1 | 82.2 | 0.6 |
| T1 | 4 | 151.6 | 51.5 | 1.1 |
| T1 | 8 | 168.9 | 30.7 | 1.8 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| T1 | 30/30 | 157.5 |
