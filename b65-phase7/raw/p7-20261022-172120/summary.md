# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| B3 llama.cpp SYCL Coder IQ1_M | 512 | 1.9 | 283.9 | 18.7 | 121.4 | 0 |
| B3 llama.cpp SYCL Coder IQ1_M | 4096 | 10.0 | 411.7 | 18.4 | 132.2 | 0 |
| B3 llama.cpp SYCL Coder IQ1_M | 16384 | 38.4 | 428.2 | 16.6 | 146.3 | 0 |
| B3 llama.cpp SYCL Coder IQ1_M | 32768 | 81.9 | 400.6 | 14.4 | 150.0 | 0 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| B3 llama.cpp SYCL Coder IQ1_M | 27/30 | 19.4 |
