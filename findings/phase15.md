# Arc Pro B65: Phase 1.5 findings (registry recipes)

Runs on 2026-10-14. All three models pass the six lab gates of [local-ai-registry](https://github.com/sybil-solutions/local-ai-registry), both on our native SYCL build and in the pinned official image, so the B65 has three recipes ready on a local registry branch. Nothing is pushed; opening the PR is AJ's call.

- **Unblocked by the registry itself:** Phase 1.5 waited on @0xSero about llama.cpp recipes. The registry merged a llama.cpp SYCL recipe for the Arc B390 on 2026-10-10 (`a8e64af`), so llama.cpp counts.
- **Not the recipe kit's own target:** the kit's first target (Qwen3.8-Flash-Next, experts in RAM) needs 68 GB free RAM and an NVMe table; this machine has 48 GB.
- **Kit:** `b65-phase15/` (see its README). Registry clone `~/src/ext/local-ai-registry-20261014`, branch `b65-arc-pro-recipes`, commit `77e44e5` on top of upstream `7c15d9c`.

## The gates
load · chat · reasoning (thinking returned separately, 17 × 23 = 391) · tools (calls `get_weather` for Paris, then uses the result) · context (finds a code planted at 85% of the window) · speed (decode ≥ 15 tok/s over the first 30 s of an uncapped answer, empty context, one user).

## Setup
- **Card:** ASRock Arc Pro B65 Creator 32 GB; Ryzen 7 5700X, PCIe 4.0 x4.
- **Settings (both runs):** 32K context, flash attention on, `-b 2048 -ub 2048`, all layers on the GPU, one slot, `--jinja`, thinking on (the reasoning gate needs it).
- **Weights:** lmstudio-community GGUFs, pinned to the commits whose files match ours byte for byte: Qwen3.8-27B-GGUF `5a7da681`, gemma-4-31B-it-QAT-GGUF `12e5eae7`, Muse-Glimmer-30B-GGUF `c34cb737`.
- **Pre-check** (`p15pre-20261014-131018`): the registry's `gates()` unmodified, against native llama.cpp b11574 (`8bb3cf0d2`).
- **Registry run** (`p15reg-20261014-141612`): `lab.py try --on endpoint` against the official `ghcr.io/ggml-org/llama.cpp` server-intel image, b11515, digest `86b37d26…` (the B390 recipe's image), started like the registry SDK does (`--device /dev/dri`), published on 127.0.0.1 only. Docker 29.7.2.

## Results
| Model | Run | Gates | Decode (tok/s) | Context prompt | Context request | Speed answer |
|---|---|---|---|---|---|---|
| Qwen3.8 27B Q4_K_M | native b11574 | 6/6 | 23.8 | 25,782 tokens | 41.6 s | 16,177 tokens, 770 s |
| | image b11515 | **6/6** | **23.6** | 25,782 | 36.0 s | 11,564 tokens, 545 s |
| Gemma 4 31B QAT Q4_0 | native b11574 | 6/6 | 21.8 | 25,746 | 58.0 s | 1,214 tokens, 60 s |
| | image b11515 | **6/6** | **21.4** | 25,746 | 66.9 s | 1,307 tokens, 66 s |
| Muse Glimmer 28B Q4_K_M | native b11574 | 6/6 | 25.4 | 21,127 | 161.7 s | 3,973 tokens, 160 s |
| | image b11515 | **6/6** | **25.2** | 21,127 | 42.0 s | 1,188 tokens, 48 s |

1. **Every model clears the 15 tok/s line by a wide margin** (21.4–25.2 tok/s in the image), and the image decodes within 2% of our native build.
2. **The registry's "prefill" is not prefill speed.** It divides the context prompt by the whole request time, thinking included: the recipes say Qwen 716, Muse 503, Gemma 385 tok/s, but the same Muse prompt gave 131 in the pre-check because it thought for longer before answering. For real prefill numbers use Phase 4+ ([ubserve.md](ubserve.md)).
3. **The speed gate's uncapped answer is long for Qwen:** 11.6–16.2K tokens (9–13 min) for "a detailed 600-word story". Only the first 30 s count, so it doesn't change the result; it does make Qwen's run the slowest.

## Recipes (local registry branch, not pushed)
- `registry/cards/intel/intel-arc-pro-b65-32gb.json`: Intel Arc Pro B65, 32 GB, 608 GB/s (published spec).
- Three frozen launches `registry/launches/llama.cpp-sycl-<model>-32k-arc-pro-b65.json` and three recipes in `registry/recipes/intel/intel-arc-pro-b65-32gb/`, each with its proof (`on: owner`, `launch_sha256`, gates, tps, prefill).
- `make` regenerated `dist/catalog.json` and the plugin exports; the catalog lists the B65 with picks Qwen, Gemma, Muse. `make check` passes (320 recipes; SDKs agree on 64 cards).
- Evidence JSONs are copied to `b65-phase15/raw/p15reg-20261014-141612/`. The registry doesn't commit `lab/runs/` (the B390 PR didn't either).

## Open, for AJ
- **Open the PR** to sybil-solutions/local-ai-registry (public). The commit mirrors the B390 PR's file set.
- **Hardware page:** the site's `/gpu/<id>/` page needs a photo with source attribution in `site/lib/hardware-photos.json`; not added.
- **Longer contexts:** these recipes declare 32K, the measured recommendation. A 64K or 128K variant would need its own run (the context gate fills 85% of the window).
