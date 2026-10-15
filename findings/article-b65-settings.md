<!--
Hugging Face community article draft.
- Use the H1 as the editor's title; paste the remaining Markdown into the body.
- Evidence links are public, commit-pinned GitHub URLs at https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2 (tag: b65-evidence-2026-10-15). They work when the Markdown is pasted into the Hub editor.
- Optional cover: https://raw.githubusercontent.com/snowopsdev/b65-benchmarks/db9c9d25dd8b318098e36e65c391c09869123ef2/charts/conclusion/b65-sum-banner.png. Upload it through the article editor.
- Authoring format: https://huggingface.co/docs/hub/blog-articles
-->

# Running 30B-class GGUF models on Intel's Arc Pro B65: SYCL vs. Vulkan and the settings I'd use

I wanted to know what Intel's 32 GB Arc Pro B65 could actually do with local models: how quickly it reads a long prompt, how generation holds up as the conversation grows, and which settings make a difference in everyday use.

So I tested three 4-bit GGUF models on two llama.cpp backends, then followed up on the results that looked wrong. The main experiments ran on October 12–13, 2026: seven numbered phases, from 0 through 6, plus focused follow-ups.

The setup I landed on is **SYCL with flash attention on, a 2048-token micro-batch, all layers on the GPU, and a 32K context window**. Leave context checkpoints at their default for chat. For Qwen coding tasks, turn thinking off.

On this setup, Qwen and Muse reached the first token of a 16K-token prompt in about **20.5 seconds**, compared with about **42 seconds** on the Vulkan reference. Gemma took **30.8 seconds**, compared with **49.4 seconds**, with checkpoints disabled in both of those Gemma measurements.

Those results come from several experiments. Below, I've separated the backend comparison, the later tuning, and the quality checks so it's clear what each number measures.

## The setup I'd start with

With a SYCL build of llama.cpp and Intel's oneAPI runtime installed, run this from the llama.cpp checkout in Bash. Replace the model path and check that `level_zero:0` is your B65:

```bash
source /opt/intel/oneapi/setvars.sh --force
sycl-ls

export ONEAPI_DEVICE_SELECTOR=level_zero:0
export UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1

./build-sycl/bin/llama-server \
  -m /absolute/path/to/model.gguf \
  -ngl 99 -c 32768 -np 1 --jinja \
  -fa on -b 2048 -ub 2048
```

Here, `-b` is the logical batch size and `-ub` is the physical micro-batch size used to process a prompt. `-np 1` sets one parallel server slot. The measurements in this article are for one request at a time.

Two changes depend on the workload:

- **Qwen for coding:** add `--reasoning-budget 0`. The confirmation run also sent `"chat_template_kwargs": {"enable_thinking": false}` in each chat-completion request.
- **Gemma in append-only agent loops:** consider `--ctx-checkpoints 0`. Keep the default for chat interfaces where you edit earlier messages.

These are settings measured on the versions below. I would recheck them after a driver or llama.cpp update.

## Hardware, software, and model files

| Component | Tested configuration |
|---|---|
| GPU | ASRock Arc Pro B65 Creator, 32 GB, 200 W board power cap |
| Host | Ryzen 7 5700X, 48 GB RAM |
| OS | Arch Linux / Omarchy 4.0.4, kernel `7.2.5-3-omarchy` |
| llama.cpp | Build 11574, commit `8bb3cf0d2`, built separately for Vulkan and SYCL |
| Vulkan | Mesa 26.2.2 |
| SYCL | oneAPI DPC++ / oneMKL 2026.0, compute-runtime `26.31.39395.13`, Level Zero 1.32.0 |
| SYCL build | `GGML_SYCL=ON`, `GGML_SYCL_F16=ON`, JIT compilation |
| PCIe | PCIe 4.0 x4 through the X570 chipset; ReBAR enabled |

An RTX 3080 drove the display. It was excluded from inference, and the benchmark scripts checked the reported GPU on every successful test.

The GGUFs came from these Hub repositories:

