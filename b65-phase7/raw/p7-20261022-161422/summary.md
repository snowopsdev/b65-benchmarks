# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| A1g vLLM sym_int4 graphs | 512 | 0.4 | 1441.6 | 28.2 | 162.5 | 0 |
| A1g vLLM sym_int4 graphs | 4096 | 2.8 | 1454.1 | 29.6 | 177.1 | 0 |
| A1g vLLM sym_int4 graphs | 16384 | 12.2 | 1347.8 | 29.0 | 188.1 | 0 |
| A1g vLLM sym_int4 graphs | 32768 | 26.5 | 1237.0 | 25.9 | 190.8 | 0 |
| A3g vLLM sym_int4 + MTP graphs | 512 | 0.4 | 1212.8 | 45.3 | 160.0 | 0 |
| A3g vLLM sym_int4 + MTP graphs | 4096 | 2.9 | 1392.6 | 48.6 | 174.0 | 0 |
| A3g vLLM sym_int4 + MTP graphs | 16384 | 12.6 | 1304.4 | 45.0 | 185.7 | 0 |
| A3g vLLM sym_int4 + MTP graphs | 32768 | 27.4 | 1196.7 | 57.4 | 195.9 | 0 |

## Concurrency (512-token prompts)

| label | streams | aggregate tok/s | per-stream decode tok/s | TTFT s |
|---|---|---|---|---|
| A1g vLLM sym_int4 graphs | 1 | 25.1 | 25.9 | 0.4 |
| A1g vLLM sym_int4 graphs | 2 | 53.0 | 27.5 | 0.6 |
| A1g vLLM sym_int4 graphs | 4 | 98.4 | 28.2 | 1.4 |
| A1g vLLM sym_int4 graphs | 8 | 151.9 | 22.3 | 2.3 |
| A3g vLLM sym_int4 + MTP graphs | 1 | 51.5 | 56.1 | 0.4 |
| A3g vLLM sym_int4 + MTP graphs | 2 | 64.6 | 46.4 | 2.2 |
| A3g vLLM sym_int4 + MTP graphs | 4 | 134.7 | 46.3 | 1.5 |
| A3g vLLM sym_int4 + MTP graphs | 8 | 197.0 | 35.9 | 2.2 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| A1g vLLM sym_int4 graphs | 30/30 | 25.1 |
| A3g vLLM sym_int4 + MTP graphs | 30/30 | 63.3 |
