# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A0 llama.cpp SYCL Q4_K_M | 512 | 1.4 | 379.2 | 23.1 | 169.5 | 0 |
| A0 llama.cpp SYCL Q4_K_M | 4096 | 5.8 | 710.2 | 22.2 | 172.5 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A0 llama.cpp SYCL Q4_K_M | 1 | 16.4 | 23.4 | 1.2 |
| A0 llama.cpp SYCL Q4_K_M | 2 | 25.5 | 15.1 | 0.7 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A0 llama.cpp SYCL Q4_K_M | 2/2 | 23.6 |
