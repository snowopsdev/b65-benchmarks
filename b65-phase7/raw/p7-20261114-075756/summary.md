# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A5 vLLM sym_int4 + MTP k=5 graphs | 512 | 0.4 | 1167.1 | 38.3 | 167.5 | 0 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 4096 | 3.0 | 1387.3 | 52.3 | 181.2 | 0 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 16384 | 12.6 | 1301.0 | 48.4 | 191.5 | 0 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 32768 | 27.4 | 1194.1 | 50.4 | 195.6 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A5 vLLM sym_int4 + MTP k=5 graphs | 1 | 44.3 | 47.7 | 0.4 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 2 | 67.7 | 43.7 | 2.0 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 4 | 126.1 | 39.9 | 1.5 |
| A5 vLLM sym_int4 + MTP k=5 graphs | 8 | 116.7 | 28.8 | 2.1 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A5 vLLM sym_int4 + MTP k=5 graphs | 29/30 | 70.9 |
