# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A5 vLLM sym_int4 + MTP k=5 graphs | 512 | 0.4 | 1169.0 | 45.2 | 168.8 | 0 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 4096 | 3.0 | 1382.2 | 47.0 | 179.8 | 0 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 16384 | 12.6 | 1295.9 | 50.6 | 191.5 | 0 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 32768 | 27.5 | 1189.7 | 51.6 | 195.0 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A5 vLLM sym_int4 + MTP k=5 graphs | 1 | 65.0 | 72.5 | 0.4 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 2 | 56.3 | 39.2 | 2.4 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 4 | 116.9 | 42.0 | 1.5 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 8 | 136.8 | 32.5 | 2.1 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A5 vLLM sym_int4 + MTP k=5 graphs | 29/30 | 74.2 |
