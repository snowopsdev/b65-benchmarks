# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A1 vLLM sym_int4 | 512 | 0.4 | 1433.3 | 19.3 | 181.2 | 0 |
| A1 vLLM sym_int4 | 4096 | 2.8 | 1440.3 | 19.2 | 186.0 | 0 |
| A1 vLLM sym_int4 | 16384 | 12.2 | 1340.2 | 18.6 | 191.2 | 0 |
| A1 vLLM sym_int4 | 32768 | 26.6 | 1231.6 | 17.9 | 193.8 | 0 |
| A2 vLLM fp8 | 512 | 0.4 | 1455.5 | 18.2 | 181.7 | 0 |
| A2 vLLM fp8 | 4096 | 0.0 | 0.0 | 0.0 | 119.5 | 1 |
| A3 vLLM sym_int4 + MTP | 512 | 0.4 | 1187.3 | 41.5 | 155.4 | 0 |
| A3 vLLM sym_int4 + MTP | 4096 | 3.0 | 1384.4 | 45.8 | 171.0 | 0 |
| A3 vLLM sym_int4 + MTP | 16384 | 12.6 | 1300.6 | 46.4 | 188.2 | 0 |
| A3 vLLM sym_int4 + MTP | 32768 | 27.5 | 1191.4 | 54.5 | 195.2 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A1 vLLM sym_int4 | 1 | 18.9 | 19.3 | 0.4 |
| A1 vLLM sym_int4 | 2 | 44.6 | 23.2 | 0.6 |
| A1 vLLM sym_int4 | 4 | 83.0 | 23.3 | 1.4 |
| A1 vLLM sym_int4 | 8 | 139.2 | 20.5 | 2.3 |
| A3 vLLM sym_int4 + MTP | 1 | 47.9 | 51.8 | 0.4 |
| A3 vLLM sym_int4 + MTP | 2 | 57.1 | 42.3 | 2.2 |
| A3 vLLM sym_int4 + MTP | 4 | 128.1 | 47.0 | 1.5 |
| A3 vLLM sym_int4 + MTP | 8 | 194.3 | 35.8 | 2.4 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A1 vLLM sym_int4 | 30/30 | 19.8 |
| A2 vLLM fp8 | 0/30 | – |
| A3 vLLM sym_int4 + MTP | 30/30 | 58.5 |
