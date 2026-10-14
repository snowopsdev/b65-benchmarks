# Arc Pro B65: Phase 1.5 findings (registry recipes)

Runs on 2026-10-14. All three models pass the six lab gates of [local-ai-registry](https://github.com/sybil-solutions/local-ai-registry), both on our native SYCL build and in the pinned official image, and at 64K and 128K too: nine B65 recipes, in [PR #260](https://github.com/sybil-solutions/local-ai-registry/pull/260) with the card; the hardware photo is its own [PR #264](https://github.com/sybil-solutions/local-ai-registry/pull/264) (one change per PR).

- **Unblocked by the registry itself:** Phase 1.5 waited on @0xSero about llama.cpp recipes. The registry merged a llama.cpp SYCL recipe for the Arc B390 on 2026-10-10 (`a8e64af`), so llama.cpp counts.
- **Not the recipe kit's own target:** the kit's first target (Qwen3.8-Flash-Next, experts in RAM) needs 68 GB free RAM and an NVMe table; this machine has 48 GB.
- **Kit:** `b65-phase15/` (see its README). Registry clone `~/src/ext/local-ai-registry-20261014`: branch `b65-arc-pro-recipes` (`9125d90` card + 32K, `3c20070` 64K/128K, rebased on upstream `c1ef238`) for PR #260 and `b65-arc-pro-photo` (`b92bf2c`) for PR #264, both pushed to the `snowopsdev` fork. `b65-pr260-backup` keeps the earlier combined branch.

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

## Longer contexts (`p15reg-20261014-154648`)
Same image, flags and weights; only `--ctx-size` changes (launch ids `…-64k-…`/`…-128k-…`). All six pass; the whole run took 53 min.

| Model | Context | Gates | Decode (tok/s) | Context prompt | Context request | Registry "prefill" | Speed answer |
|---|---|---|---|---|---|---|---|
| Qwen3.8 27B Q4_K_M | 128K | **6/6** | **23.6** | 106,294 tokens | 182.8 s | 581 | 7,146 tokens, 327 s |
| | 64K | **6/6** | **23.6** | 52,625 | 83.0 s | 634 | 14,179 tokens, 684 s |
| Gemma 4 31B QAT Q4_0 | 128K | **6/6** | **21.4** | 106,258 | 326.9 s | 325 | 1,320 tokens, 65 s |
| | 64K | **6/6** | **21.4** | 52,589 | 139.4 s | 377 | 1,317 tokens, 69 s |
| Muse Glimmer 28B Q4_K_M | 128K | **6/6** | **25.1** | 87,285 | 130.8 s | 667 | 1,269 tokens, 52 s |
| | 64K | **6/6** | **25.3** | 43,186 | 212.1 s | 204 | 3,590 tokens, 146 s |

1. **Decode doesn't change with the window** (the speed gate runs on an empty context): 23.6 / 21.4 / 25.1–25.3 tok/s at 32K, 64K and 128K.
2. **Everything fits in 32 GB at 128K**, Gemma included: its KV state at 128K is 10.7 GB (the server log's prompt-state size), plus 17.7 GB of weights.
3. **Muse's 128K is its trained maximum** (`context_length` 131072); Qwen and Gemma are trained to 256K, not tried here.
4. The 64K Muse "prefill" (204) is again thinking time: the request took longer at 64K than at 128K.
5. With these in the catalog, the B65's picks become Qwen 128K, Gemma 128K, Muse 64K. `make check` passes (SDKs agree on 317 recipes).

## Recipes
- `registry/cards/intel/intel-arc-pro-b65-32gb.json`: Intel Arc Pro B65, 32 GB, 608 GB/s (published spec).
- Three frozen launches `registry/launches/llama.cpp-sycl-<model>-32k-arc-pro-b65.json` and three recipes in `registry/recipes/intel/intel-arc-pro-b65-32gb/`, each with its proof (`on: owner`, `launch_sha256`, gates, tps, prefill).
- `make` regenerated `dist/catalog.json` and the plugin exports; the catalog lists the B65 with picks Qwen, Gemma, Muse. `make check` passes (320 recipes; SDKs agree on 64 cards).
- Evidence JSONs are copied to `b65-phase15/raw/p15reg-20261014-141612/`. The registry doesn't commit `lab/runs/` (the B390 PR didn't either).

## Evidence re-run for PR #260 (`p15reg-20261014-183825`)
0xSero asked for owner-run evidence, because the registry can't rent a B65: the `data/lab-runs/` records, plus the kit's `memwatch` log and `probe.py` output. The memory log has to come from the same run as the records, so all nine launches were re-run with the kit's `tools/memwatch.sh` (unmodified), a B65 VRAM log (xe DRM fdinfo, read inside the container) and one `probe.py`. All nine pass again, within 0.3 tok/s of the first run. The lab added the re-run as a second proof on each recipe. Pushed as `e67643b`, with the evidence in `data/sources/intel-arc-pro-b65-llamacpp-sycl/`, and answered on the PR (PCI id `8086:e222`).

| Launch | B65 VRAM peak (MiB) | Host MemAvailable start → min (GB) |
|---|---|---|
| Qwen 32K / 64K / 128K | 18,496 / 20,713 / 24,906 | 39.3→34.2 / 39.5→32.2 / 39.4→29.0 |
| Gemma 32K / 64K / 128K | 23,926 / 26,614 / **31,990** | 39.4→31.5 / 39.5→29.1 / 39.5→35.3 |
| Muse 32K / 64K / 128K | 17,826 / 17,857 / 19,458 | 39.4→37.3 / 39.5→36.9 / 39.5→36.1 |

**Gemma at 128K leaves about 650 MiB of the 32,656 MiB free.** It fits on a card with nothing else on it, but not with a display attached; use 64K then. memwatch's GPU column is `nvidia-smi`, which here is the idle RTX 3080, hence the separate B65 log. Memwatch needed `bc`, which AJ installed (2026-10-14).

## Hardware photo
ASRock's own render of the Arc Pro B65 Creator 32GB (`(L2).png` from the product page's gallery), 1100×578 on the site's #141414 matte, credited to ASRock with the product page as source. asrock.com blocks scripted downloads (Incapsula); the same files are served by `www.asrock.com.tw`. Not marked representative: the B65 ships only as partner cards, so this is the exact SKU.

## Open, for AJ
- **PR #260** (card, nine recipes) and **PR #264** (hardware photo, needs #260's card) are open against sybil-solutions/local-ai-registry, waiting on maintainer review. Split per CONTRIBUTING rule 1; a card plus several recipes for it is one change in merged PRs (#198, #205).
