# Arc Pro B65 32 GB: recommended settings (Phases 0–6)

This is the conclusion of Phases 0–6 (2026-10-12 to 2026-10-13). Each line names the phase it comes from; the numbers are in the linked findings.
- **Scope:** three ~30B Q4 models (Qwen 3.8 27B Q4_K_M, Gemma 4 31B QAT Q4_0, Muse Glimmer 28B Q4_K_M) on llama.cpp.
- **Versions:** llama.cpp build 11574 (`8bb3cf0d2`), oneAPI 2026.0, compute-runtime 26.31.39395.13, Mesa 26.2.2, kernel 7.2.5-3-omarchy.
- **After an update:** these settings are measured on these versions only. After any update, run the canary (`b65-phase4/canary.sh`, about 10 minutes) before trusting them.

**Share cards:** the Conclusion tab on the share page (`/share#sum`) has six cards, each in wide (X) and tall format, with captions. The cards are drawn from the run data:
- the recipe without numbers, and the recipe with its evidence
- time to first token on a 16K prompt
- generation speed out to 32K
- five settings that cost you
- which model for what

A seventh card, `sum-banner`, is a fixed 5:2 header for the X article. PNG exports are in `charts/conclusion/`. An article version for X and LinkedIn is in [article-b65-settings.md](article-b65-settings.md).

## The short answer

**llama.cpp SYCL, flash attention on, `-b 2048 -ub 2048`, all layers on the GPU, 32K context.** Leave context checkpoints at their default, and turn Qwen's thinking off for coding.

```bash
set +u; source /opt/intel/oneapi/setvars.sh --force; set -u
export ONEAPI_DEVICE_SELECTOR=level_zero:0 UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1
llama-server -m <model.gguf> -ngl 99 -c 32768 -np 1 --jinja -fa on -b 2048 -ub 2048
#   Qwen, coding:                add --reasoning-budget 0
#   Gemma, append-only agents:   add --ctx-checkpoints 0
```

## Why each setting

| Setting | Recommendation | Evidence |
|---|---|---|
| Engine | **SYCL** (oneAPI, Level Zero), not Vulkan | +21.8% decode and +31.2% prefill on average at the same commit; more efficient (decode 0.115 against 0.100 tok/J) ([Phase 2](phase2.md)). Answers 1.4–2.0× sooner at 512 tokens for Qwen and Muse, and uses 1.5–3.3 GiB less VRAM at 32K ([1S](phase1s.md)). |
| Flash attention | **On** with SYCL (off with Vulkan) | On SYCL it adds 18.5% to decode on average, up to +61% for Gemma at 32K. Gemma's server with it off: 91 s to first token at 16K ([Phase 2](phase2.md), [diag](gemma-sycl-diag.md)). On Vulkan it's the reverse: it cut Gemma's 16K prefill to 38 tok/s ([0.5](phase05.md)). |
| Micro-batch | **`-b 2048 -ub 2048`** on SYCL (512 on Vulkan) | +35–55% prefill at 16K, decode within 1.2%. 16K first token: Qwen 28.9 → 20.5 s, Muse 28.5 → 20.5 s, Gemma 58.1 → 30.8 s. Costs 0.5–0.7 GB VRAM ([Phase 4](phase4.md), [server rerun](ubserve.md)). On Vulkan, ub 2048 costs Muse 36%. |
| Context | **32K fits all three** | Every model decodes above 15 tok/s at 32K on SYCL ([1S](phase1s.md)). `--swa-full` doesn't fit for Gemma, at 32K or at 17K ([1](phase1.md), [diag](gemma-sycl-diag.md)). |
| Context checkpoints | **Default (on)**, with two exceptions | With them off, Qwen re-reads the whole chat on every regenerate or edit (9.4K tokens, 11.3 s against 0.17 s). Every model re-reads it when an earlier turn is edited ([Phase 6](phase6.md)). Exceptions: `--ctx-checkpoints 0` for Gemma append-only agent loops on SYCL (3.2 s against 6.0 s per turn, [Phase 5](phase5.md)), and for Gemma on Vulkan, always. |
| Thinking | **Off for Qwen coding** (`--reasoning-budget 0`); **on** for Muse | Qwen with thinking off: 10/10 greedy and 30/30, median 130 tokens, about 4× faster than with thinking on (9/10). Muse ignores both switches ([Phase 6](phase6.md)). |
| Token budget with thinking on | **At least 4K** for coding | At a 2K cap, Qwen and Gemma each failed one task while still thinking. Gemma passes with room (3,326 tokens); Qwen needs up to 9,650 ([Phase 3](phase3.md), [Phase 5](phase5.md)). |

