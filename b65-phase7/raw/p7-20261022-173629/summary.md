# Phase 7 summary (medians)

## Single stream

| label | prompt | TTFT s | prefill tok/s | decode tok/s | board W | short |
|---|---|---|---|---|---|---|
| B1 Strata Coder IQ1_M drafts on | 512 | 1.2 | 442.4 | 49.9 | 144.1 | 0 |
| B1 Strata Coder IQ1_M drafts on | 4096 | 4.4 | 945.0 | 48.6 | 145.5 | 0 |
| B1 Strata Coder IQ1_M drafts on | 16384 | 16.1 | 1022.5 | 81.8 | 153.6 | 0 |
| B1 Strata Coder IQ1_M drafts on | 32768 | 32.9 | 996.5 | 55.0 | 154.2 | 0 |

## Coding (thinking off)

| label | pass | decode tok/s on answers |
|---|---|---|
| B1 Strata Coder IQ1_M drafts on | 26/30 | 73.7 |
| A3k5 vLLM sym_int4 + MTP k=5 graphs | 29/30 | 74.3 |
| A3k6 vLLM sym_int4 + MTP k=6 graphs | 30/30 | 71.8 |
