# Phase 7: other engines on the B65 (Intel llm-scaler vLLM, Strata)

Goal: find out whether llama.cpp SYCL is still the best way to run the B65, using the same client and tests on every engine. There are two challengers:

- **[intel/llm-scaler](https://github.com/intel/llm-scaler)**: Intel's official vLLM for Arc Pro B-series. It runs in Docker.
- **[Niko1221/Strata](https://github.com/Niko1221/Strata)**: a community engine built for one model family, Qwen3.8-Flash-Next (125B MoE).

## What was confirmed (2026-10-22)
| | Intel llm-scaler (vLLM) | Strata |
|---|---|---|
| Who | Intel, Apache-2.0 | One community author (Niko1221), MIT |
| What | vLLM 0.26.1-dev for XPU in `intel/llm-scaler-vllm:1.5` (the same build as `0.26.0-b2`, digest `52218ad8…`, 31.7 GB unpacked). It serves any supported Hugging Face model. | Its own engine, which reuses parts of ggml, for **Qwen3.8-Flash-Next only**: expert cache, speculative drafts. Intel support is "experimental" and has to be built from source with SYCL. |
| Official cards | Arc Pro B60 and B70, on Ubuntu 24.04 with Intel's offline driver installer. The B65 is not listed. | Tested on the B70 and A750. Community reports cover the B50, B580 and B60. The B65 is not listed. |
| Weights | Safetensors only, no GGUF. Quantization happens online when the model loads (`--quantization sym_int4` or `fp8`), or the weights come pre-quantized (FP8/AWQ/GPTQ). | GGUF (GSQ-RCO quants) plus files Strata prepares itself. |
| Fit for the B65 | Same die as the B70 (BMG-G31, `8086:e222`). **Probe passed on this Arch host**: `p7probe-20261022-115506` shows torch 2.12 XPU seeing exactly one device, `Intel(R) Graphics [0xe222]` with 31.9 GiB, inside the container. | AOT target `bmg-g31` is the B65's die. |
| Published reference | Registry B70, Qwen3.8-27B, on 0xSero's exl3xpu image, which is built on **the same vLLM commit** (`g568afb3a1`): 75 tok/s at C1 with MTP k=3, 410 tok/s aggregate at C16. llama.cpp on the same card: 25.0 at C1, 56.8 at C8. | The author's B70 numbers: Coder IQ1_M decode 70–78 tok/s against 23–25 for llama.cpp on the same GGUF, and about 790 tok/s prefill. |

Phase 2's plan had "vLLM on XPU" as a stretch step. It never ran ([phase2.md](../findings/phase2.md)).

## Steps
| Step | What | Size / time | Done when |
|---|---|---|---|
| 0 ✔ | `probe.sh`: does the llm-scaler container see the B65? | 7.8 GB pull | PASS (above) |
| 1 ✔ | `oai_bench.py`: one OpenAI-API client for every engine (speed, conc, coding, summary) | — | Tested on a CPU llama-server (Qwen3-0.6B): exact prompt lengths, `ignore_eos` honored |
| 2 ✔ | **Track A, dense 27B** (Qwen3.8-27B): download `Qwen/Qwen3.8-27B` in BF16 | 55.6 GB | sha256 manifest written |
| 2a ✔ | A0: llama.cpp SYCL b11574, Q4_K_M, recipe flags (`-fa on -b 2048 -ub 2048`). This is the baseline, rerun through the new client. | ~40 min | speed + conc + coding |
| 2b ✔ | A1: llm-scaler, `--quantization sym_int4`, Intel's 4-bit and the like-for-like match for Q4_K_M | ~1 h incl. load | same |
| 2c ✔ | A2: llm-scaler, `--quantization fp8`, 8-bit. It may not fit with a useful context on 32 GB, and either way is a result. | ~1 h | same, or a recorded no-fit |
| 2d ✔ | A3 (stretch): A1 + MTP, `--speculative-config '{"method":"qwen3_5_mtp","num_speculative_tokens":3}'`. Intel has verified MTP on Qwen3.6 only. | ~1 h | coding suite only (real text) |
| 2e ✔ | A4 (optional reference): the registry's exl3xpu image, Qwen3.8-27B EXL3 4 bpw + MTP, to see what the B70's 75 tok/s becomes on the B65 | 15.7 GB, ~1 h | same |
| 3 ✔ | Delete the BF16 weights. **Track B, Flash-Next 125B MoE**: build Strata's `strata-sycl-dev` image with AOT `bmg-g31`, then `./setup.sh --backend sycl --family coder` | 13 GB image + 59.3 GB GGUF | Strata answers on :8080 |
| 3a ✔ | B1: Strata, Coder IQ1_M, all experts in VRAM, its speculative drafts on (default) | ~1 h | speed + conc + coding |
| 3b ✔ | B2: B1 without the MTP layer (`--spec 2`; the native pack refuses `--spec 0`) | ~40 min | speed + coding |
| 3c ✔ | B3: llama.cpp SYCL, the **same GGUF**, all layers on the B65 | ~40 min | speed + coding |
| 2f ✔ | Added after the first results: A1g / A3g (graphs, with `patches/sym_int4.py`), A2b (fp8, 512-token chunks), the MTP draft-length sweep A3k2–A3k6 (coding only), and A5 (the winner, k=5, in full) | | |
| 2g ✔ | Added before publishing: llama.cpp's own speculative decoding, so the baseline is like-for-like. A0m3 (MTP k=3, full), A0mk2–A0mk6 (coding sweep, plus an A0mk3 repeat), B3n (n-gram drafts on Flash-Next) | ~50 min | speed + conc + coding |
| 4 ✔ | `oai_bench.py summary`, [findings/phase7.md](../findings/phase7.md), dashboard tab `/p7`, share cards (`/share#p7`, PNGs in `charts/phase7/` via `export_cards.sh`) | — | — |

Tracks A and B can't share the disk: 152 GB is free, and A (55.6) + B (59.3 + 13) plus Strata's prepared files leaves almost nothing. Run A, delete, then run B.

## Tests (identical for every engine, `oai_bench.py`)
- **speed**: one request at a time. Prompts of 512, 4K, 16K and 32K tokens, 256 tokens generated, 1 warmup + 3 reps. TTFT, prefill tok/s (= prompt / TTFT) and decode tok/s are all timed on the client from the stream. Prompts are windows of this repo's own markdown, cut to exact length with the model's `tokenizer.json`. Each rep starts at a different offset, so no prefix cache can answer it.
- **conc**: 1, 2, 4 and 8 requests released together, each a 512-token prompt with 256 tokens out, 3 reps. Records aggregate tok/s and per-stream decode. This is where vLLM is supposed to shine.
- **coding**: `tasks/coding.json` (the Phase 5 set, 10 tasks × 3 tries, thinking off, the same system message). The **pass rate is the quality gate**, which catches fast-but-wrong engines and broken AOT builds. Its decode speed is the honest number for speculative decoding, because acceptance depends on real content.
- **Board power** from the xe `card` energy counter (`--energy`), as in earlier phases. **Peak VRAM** from the Phase 1.5 memwatch.

## Decision rules
- **Single user (C1):** an engine replaces llama.cpp SYCL for a model only if decode is at least +10%, coding passes are within 2 of 30, and the 32K prompt works.
- **Several clients or agents at once:** report the C4/C8 aggregate on its own. A vLLM win there is a reason to run it as a shared server, not for chat.
- **Strata:** if its B70 claim (about 3× llama.cpp on the same file) holds on the B65, Flash-Next becomes a usable model on this 48 GB box. Phase 1.5 ruled it out on the registry's SGLang recipe, which needs 63 GB RAM.

## Known pitfalls
- **Device mapping:** the B65 here is `card0` + `renderD129` (PCI `0000:06:00.0`). `renderD128` is the 3080, but Intel's single-GPU example maps `renderD128`, so map by PCI path as `probe.sh` does.
- **Free the B65 first:** Unsloth Studio's Muse llama-server (port 36799) holds about 19 GB of it.
- **Strata on `xe`:** a request that needs more VRAM than the card has can stall the whole host. Keep about 1.5 GB free (`--vram-reserve-mib`), and never ask for more context than was configured.
- **AOT on Battlemage:** llama.cpp AOT builds produced gibberish in Phase 2, and Strata's Intel engine is AOT `bmg-g31`. The coding gate is what catches that.
- **Speculative decoding inflates easy text:** the speed suite's `ignore_eos` continuations of markdown are not natural answers. Quote MTP and Strata-draft gains from the coding suite only, and run Strata both ways (B1/B2).
- **vLLM defaults:** prefix caching is on by default, so pass `--no-enable-prefix-caching` for speed and conc. Loading includes online quantization and graph capture (minutes); the warmup request absorbs the rest.
- **Not like-for-like quantization:** Q4_K_M (about 4.8 bpw, k-quants) is not the same as `sym_int4` (4-bit symmetric, group-wise). The coding gate is the check on that, and the summary names the quantization in every label.
- Docker in agent shells: `echo "docker …" | newgrp docker`. Long runs go in `systemd-run --user` units.

## Files
| file | what |
|---|---|
| `probe.sh` | step 0: B65-only device mapping, prints OS, compute-runtime, torch.xpu and vLLM versions into `raw/p7probe-*` |
| `oai_bench.py` | the client: `speed`, `conc`, `coding`, `summary` |
| `quality.py`, `tasks/coding.json` | copied from Phase 5 (grader and tasks), unchanged |
| `phase7.sh` | the runner: every part (A0–A5, A0m*/A0mk* llama.cpp MTP, A1g/A2b/A3g, A3k2–A3k6, B1–B3, B3n), `PARTS="..."`, B65-only device mapping, VRAM watcher, per-run `raw/p7-*` |
| `patches/sym_int4.py`, `.diff` | llm-scaler 1.5's `sym_int4.py` with its two `logger.info_once` calls in `apply()` made no-ops, so graph mode loads |
| `export_cards.sh` | renders the Phase 7 share cards to `charts/phase7/*.png` (needs the dashboard and `FINAL`) |
| `FINAL` | marks Phase 7 complete: the share page only releases its numbers once this exists |