## What you get, per model (SYCL, flash attention on, ub 2048)

| | Qwen 3.8 27B | Muse Glimmer 28B | Gemma 4 31B QAT |
|---|---|---|---|
| Decode, empty context → 32K (tok/s) | 23.7 → 15.3 | 25.7 → 22.3 | 22.5 → 16.1 |
| Time to first token, 512 / 4K / 16K prompt | 0.96 / 4.87 / 20.5 s | 0.87 / 4.77 / 20.5 s | 2.75 / 7.24 / 30.8 s |
| Server generation, 512 / 4K / 16K prompt (tok/s) | 23.3 / 22.4 / 18.8 | 25.4 / 24.0 / 23.0 | 21.6 / 18.7 / 16.9 |
| VRAM held at 32K context | 18,104 MiB | 16,755 MiB | 20,916 MiB (ub 512; not recorded at ub 2048) |
| Quality, Phase 3 (coding / tools / recall) | 9 / 10 / 5; 10/10 coding with thinking off | **10 / 10 / 5**, fastest overall | 9 / 10 / 5; **best writing** (blind rank 1.6) |

Sources:
- **Decode:** [Phase 1S](phase1s.md), llama-bench at ub 512; ub 2048 changes decode by ≤1.2% ([Phase 4](phase4.md)).
- **Time to first token and generation:** [the server rerun](ubserve.md) and [the Gemma diagnostic](gemma-sycl-diag.md).
- **Quality:** [Phase 3](phase3.md) and [Phase 6](phase6.md).

## Which model for what
- **Long context or general use: Muse.** It loses only 13% decode from empty to 32K context, has the fastest decode and the smallest VRAM, and scored best on Phase 3's coding set.
- **Coding with quick answers: Qwen with thinking off.** It scored 30/30, and a typical answer is about 130 tokens and a few seconds. Watch its decode at 32K: 15.3 tok/s, the one place SYCL loses to Vulkan (−5%).
- **Writing: Gemma.** It ranked first on 3 of 5 prompts in AJ's blind ranking (one rater, five prompts). It's the slowest to first token and the largest in VRAM. Its SYCL floor of about 1.1 s per request makes tiny prompts 0.3–0.6 s slower than on Vulkan ([Phase 5](phase5.md)).
- **Tool calling and notes recall:** all three scored 10/10 and 5/5. These don't separate the models.

## If you have to use Vulkan
Use flash attention off, ub 512, and `--ctx-checkpoints 0` for Gemma.
- **Gemma with default checkpoints** takes 25 s on a 512-token prompt and about 124 s per chat turn ([Phase 1](phase1.md), [Phase 5](phase5.md)).
- **Expect** about 18% slower decode (SYCL is +21.8%) and roughly half the 16K prefill of SYCL at ub 2048 (Qwen 388 vs 824, Gemma 335 vs 617 tok/s).

## Power
- **Decode:** 165–199 W of GPU board power against a 200 W cap. Muse sits at 190–199 W with no sign of throttling ([Phase 2](phase2.md), [1S](phase1s.md)).
- **Idle:** about 45 W with a model loaded, and 43 W empty.
- All figures are board power, not wall power.

## Not covered
- **Muse with thinking off:** no working switch was found.
- **Qwen's 32K regression on SYCL:** untested against SYCL tuning variables.
- **Gemma's ~1.1 s request floor on SYCL:** unexplained.
- **The PCIe link:** the card sits in a 4.0 x4 chipset slot, and its effect wasn't measured (it should mainly affect load time).
- **Other engines:** vLLM on XPU wasn't attempted.
- **Phase 1.5:** the registry recipes are still blocked on @0xSero.
- **Quality sets:** small and self-made. They're sanity checks, not leaderboards.
