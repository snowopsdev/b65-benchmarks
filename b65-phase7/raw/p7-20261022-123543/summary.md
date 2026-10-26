# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A0 llama.cpp SYCL Q4_K_M | 512 | 1.1 | 450.7 | 23.1 | 184.2 | 0 |
| A0 llama.cpp SYCL Q4_K_M | 4096 | 5.3 | 769.5 | 22.2 | 187.4 | 0 |
| A0 llama.cpp SYCL Q4_K_M | 16384 | 21.3 | 768.3 | 18.5 | 184.4 | 0 |
| A0 llama.cpp SYCL Q4_K_M | 32768 | 46.5 | 704.0 | 15.1 | 182.1 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A0 llama.cpp SYCL Q4_K_M | 1 | 21.0 | 23.1 | 1.1 |
| A0 llama.cpp SYCL Q4_K_M | 2 | 29.8 | 16.5 | 1.7 |
| A0 llama.cpp SYCL Q4_K_M | 4 | 39.1 | 11.2 | 3.3 |
| A0 llama.cpp SYCL Q4_K_M | 8 | 37.3 | 5.2 | 6.2 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A0 llama.cpp SYCL Q4_K_M | 30/30 | 24.0 |
