# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 512 | 1.3 | 401.7 | 34.1 | 175.4 | 0 |
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 4096 | 5.8 | 711.7 | 32.5 | 181.9 | 0 |
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 16384 | 22.4 | 730.6 | 30.9 | 185.5 | 0 |
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 32768 | 49.2 | 665.4 | 27.4 | 184.2 | 0 |
| B3n llama.cpp SYCL Coder IQ1_M + ngram-mod | 512 | 1.8 | 298.3 | 19.0 | 122.5 | 0 |
| B3n llama.cpp SYCL Coder IQ1_M + ngram-mod | 4096 | 10.0 | 413.7 | 18.4 | 132.9 | 0 |
| B3n llama.cpp SYCL Coder IQ1_M + ngram-mod | 16384 | 38.7 | 424.8 | 16.5 | 144.7 | 0 |
| B3n llama.cpp SYCL Coder IQ1_M + ngram-mod | 32768 | 81.7 | 401.6 | 24.7 | 152.8 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 1 | 32.1 | 37.3 | 1.2 |
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 2 | 33.3 | 19.4 | 1.6 |
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 4 | 23.6 | 6.5 | 3.2 |
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 8 | 37.4 | 5.4 | 5.4 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A0m3 llama.cpp SYCL Q4_K_M + MTP k=3 | 30/30 | 43.1 |
| A0mk2 llama.cpp SYCL Q4_K_M + MTP k=2 | 30/30 | 39.0 |
| A0mk4 llama.cpp SYCL Q4_K_M + MTP k=4 | 30/30 | 39.8 |
| A0mk5 llama.cpp SYCL Q4_K_M + MTP k=5 | 30/30 | 38.5 |
| A0mk6 llama.cpp SYCL Q4_K_M + MTP k=6 | 30/30 | 35.0 |
| B3n llama.cpp SYCL Coder IQ1_M + ngram-mod | 27/30 | 20.5 |
