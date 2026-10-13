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

Dry runs (`raw/20261012-135144`, `-135358`, `-140508`; `p05-20261012-163305`; `p1-20261012-175804`; `p2-dry-20261013-091018`; `p1s-dry-20261013-111753`) are kept for the record and aren't used in any findings.

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