| Model name used below | Hub repository | Tested file |
|---|---|---|
| Qwen 3.8 27B | [lmstudio-community/Qwen3.8-27B-GGUF](https://huggingface.co/lmstudio-community/Qwen3.8-27B-GGUF) | `Qwen3.8-27B-Q4_K_M.gguf` |
| Gemma 4 31B QAT | [lmstudio-community/gemma-4-31B-it-QAT-GGUF](https://huggingface.co/lmstudio-community/gemma-4-31B-it-QAT-GGUF) | `gemma-4-31B-it-QAT-Q4_0.gguf` |
| Muse Glimmer | [lmstudio-community/Muse-Glimmer-30B-GGUF](https://huggingface.co/lmstudio-community/Muse-Glimmer-30B-GGUF) | `Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf` |

Muse's repository is named 30B; the measured GGUF contains about 27.85 billion parameters, which is why the findings call it 28B. Model-file hashes are recorded in [the Phase 2 SHA-256 manifest](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase2/raw/p2-20261013-091509/models.sha256).

## How to read the results

**Prefill** is processing the input prompt. **Decode** is generating the answer, one token at a time. Both are reported in tokens per second; higher is faster.

For llama-bench, each test used its built-in warm-up followed by **five measured repeats**. The tables show **mean ± standard deviation (SD)**. For example, `100 ± 2` means an average of 100 tokens/second with a standard deviation of 2. Smaller SD means more consistent measurements within that test; it doesn't measure variation across different machines or driver versions.

The server latency tables use **time to first token (TTFT)**, measured from requests with prompt caching disabled, with the **median of three requests** reported. Lower is faster. These are separate measurements from llama-bench throughput.

The numbered phases are different experiments. They aren't the five repeats of a benchmark cell. Dry runs are excluded from the results.

## 1. Compare the backends before changing the batch size

Phase 2 used the same model files and llama.cpp commit, with `-b 2048 -ub 512`, all layers on the GPU, and F16 KV caches. It compared three configurations: Vulkan with flash attention off, SYCL with it off, and SYCL with it on.

The full matrix was three models × three configurations × seven tests: prefill at 512, 4,096, and 16,384 tokens, plus generation of 128 tokens at context depths of 0, 4K, 16K, and 32K.

### Processing a 16K-token prompt

Tokens/second, mean ± SD across five repeats:

| Model | Vulkan, FA off | SYCL, FA off | SYCL, FA on |
|---|---:|---:|---:|
| Qwen | 388.17 ± 0.035 | 571.17 ± 0.070 | 606.15 ± 0.071 |
| Gemma | 335.29 ± 0.123 | 384.63 ± 0.020 | 397.37 ± 0.016 |
| Muse | 429.73 ± 0.139 | 508.84 ± 0.041 | 608.70 ± 0.057 |

### Generating at 32K tokens of context

Tokens/second, mean ± SD across five repeats:

| Model | Vulkan, FA off | SYCL, FA off | SYCL, FA on |
|---|---:|---:|---:|
| Qwen | 16.16 ± 0.038 | 14.11 ± 0.002 | 15.26 ± 0.012 |
| Gemma | 12.84 ± 0.084 | 9.99 ± 0.116 | 16.06 ± 0.164 |
| Muse | 14.73 ± 0.062 | 15.74 ± 0.239 | 22.29 ± 0.002 |

Across the full matrix, SYCL with flash attention on improved prefill by **31.2%** and decode by **21.8%** relative to Vulkan with flash attention off. Those are arithmetic means of the percentage change in each matched cell: nine prefill cells and twelve decode cells.

| Model | Average prefill change | Average decode change |
|---|---:|---:|
| Qwen | +49.8% | +10.4% |
| Gemma | +9.0% | +18.6% |
| Muse | +34.9% | +36.5% |

There are exceptions worth keeping visible. **Qwen's 32K decode was 5.6% slower on SYCL.** Gemma's 512-token prefill was also slightly lower: 410.75 versus 414.48 tokens/second, a 0.9% difference.

I chose one SYCL configuration, with flash attention on, rather than selecting the fastest flash-attention setting separately for every cell.

Sources: [Phase 2 findings](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase2.md), [all 63 results, including SD and board power](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase2/raw/p2-20261013-091509/backend_compare.csv), and [the recorded environment](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase2/raw/p2-20261013-091509/env.txt).

## 2. Flash attention depends on the backend

On SYCL, flash attention improved decode by **18.5% on average** relative to SYCL with it disabled. Gemma at 32K went from 9.99 to 16.06 tokens/second, a 61% gain.

On the Vulkan build, it went the other way. Gemma's 16K prefill was about **38 tokens/second with flash attention on**, versus **335 with it off**.

For this software stack, my starting point is **FA on for SYCL, FA off for Vulkan**. I wouldn't carry that rule to another backend or build without measuring it.

Sources: [Phase 0.5](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase05.md) and [Phase 2](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase2.md).

## 3. A larger micro-batch improves prompt processing on SYCL

After choosing the backend, I raised the SYCL micro-batch from 512 to 2048, keeping `-b 2048`. At 16K, llama-bench prefill improved by about **35–55%**, depending on the model.

The later Phase 5 baseline confirmed these results:

| Model | SYCL FA on, ub 512 — Phase 2 | SYCL FA on, ub 2048 — Phase 5 |
|---|---:|---:|
| Qwen | 606.15 ± 0.071 | 824.33 ± 0.158 |
| Gemma | 397.37 ± 0.016 | 616.92 ± 0.101 |
| Muse | 608.70 ± 0.057 | 820.67 ± 0.098 |

Tokens/second, mean ± SD, five repeats. This table compares different runs; the same-run micro-batch checks are in [Phase 4](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase4.md) and [the Gemma diagnostic](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/gemma-sycl-diag.md).

The improvement carried over to llama-server:

| Model | Vulkan, ub 512 | SYCL, ub 512 | SYCL, ub 2048 |
|---|---:|---:|---:|
| Qwen | 42.22 s | 28.89 s | 20.48 s |
| Muse | 41.65 s | 28.51 s | 20.53 s |
| Gemma | 49.36 s | 58.13 s | 30.79 s |

These are **16K-prompt TTFT medians**, three requests per cell. Vulkan used FA off; SYCL used FA on. The Gemma rows used `--ctx-checkpoints 0`, including the diagnostic's ub-2048 result. The final chat recipe keeps checkpoints at their default; that exact Gemma combination wasn't measured in this TTFT table.

The larger micro-batch added **522 MiB for Qwen** and **675 MiB for Muse** to the server's recorded VRAM use at 32K. Gemma's VRAM wasn't recorded in the ub-2048 diagnostic. Qwen and Muse server generation stayed within about 2%; Gemma's generation was 5–6% slower at 4K and 16K, in exchange for the faster prefill.

On Vulkan, a larger micro-batch wasn't consistently better: Qwen gained about 10% at 16K, while Muse lost 36%. I kept the Vulkan reference at ub 512.

Sources: [Phase 4](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase4.md), [Phase 5 baseline](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase5.md), [the server rerun](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/ubserve.md), and [the Gemma diagnostic](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/gemma-sycl-diag.md).

## 4. Test regenerate and edit before disabling checkpoints

An append-only chat test made `--ctx-checkpoints 0` look like a useful default. Every setup reused its prompt cache, and every setup answered sooner with checkpoints disabled.

Then I tested regenerating a response and editing earlier messages.

With checkpoints off, **Qwen reprocessed the entire 9,413-token chat when regenerating**, taking **11.3 seconds** to the first token. With checkpoints at their default, it reprocessed four tokens and took **0.17 seconds**.

Editing an earlier turn caused a full reread in every checkpoints-off configuration. With checkpoints on, the server could reuse the prefix before the edit.

That changed the recommendation:

| Workload | Checkpoint setting I'd use |
|---|---|
| Qwen or Muse in a chat UI | Default |
| Gemma on SYCL in a chat UI | Default |
| Gemma on SYCL in an append-only agent loop | `--ctx-checkpoints 0` |
| Gemma on Vulkan | `--ctx-checkpoints 0` |

Gemma's append-only SYCL turns took **3.24 seconds with checkpoints off**, versus **5.96 seconds with them on**. On Vulkan, Gemma had a much larger checkpoint cost: its 512-token TTFT fell from about **25.3 seconds to 1.36 seconds** when checkpoints were disabled.

Sources: [the initial server follow-up](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase1.md#gemma-llama-server-rerun-p1-swa-20261013-081841), [Phase 5 append-only chat](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase5.md), and [Phase 6 regenerate/edit tests](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase6.md).

## 5. Qwen coding improved with thinking off

The quality checks were small: ten coding tasks, ten tool-calling tasks, five notes-recall tasks, and five writing prompts.

With thinking on and a 2,048-token output cap, Qwen and Gemma each passed **9/10 coding tasks**. Both failures exhausted the budget while reasoning, before returning code. Muse passed 10/10.

In Phase 6, Qwen ran the same coding tasks with thinking disabled, a 4,096-token cap, and three attempts per task: one greedy attempt and two at temperature 0.3 with fixed seeds. It passed **10/10 greedy and 30/30 overall**, with a median answer length of **130 tokens**. The greedy pass took **73 seconds**, compared with **305 seconds** in the original test.

That supports thinking off for this Qwen coding workload. The follow-up also changed the micro-batch and token cap, so the timing isn't an isolated measurement of the thinking switch. It doesn't establish a general coding score beyond these ten tasks.

Muse ignored both thinking-off controls and returned reasoning on all 30 attempts. Its 30/30 result is **with thinking on**.

If you keep thinking enabled, leave room for it. Gemma completed its failed task in 3,326 tokens; Qwen needed up to 9,650 tokens on the same task in the budget sweep. A 4K cap wasn't enough for every Qwen attempt.

Sources: [Phase 3](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase3.md), [Phase 5's token-budget sweep](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase5.md), and [Phase 6 coding confirmation](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase6.md).

## Which model I'd use

**Muse for general use and longer conversations.** In the SYCL context-depth rerun at ub 512, decode fell from 25.69 tokens/second at empty context to 22.28 at 32K. It also finished the original quality set fastest and passed all ten coding tasks.

**Qwen with thinking off for concise coding answers.** It passed every attempt in the coding follow-up. Its long-context decode is the caveat: 15.27 tokens/second at 32K in the SYCL rerun, behind Vulkan at that depth.

**Gemma for the writing I tested.** It ranked first on three of five prompts in my blind ranking. That was one rater and five prompts, with a possible presentation-order bias recorded in the findings. It's a preference from this test, not a general writing leaderboard.

All three scored **10/10 on tool calling** and **5/5 on notes recall**, so those checks didn't separate them.

Sources: [Phase 1S context-depth results](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase1s.md), [Phase 3 quality checks](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase3.md), and [Phase 6](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase6.md).

## Power and memory

SYCL decode drew about **165–199 W of GPU board power**. Muse ran close to the card's 200 W cap. Stable repeat speeds showed no obvious decline, but I didn't independently characterize throttling.

Loaded idle was roughly **43–45 W**. These readings come from the xe driver's board-energy sensor. They don't include the rest of the PC.

At 32K context, recorded server VRAM was **18,104 MiB for Qwen** and **16,755 MiB for Muse** at ub 2048. Gemma used **20,916 MiB at ub 512**; I didn't record its ub-2048 footprint. All three loaded and ran at 32K, but these aren't three memory measurements of the complete final recipe.

Sources: [Phase 2 power](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase2.md), [Phase 1S memory](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/phase1s.md), and [the ub-2048 server rerun](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/ubserve.md).

## The experiment log

The [benchmark repository](https://github.com/snowopsdev/b65-benchmarks) contains the scripts, raw measurements, model hashes, and findings. The evidence links below pin commit `db9c9d25dd8b318098e36e65c391c09869123ef2` so they keep identifying the files used for this article.

This is the order of the main runs and follow-ups behind the recommendations. Each run link points to its raw artifacts; [the findings index](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/findings/README.md) also lists excluded dry runs.

| Experiment | What changed or was tested | Raw run |
|---|---|---|
| Phase 0 | Vulkan baseline, FA on | [20261012-140638](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/raw/20261012-140638) |
| Phase 0.5 | Vulkan FA off vs. on, plus decode follow-up | [p05-20261012-163413](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase05/raw/p05-20261012-163413), [p05b-20261012-173906](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase05/raw/p05b-20261012-173906) |
| Phase 1 | Context depth, server latency, loaded idle | [p1-20261012-180308](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase1/raw/p1-20261012-180308) |
| Phase 1 follow-up | Gemma checkpoints and full sliding-window cache | [p1-swa-20261013-081841](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase1/raw/p1-swa-20261013-081841) |
| Phase 2 | Same-commit Vulkan/SYCL comparison | [p2-20261013-091509](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase2/raw/p2-20261013-091509) |
| Phase 1S | Context and server tests on SYCL, FA on | [p1s-20261013-111949](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase1s/raw/p1s-20261013-111949) |
| Gemma diagnostic | SYCL micro-batch, checkpoints, context, and FA | [gd-20261013-123933](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-gemmadiag/raw/gd-20261013-123933) |
| Phase 3 | Coding, tools, recall, blind writing | [p3-20261013-135609](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase3/raw/p3-20261013-135609) |
| Phase 4 | Baseline drift and micro-batch controls | [p4-20261013-150339](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase4/raw/p4-20261013-150339) |
| Server follow-up | Qwen/Muse latency at ub 2048 | [us-20261013-161926](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-ubserve/raw/us-20261013-161926) |
| Phase 5 | New baseline, short prompts, append-only chat, Qwen budgets | [p5-20261013-171039](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase5/raw/p5-20261013-171039) |
| Phase 6 | Coding confirmation, regenerate/edit, baseline check | [p6-20261013-211819](https://github.com/snowopsdev/b65-benchmarks/tree/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase6/raw/p6-20261013-211819) |

The final settings are assembled from these experiments. There wasn't one run that measured every metric with every final flag. In particular, the 32K decode curves used ub 512; the tuned latency tests used ub 2048; and Gemma's tuned latency test disabled checkpoints.

## Reproducing the build and a throughput test

The SYCL build used the following CMake settings. Install the compiler, libraries, and Intel GPU runtime first; [llama.cpp's SYCL documentation](https://github.com/ggml-org/llama.cpp/blob/8bb3cf0d2/docs/backend/SYCL.md) covers the prerequisites. The tested Arch package versions and local build script are in [the Phase 2 kit](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase2/README.md).

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
git checkout 8bb3cf0d2
source /opt/intel/oneapi/setvars.sh --force

cmake -S . -B build-sycl -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx \
  -DGGML_SYCL=ON -DGGML_SYCL_F16=ON -DLLAMA_CURL=OFF
cmake --build build-sycl -j --target llama-bench llama-server

export ONEAPI_DEVICE_SELECTOR=level_zero:0
export UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1
./build-sycl/bin/llama-bench --version
./build-sycl/bin/llama-bench --list-devices
```

After confirming that the selected device is the B65, a Phase 2-style 16K prefill measurement is:

```bash
./build-sycl/bin/llama-bench \
  -m /absolute/path/to/model.gguf \
  -ngl 99 -fa 1 -b 2048 -ub 512 \
  -p 16384 -n 0 -r 5 -o jsonl
```

Change only `-ub 512` to `-ub 2048` to check the micro-batch gain. The JSONL records the model, device, build, settings, mean, SD, and individual samples. Compare the file's SHA-256 with the manifest before treating it as the same model.

For the full backend matrix, power sampling, server requests, or quality tests, use the corresponding phase scripts and recorded environments. After updates, I use [the canary](https://github.com/snowopsdev/b65-benchmarks/blob/db9c9d25dd8b318098e36e65c391c09869123ef2/b65-phase4/README.md) to check a small set of throughput measurements against the saved baseline.

## What I'd still test

The B65 ran all three of these 30B-class Q4 models at 32K context. SYCL with FA on was the stronger starting point for this stack, and the larger micro-batch made long prompts much less painful.

The remaining questions are specific:

- Why does Qwen lose to Vulkan on decode at 32K?
- Why does Gemma have a roughly 1.1-second SYCL request floor on tiny uncached prompts?
- What does a PCIe x16 slot change? The x4 link's effect wasn't measured.
- How do newer llama.cpp builds and other engines, including vLLM, compare?
- Do the coding and writing preferences hold on larger, independently scored task sets?

If you're testing an Arc card, share the exact model file, backend, build, context depth, and batch settings with your results. I'd like to compare the cases where these recommendations hold—and the ones where they change.
