# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 512 | 0.8 | 642.8 | 24.0 | 183.9 | 0 |
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 4096 | 4.5 | 901.0 | 22.9 | 186.6 | 0 |
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 16384 | 19.3 | 847.3 | 19.1 | 185.3 | 0 |
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 32768 | 42.0 | 780.3 | 15.6 | 185.9 | 0 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 512 | 0.8 | 612.0 | 52.7 | 167.0 | 0 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 4096 | 4.7 | 866.1 | 62.0 | 179.6 | 0 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 16384 | 20.4 | 805.0 | 48.0 | 186.5 | 0 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 32768 | 44.7 | 733.7 | 39.4 | 188.2 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 1 | 22.5 | 24.2 | 0.8 |
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 2 | 41.6 | 22.8 | 1.1 |
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 4 | 65.1 | 18.9 | 2.1 |
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 8 | 85.4 | 13.1 | 4.3 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 1 | 48.9 | 57.9 | 0.8 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 2 | 72.9 | 43.6 | 1.0 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 4 | 99.9 | 31.6 | 2.0 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 8 | 111.0 | 19.1 | 4.0 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| OA0mk3 llama.cpp b11574 SYCL Q4_K_M + MTP k=3 | 30/30 | 42.2 |
| NA0 llama.cpp v1.0.0 SYCL Q4_K_M | 30/30 | 24.7 |
| NA0m3 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=3 | 30/30 | 68.9 |
| NA0mk2 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=2 | 30/30 | 56.8 |
| NA0mk4 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=4 | 30/30 | 72.2 |
| NA0mk5 llama.cpp v1.0.0 SYCL Q4_K_M + MTP k=5 | 30/30 | 78.4 |
