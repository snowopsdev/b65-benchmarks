# Findings

Intel Arc Pro B65 32 GB · llama.cpp b11574 (`8bb3cf0d2`) Vulkan · Mesa 26.2.2 · kernel 7.2.5 · Omarchy 4.0.4.
Power is GPU board power from xe hwmon only; there's no wall meter.

| Phase | What it tested | Runs (raw data) | Findings |
|---|---|---|---|
| 0 | Baseline prefill + decode, 3 models, flash attention on | `raw/20261012-140638` | [phase0.md](phase0.md) |
| 0.5 | Flash attention off vs on, + fa=0 decode follow-up | `b65-phase05/raw/p05-20261012-163413`, `p05b-20261012-173906` | [phase05.md](phase05.md) |
| 1 | Decode by context depth (to 32K), llama-server TTFT, loaded idle | `b65-phase1/raw/p1-20261012-180308` | [phase1.md](phase1.md) |
| 1 follow-up | Gemma llama-server: `--ctx-checkpoints 0` / `--swa-full` / defaults | `b65-phase1/raw/p1-swa-20261013-081841` | [phase1.md](phase1.md#gemma-llama-server-rerun-p1-swa-20261013-081841) |
| 2 | Vulkan (FA off) vs SYCL (FA off/on), same commit, 7 tests × 3 models | `b65-phase2/raw/p2-20261013-091509` | [phase2.md](phase2.md) |
| 1S | Phase 1 rerun on SYCL, flash attention on | `b65-phase1s/raw/p1s-20261013-111949` | [phase1s.md](phase1s.md) |
| 3 | Quality: coding, tool calling, notes recall, blind writing (SYCL, FA on) | `b65-phase3/raw/p3-20261013-135609` | [phase3.md](phase3.md) |
| 4 | Canary vs Phase 2 baseline, plus the micro-batch check (SYCL and Vulkan) | `b65-phase4/raw/p4-20261013-150339` | [phase4.md](phase4.md) |
| 4+ | llama-server at the new SYCL default -ub 2048 (Qwen, Muse) | `b65-ubserve/raw/us-20261013-161926` | [ubserve.md](ubserve.md) |
| 5 | Open questions: ub 2048 canary baseline, Gemma short prompts, chat cache/checkpoints, Qwen thinking | `b65-phase5/raw/p5-20261013-171039` | [phase5.md](phase5.md) |
| 6 | Qwen/Muse coding with thinking off; regenerate/edit with checkpoints on/off; canary at ub 2048 | `b65-phase6/raw/p6-20261013-211819` | [phase6.md](phase6.md) |
| 1.5 | local-ai-registry's six lab gates: native pre-check, then `lab.py try` in the official server-intel image (3 recipes, local branch) | `b65-phase15/raw/p15pre-20261014-131018`, `p15reg-20261014-141612` | [phase15.md](phase15.md) |
| 1S diag | Gemma SYCL server prefill: micro-batch, checkpoints, ctx, swa-full, FA | `b65-gemmadiag/raw/gd-20261013-123933` | [gemma-sycl-diag.md](gemma-sycl-diag.md) |

Dry runs (`raw/20261012-135144`, `-135358`, `-140508`; `p05-20261012-163305`; `p1-20261012-175804`; `p2-dry-20261013-091018`; `p1s-dry-20261013-111753`; `p3-dry-20261013-135213`; `p4-dry-20261013-150059`; `p5-dry-20261013-162644`; `p6-dry-20261013-205752`) are kept for the record and aren't used in any findings.

**Conclusion:** [recommended-settings.md](recommended-settings.md) collects the best settings for the B65 from all phases.

## Headlines so far

1. **Turn flash attention off on this build.** `-fa 0` is faster or tied on every test. Gemma's 16K prefill went from 38 to 335 tok/s (8.8×), and Muse's decode at 16K went from 11.3 to 16.8 tok/s (Phase 0.5).
2. **All three ~30B Q4 models fit 32K context in 32 GB.** Decode at 32K: Qwen3.8 27B 16.1, Muse Glimmer 28B 14.7, Gemma 4 31B QAT 12.8 tok/s (Phase 1).
3. **Time to first token for Qwen and Muse:** 1.3–1.7 s on a 512-token prompt, about 42 s on a 16K prompt (Phase 1).
4. **Gemma + llama-server: use `--ctx-checkpoints 0`.** The default context checkpoints for sliding-window models cost 25 s on a 512-token prompt. With them off, it's 1.4 s. The multi-turn cost of turning them off isn't measured yet (Phase 1 follow-up).
5. **Idle with a model loaded is about 45 W**, against 43 W with nothing loaded.
6. **SYCL with flash attention on beats Vulkan:** +21.8% decode and +31.2% prefill on average, at the same llama.cpp commit (Phase 2). That clears the +10% rule, so **SYCL with flash attention on is the default engine from here (Forge, 2026-10-13)**. The exception is Qwen at 32K, where SYCL is 5.6% slower. Unlike Vulkan, SYCL wants flash attention on.

## Packages

Release tarballs for each run (raw data, scripts as run, summaries, SHA256SUMS) are built into `dist/`, which isn't committed because everything in it is regenerated from what's here. The dashboard serves them at `/files/dist/`.
7. **On SYCL, Qwen and Muse answer 1.4–2.0× sooner, all models fit 32K in 1.5–3.3 GiB less VRAM, and server generation matches llama-bench** (Phase 1S). Gemma's first token is slower than on Vulkan with the same checkpoint fix (2.8 s vs 1.4 s on a 512-token prompt), which is still open.
8. **Gemma on SYCL needs `-b 2048 -ub 2048`:** its 16K first token drops from 58 s to 31 s, 1.6× faster than Vulkan. Checkpoints cost nothing on SYCL (Gemma diagnostic).
9. **Quality (Phase 3): Muse scores 10/10 coding, 10/10 tools and 5/5 recall, and is quickest.** Qwen and Gemma each miss one coding task by running out of tokens while thinking. Gemma passes with more room; Qwen goes round in circles (Phase 5: it does finish on its own, at 9,402 tokens). In AJ's blind writing ranking, Gemma wins (mean rank 1.6 against 2.2 for both others).
10. **The canary is clean** (all within 0.1%), and **`-ub 2048` lifts SYCL prefill for all three models** (+35–55% at 16K, decode unchanged). On Vulkan it helps Qwen (+10%) but costs Muse 36% (Phase 4).
11. **At the new default, Qwen and Muse answer a 16K prompt in about 20.5 s,** 1.4× sooner than at ub 512 and about 2× sooner than on Vulkan. Generation is unchanged and VRAM is 0.5–0.7 GB higher (server rerun after Phase 4).
12. **Phase 5:**
    - The ub 2048 baseline reproduces Phase 4 within 0.03%.
    - Gemma on SYCL has a fixed ~1.1 s floor per request, so Vulkan answers tiny prompts 0.3–0.6 s sooner; SYCL is faster from 1K tokens up.
    - Every chat setup reuses its cache, and `--ctx-checkpoints 0` was faster in all 6 model and engine pairs (Gemma on Vulkan: 124 s per turn with checkpoints on vs 5.5 s off).
    - Qwen passes c08 5/5 with thinking off, in about 300 tokens and 13 s. With thinking on it needs up to 9,650 tokens; caps only cut it short, and the samplers don't help.
13. **Phase 6:**
    - Qwen with thinking off scores 10/10 greedy and 30/30 on the Phase 3 coding set (Phase 3: 9/10), about 4× faster. That makes thinking off the Qwen coding recipe. Muse ignores the thinking-off switches: it reasoned on all 30.
    - `--ctx-checkpoints 0` makes Qwen re-read the whole chat on every regenerate or edit (9.4K tokens, 11.3 s against 0.17 s). Gemma and Muse handle regenerate and edit-last fine with checkpoints off, but every model re-reads the whole chat when an earlier turn is edited.
    - The ub 2048 canary is within 0.03% of the Phase 5 baseline.
    - Forge's decision: checkpoints stay at the default except for Gemma on Vulkan and Gemma agent loops. The Phase 5 idea of `--ctx-checkpoints 0` everywhere is withdrawn.

## Current defaults (Forge, 2026-10-13; checkpoints and thinking updated after Phase 6)
- **Engine:** llama.cpp `8bb3cf0d2` SYCL, flash attention on, `-b 2048 -ub 2048`, for all three models.
- **Context checkpoints (llama-server):** leave at the default (on) for Qwen, Muse, and Gemma in chat UIs. `--ctx-checkpoints 0` only for Gemma on Vulkan, and for Gemma append-only agent loops on SYCL (3.2 s against 6.0 s per turn in Phase 5).
- **Qwen for coding:** thinking off (`--reasoning-budget 0`). Muse has no working thinking-off switch; it runs with thinking on.
- **Canary:** `b65-phase4/canary.sh` runs at ub 2048 against `baseline_ub2048.json` (Phase 5 part A); `UB=512` still checks against the Phase 2 baseline (Phase 6 handoff).
- **Vulkan:** if used, flash attention off and ub 512.
