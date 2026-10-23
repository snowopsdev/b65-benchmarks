# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A4 exl3xpu EXL3 4bpw + MTP | 512 | 0.4 | 1309.2 | 42.0 | 157.8 | 0 |
| A4 exl3xpu EXL3 4bpw + MTP | 4096 | 1.9 | 2148.1 | 43.9 | 164.7 | 0 |
| A4 exl3xpu EXL3 4bpw + MTP | 16384 | 8.2 | 1993.1 | 42.0 | 177.0 | 0 |
| A4 exl3xpu EXL3 4bpw + MTP | 32768 | 18.5 | 1774.9 | 44.6 | 182.2 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A4 exl3xpu EXL3 4bpw + MTP | 1 | 39.2 | 41.5 | 0.4 |
| A4 exl3xpu EXL3 4bpw + MTP | 2 | 60.3 | 39.8 | 1.8 |
| A4 exl3xpu EXL3 4bpw + MTP | 4 | 105.5 | 35.4 | 1.0 |
| A4 exl3xpu EXL3 4bpw + MTP | 8 | 207.5 | 36.0 | 1.8 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A4 exl3xpu EXL3 4bpw + MTP | 30/30 | 51.1 |
| A3k2 vLLM sym_int4 + MTP k=2 graphs | 30/30 | 58.5 |
| A3k4 vLLM sym_int4 + MTP k=4 graphs | 30/30 | 68.7 |
