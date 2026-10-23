# Arc Pro B65: Phase 7 findings (other engines: Intel llm-scaler vLLM, exl3xpu, Strata)

The question: is llama.cpp SYCL still the best way to run the B65? We used one OpenAI-API client (`b65-phase7/oai_bench.py`) and the same tests on every engine, on 2026-10-22.

**Runs:**

| run | parts | notes |
|---|---|---|
| `p7-20261022-123543` | A0 | A1–A3 failed at start: the oneCCL device-mapping problem, below |
| `p7-20261022-141831` | A1, A2, A3 | Intel's container as shipped; graph mode crashed, so the eager fallbacks ran |
| `p7-20261022-161422` | A1g, A3g, A2b | graphs with the `sym_int4` patch; fp8 with small chunks |
| `p7-20261022-165453` | A4, A3k2, A3k4 | 0xSero's exl3xpu image; MTP draft-length sweep |
| `p7-20261022-172120` | B3 (B1, B2 failed: a config-path bug in the runner) | llama.cpp on the Flash-Next GGUF |
| `p7-20261022-173629` | B1, A3k5, A3k6 (B2 failed: Strata refuses `--spec 0` on this pack) | Strata with its MTP drafts; the rest of the MTP sweep |
| `p7-20261022-175606` | B2 | Strata without the MTP layer (`--spec 2`, suffix drafts only) |
| `p7-20261022-180341` | A5 | the sweep's winner (MTP k=5) measured in full |
| `p7-20261023-093219` | A0m3, A0mk2, A0mk4, A0mk5, A0mk6, B3n | llama.cpp's own speculative decoding: MTP on the 27B (full suite at k=3, coding sweep k=2–6), n-gram drafts on Flash-Next |
| `p7-20261023-101139` | A0mk3 | repeat of llama.cpp MTP k=3 on the coding suite (the full run's VRAM watcher recorded nothing) |

Dry run: `p7-dry-20261022-123145`. The dashboard (`/p7`) shows any run. The share page merges them: one result per part, the latest full run.

**Versions and setup:**
- **Host and card:** kernel 7.2.8-9-omarchy, the B65 at `0000:06:00.0` (`card0`, `renderD129`). `renderD128` is the 3080, which nothing here touches.
- **llama.cpp:** b11574 (`8bb3cf0d2`), SYCL.
- **Intel llm-scaler:** `intel/llm-scaler-vllm:1.5` (`sha256:52218ad8…`), with vLLM `0.26.1.dev0+g568afb3a1` and torch 2.12 XPU.
- **exl3xpu:** `ghcr.io/0xsero/exl3xpu@sha256:21412bdd…` (exl3xpu 0.1.0, built on the same vLLM).
- **Strata:** `011c9e6` (2026-10-21), its SYCL port built AOT for `bmg-g31` in its `strata-sycl-dev` image.

**Weights:**
- **Qwen3.8-27B:** BF16 at `1d4bf0f2`, for the vLLM parts. The llama.cpp baseline uses the Q4_K_M GGUF from Phases 0–6.
- **EXL3 4.00 bpw:** `turboderp/Qwen3.8-27B-exl3@113cf7ab`.
- **Flash-Next Coder IQ1_M:** `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF@5348543e`, the revision Strata pins.

## How everything was measured

The same client was used for every engine. Every number is timed from the stream on the client, so no engine's own timings are trusted over another's.
- **speed:** one request at a time, with prompts of 512, 4K, 16K and 32K tokens, 256 generated, 1 warmup and 3 reps, reporting medians.
  - **Prompts:** windows of this repo's markdown, cut to exact length with the model's own `tokenizer.json`. Each rep starts at a different offset, and prefix caching is off on every vLLM engine.
  - **Track A:** `/v1/completions` with `ignore_eos`.
  - **Track B:** Strata has neither, so it uses a chat request ("continue this document"), and llama.cpp gets the identical request.
- **conc:** 1, 2, 4 and 8 requests released together, each a 512-token prompt with 256 tokens out. Reports the aggregate tok/s. Track A only, since Strata serves one request at a time.
- **coding:** Phase 5's 10 tasks × 3 tries, with thinking off and Phase 5's system message. The pass rate is the quality gate. **Decode on these answers is the honest single-user number**: speculative decoding (MTP) depends on the text, and code is the real use. The `ignore_eos` markdown continuations in *speed* flatter it at 32K.
- **Power and VRAM:**
  - **Power:** board power from the xe `card` energy counter.
  - **VRAM:** the peak resident VRAM of the server's processes (xe fdinfo), read inside the container for Docker engines.
  - **Caveat:** vLLM claims `--gpu-memory-utilization` of the card up front, so its VRAM is a setting, not a need.

## Track A: Qwen3.8 27B, 4-bit, four engines

| part | engine and settings | load | decode 512 | decode 32K | first token 32K | 8 users, total | coding pass | coding tok/s | VRAM peak (GiB) |
|---|---|---|---|---|---|---|---|---|---|
| A0 | llama.cpp SYCL, Q4_K_M, `-fa on -b 2048 -ub 2048 -c 65536 -np 8 -kvu` | 10 s | 23.1 | 15.1 | 46.5 s | 37.3 | 30/30 | **24.0** | 22.1 |
| **A0m3** | **llama.cpp SYCL, as A0 + its own MTP (`--spec-type draft-mtp --spec-draft-n-max 3`)** | 9 s | 34.1 | 27.4 | 49.3 s | 37.4 | 30/30 | **43.1** | 25.8 (A0mk3) |
| A0mk2 / A0mk3 / A0mk4 / A0mk5 / A0mk6 | llama.cpp + MTP k = 2 / 3 / 4 / 5 / 6, coding only | 9–42 s | | | | | 30 of 30 each | 39.0 / 42.2 / 39.8 / 38.5 / 35.0 | 24.7 / 25.8 / 27.0 / 28.2 / 29.3 |
| A1 | Intel vLLM, `sym_int4`, **eager** (as shipped: graphs crash) | 189 s | 19.3 | 17.9 | 26.6 s | 139.2 | 30/30 | 19.8 | 29.7 |
| A1g | Intel vLLM, `sym_int4`, **graphs** (patched) | 354 s | 28.2 | 25.9 | 26.5 s | 151.9 | 30/30 | 25.1 | 27.3 |
| A3 | Intel vLLM, `sym_int4` + MTP k=3, eager | 197 s | 41.5 | 54.5 | 27.5 s | 194.3 | 30/30 | 58.5 | 30.2 |
| A3g | Intel vLLM, `sym_int4` + MTP k=3, graphs (patched) | 464 s | 45.3 | 57.4 | 27.4 s | 197.0 | 30/30 | 63.3 | 27.7 |
| A4 | exl3xpu, EXL3 4 bpw + MTP k=3, fp8 KV (0xSero's B70 config) | 369 s | 42.0 | 44.6 | **18.5 s** | **207.5** | 30/30 | 51.1 | 31.7 |
| A2 | Intel vLLM, `fp8` | 183 s | 18.3 | – | – | – | crashed | – | 31.8 |
| A2b | Intel vLLM, `fp8`, 512-token chunks | – | – | – | – | – | no fit | – | – |
| A3k2 / A3g / A3k4 / A3k5 / A3k6 | Intel vLLM, graphs (patched), MTP k = 2 / 3 / 4 / 5 / 6, coding only | 328 / 464 / 318 / 327 / 332 s | | | | | 30 / 30 / 30 / 29 / 30 of 30 | 58.5 / 63.3 / 68.7 / **74.3** / 71.8 | 27.6 |
| **A5** | **Intel vLLM, `sym_int4` + MTP k=5, graphs (patched)** | 367 s | 45.2 | 51.6 | 27.5 s | 136.8 | **29/30** | **74.2** | 27.7 |

Medians of 3. Decode is in tok/s. "8 users" is the aggregate tok/s of 8 requests released together.

1. **Intel's own container, with MTP and graphs, is the fastest single-user setup on the B65.**
   - **The numbers:** 74.2 tok/s while writing code with MTP k=5 (A5), against **43.1 for llama.cpp with its own MTP (1.7×)** and 24.0 for llama.cpp without it (3.1×). It passed 29/30 against 30/30; the miss is one sampled try, and the greedy try passed.
   - **The fair comparison is MTP against MTP.** The first version of this write-up compared A5 with plain llama.cpp (3.1×). This llama.cpp build has its own MTP (`draft-mtp`), and the Q4_K_M GGUF carries the model's `nextn` layer, so A0m3 is the like-for-like baseline.
   - **At Intel's documented k=3 (A3g):** 63.3 tok/s and 30/30.
   - **MTP is most of that:** it gives 2.5–3× over the same engine without it (A1g 25.1). MTP is the model's own multi-token-prediction head, used for speculative decoding.
   - **Graphs add 8%** at k=3 (58.5 → 63.3).
2. **llama.cpp's own MTP is one flag and nearly doubles its single-user speed.**
   - **On code:** 24.0 → 43.1 tok/s (1.8×) at k=3, still 30/30. On markdown continuation 23.1 → 34.1 at 512 and 15.1 → 27.4 at 32K. Load time is unchanged (9 s), and VRAM rises by about 3.7 GiB.
   - **Draft length:** k=3 is best on code (39.0 / 42.2 / 39.8 / 38.5 / 35.0 for k=2–6; the k=3 repeat gave 42.2 against 43.1 in the full run). vLLM's MTP peaks later (k=5) and higher.
   - **Several users: no help.** 37.4 tok/s total at 8 requests against 37.3 without it, and lower at 4 (23.6 against 39.1). Turn it on for one user, not for a shared server.
   - **Prompt reading: unchanged.** A 32K prompt starts in 49.3 s against 46.5 s.
3. **Intel's vLLM as shipped is slower than llama.cpp without MTP.** A1 decodes at 19.3–19.8 tok/s against 23–24.
   - **Why:** graph mode never loads with `sym_int4` in llm-scaler 1.5 (below). Eager mode, which Intel's README uses anyway (`--enforce-eager`), costs **46%** of decode at 512 (19.3 → 28.2).
   - **Patched:** with the two-line patch (`b65-phase7/patches/sym_int4.py`), plain 4-bit vLLM beats llama.cpp's decode by 22% at 512 and 72% at 32K.
4. **Reading prompts:**
   - **vLLM vs llama.cpp:** vLLM reads them about 2× faster, 1,230–1,450 against 450–770 tok/s. A 32K prompt answers in 26.5 s against 46.5 s.
   - **exl3xpu is fastest:** its int8 prefill linears and oneDNN attention reach 1,775–2,150 tok/s, so a 32K prompt starts in 18.5 s.
5. **Several users: vLLM keeps scaling, llama.cpp doesn't.**
   - **llama.cpp** peaks at about 4 requests (39.1 tok/s total) and drops at 8 (37.3).
   - **vLLM** reaches 139–197 at 8 (**4–5×**), and exl3xpu reaches 207.5.
   - **Per-stream speed holds:** A1g's per-stream decode at 8 users (22.3) is about llama.cpp's single-user speed.
6. **exl3xpu (0xSero) is second for one user, and first for long prompts and many users.**
   - **Speed:** 51.1 tok/s on code.
   - **Download:** a 16 GB EXL3 download against 56 GB of BF16 for Intel's online quantization.
   - **Context:** fp8 KV, so its config fits 256K context.
   - **Single-user deficit:** its MTP drafts from an EXL3-quantized head, while Intel's quantizes the BF16 head on load. That is a likely reason for the gap, not measured here.
   - **Against its B70 number:** its registry recipe quotes 63–77 tok/s at C1 on a B70 (thinking on, its own prompts). On the B65, with our client, it does 42–45 on markdown and 51.1 on code.
7. **fp8 doesn't fit a 32 GB card for a 27B model.**
   - **Memory:** 27.6 GiB of weights leaves about 2 GiB.
   - **A2:** it loaded at 8K context, answered 512-token prompts (18.3 tok/s), then ran out of GPU memory on the first 4K prompt and died.
   - **A2b:** with 512-token prefill chunks it ran out of memory while allocating its KV cache. The coding suite got nothing from either.
8. **Power and efficiency:**
   - **Power:** the vLLM engines draw the same 160–195 W as llama.cpp.
   - **Energy per token:** on a 4K prompt, A3g makes 48.6 tok/s at 174 W against 22.2 at 187 W, about **2.4× the tokens per joule**.
9. **Load times:** llama.cpp loads in 10 s. Intel's vLLM takes 3–8 minutes (online quantization of 56 GB of BF16, then graph capture), and exl3xpu about 6.

**MTP draft length (k): 5 is best on code.**
- **The sweep:** each extra draft token adds about 5 tok/s up to k=5 (58.5 → 63.3 → 68.7 → 74.3), then k=6 drops to 71.8.
- **Quality holds:** speculative decoding doesn't change what the model would have written. The one miss at k=5 is task c08 on a sampled try (temperature 0.3), and the greedy try passed.
- **A5** is k=5 run through the whole suite: 29/30 (the same sampled c08 miss) at **74.2 tok/s**, 1.7× llama.cpp with its own MTP (3.1× without). Markdown decode and prompt reading match k=3. **For several users k=5 is worse:** 136.8 tok/s at 8 requests against 197.0 for k=3, because drafts that get rejected cost compute when requests are batched. So k=5 is the setting for one user, and k=3 for a shared server.

## Track B: Qwen3.8-Flash-Next Coder (125B MoE, IQ1_M), Strata vs llama.cpp on the same GGUF

Strata only runs Qwen3.8-Flash-Next (a 125B MoE with 256 experts in the Coder release), so this track compares engines on that model.
- **The file:** ISTA-DASLab's Coder IQ1_M GGUF (2 shards, 58.4 GB) for both engines.
- **Context:** 40,960 for both, so the 32K prompt fits.
- **Strata:** the setup's own config, minus `--ple-io ram` (below): 4,096-token prompt chunks, int8 KV, a 2 GiB VRAM reserve, experts streamed into VRAM.
- **llama.cpp:** the flags Strata's docs use for their own llama.cpp comparison:
  - `-ngl 999 --override-tensor per_layer_token_embd=CPU`: every layer on the card except shard 2's 28.8 GB n-gram table, which stays mmapped from the SSD
  - `-fa on`, q8_0 KV
  - `SYCL_CACHE_PERSISTENT=0`
- **Speed test:** chat mode with a "continue this document" request, because Strata has no `/v1/completions`. Every row here generated the full 256 tokens.

| part | engine | load | decode 512 | decode 32K | prefill 4K–32K | first token 32K | coding pass | coding tok/s | board W | VRAM peak (GiB) |
|---|---|---|---|---|---|---|---|---|---|---|
| B3 | llama.cpp SYCL | 93 s | 18.7 | 14.4 | 400–428 | 81.9 s | 27/30 | 19.4 | 121–150 | 28.9 |
| B3n | llama.cpp SYCL + n-gram drafts (`--spec-type ngram-mod`) | 72 s | 19.0 | 24.7 | 402–425 | 81.7 s | 27/30 | 20.5 | 123–153 | 29.8 |
| B2 | Strata, no MTP (`--spec 2`, suffix drafts only) | 97 s | 37.9 | 40.9 | 941–1,022 | 32.9 s | 26/30 | 38.6 | 138–153 | 28.5 |
| **B1** | **Strata, MTP drafts (setup's default `--spec 4 --spec-min-p 0.5`)** | 50 s | 49.9 | 55.0 | 945–1,023 | 32.9 s | 26/30 | **73.7** | 144–154 | 29.6 |

1. **Strata runs a 125B MoE on one B65 at 73.7 tok/s writing code, 3.6× llama.cpp at its best on the same file (20.5 with n-gram drafts; 19.4 without, 3.8×).**
   - **llama.cpp can't use MTP here:** this GGUF has no `nextn` layer (Strata ships its MTP head separately). Its n-gram drafts (`ngram-mod`, the `--spec-default`) barely help: 19.4 → 20.5 on code, 27/30 both.
   - **Without its MTP layer** it still decodes at 38–41 tok/s, about 2× llama.cpp without drafts. That run still drafts from Strata's suffix cache, which this pack can't turn off, so it isn't a drafts-off number. Prompt reading, which no drafting touches, is the clean sign that the engine itself is faster.
   - **Prompt reading:** about 2.4× faster, 941–1,023 against 400–428 tok/s. A 32K prompt starts in 33 s against 82 s.
2. **Quality is the same on both engines.**
   - **Strata:** both Strata runs miss task c08 on every try, plus one sampled c02.
   - **llama.cpp:** misses c08 on every try.
   - **The rest:** everything else passes on both. The c08 miss belongs to the model at this quant, not to an engine.
3. **Strata's B70 claim holds on the B65.**
   - **Decode:** its docs report 70–78 tok/s for greedy engine runs on a B70, and through the API we measured 73.7 on code.
   - **Prefill:** its docs say 790 tok/s at 2K, and we measured 945–1,023 at 4K–32K with a newer engine.
   - **llama.cpp on this model** is slower here than on the B70 (18.7–19.4 against 23–25).
4. **Strata's AOT build for `bmg-g31` (the B70's chip) runs on the B65 unchanged, and its answers pass.** The coding gate is what would catch a broken AOT build.
5. **Limits:**
   - **One request at a time** in this setup. Strata has an opt-in `--parallel N` that wasn't tested here.
   - **One model family.**
   - **Built from source:** a 13 GB dev image.
   - **No pictures on Intel by default:** its docs report that a picture reset the B70.

## What broke, and the fixes

1. **Intel's vLLM container died at start on this host (`ze_fd_manager.cpp: fill_device_fds`).**
   - **Cause:** even with one GPU, vLLM's `all_reduce` initialises oneCCL, which opens every render node listed in `/dev/dri/by-path`. The host's directory also lists the 3080's nodes, which aren't in the container.
   - **Intel's single-GPU example:** it maps `renderD128`, which on this host is the 3080.
   - **Fix:** map only the B65's `card0` and `renderD129`, and mount a by-path directory holding only the B65's two links (`phase7.sh`, `BYPATH`).
2. **Graph mode never loads with `--quantization sym_int4` in llm-scaler 1.5.**
   - **Cause:** `sym_int4.py`'s `apply()` calls `logger.info_once(...)` inside the region torch.compile traces, and dynamo rejects it (`gb0291`).
   - **Fix:** `patches/sym_int4.py` turns those two calls into no-ops. Nothing else changes, and the result is +46% decode and identical pass rates.
3. **fp8 doesn't fit** (above). Also, when its engine died during KV allocation, vLLM's API server stayed up and never became healthy. The runner now treats "Engine core initialization failed" in the log as a failed load.
4. **Strata's pinned GGUF was replaced upstream.**
   - **What changed:** ISTA-DASLab replaced the Coder IQ1_M shard 1 on 2026-10-19 ("updated expert-pruned model"), and Strata `011c9e6` still pins the 2026-09-29 file and its expert profile.
   - **Fix:** we downloaded the pinned revision (`5348543e`), and both sha256s match Strata's.
5. **Strata's setup took this 46 GB PC for one with 1024 GB of RAM.**
   - **Cause:** the Intel wrapper's placeholder RAM value reached the rule that keeps the 29 GB n-gram table in RAM (`--ple-io ram`).
   - **Fix:** the runner drops that flag, so the table stays on the SSD, as in Strata's own B70 numbers.
6. **Strata's native IQ pack refuses `--spec 0`** ("needs --native SHARD1, --spec T (T >= 2)"), so drafting can't be fully off. "No MTP" is the closest equivalent: `--spec 2` without the MTP layer, leaving only the suffix drafter, which Strata's docs measured at about 9% acceptance on the B70.
7. **Our runner's own bug:** the first B1/B2 attempt passed a config path relative to the run folder after `cd`-ing into Strata's checkout, and failed in 5 s. It was fixed and re-run.

## Settings that win (Qwen3.8 27B, one B65)

- **One user, fastest: Intel llm-scaler vLLM 1.5,** 74.2 tok/s writing code, with:
  - `--quantization sym_int4`
  - MTP (`--speculative-config '{"method":"qwen3_5_mtp","num_speculative_tokens":5}'`). For a server shared by several users, use `3`.
  - graphs on: the `sym_int4.py` patch, and no `--enforce-eager`
  - `--max-model-len 40960 --gpu-memory-utilization 0.9`
  - devices: only the B65's two nodes plus a filtered by-path
- **Long prompts and many users:** exl3xpu, 0xSero's image and config, unchanged.
- **Simplest:** llama.cpp SYCL with the Phase 0–6 recipe plus `--spec-type draft-mtp --spec-draft-n-max 3` for one user. It loads in 10 s, runs any GGUF, and writes code at 43 tok/s (24 without MTP). Leave MTP off for a shared server.

Full commands are in [recommended-settings.md](recommended-settings.md#phase-7-other-engines).
