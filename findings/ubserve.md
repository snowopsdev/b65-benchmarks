# Arc Pro B65: llama-server at the new SYCL default (-b 2048 -ub 2048)

Run `us-20261013-161926`, 2026-10-13, 4:19–4:28 PM ET. Qwen and Muse. Package: `b65-ubserve-us-20261013-161926.tar.gz`.
- **Method:** the same as Phase 1S. llama-server on SYCL with flash attention on, 32K context, prompt cache off; prompts of 512, 4K and 16K tokens, 3 reps each, median reported; 30 s of loaded idle plus VRAM. Only `-b 2048 -ub 2048` changes.
- **Gemma's ub 2048 numbers** come from the Gemma diagnostic (`gd-20261013-123933`, `ckpt0_ub2048`).
- **Why:** Forge's Phase 4 decision made ub 2048 the SYCL default for all three models, but its llama-server effect had only been measured for Gemma.

## Time to first token (median of 3)

| Model | Prompt | Vulkan (Phase 1) | SYCL ub 512 (Phase 1S) | **SYCL ub 2048** | Change vs ub 512 | Prompt tok/s | Gen tok/s |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B | 512 | 1.31 s | 0.96 s | **0.96 s** | same | 536 → 536 | 23.36 → 23.34 |
| | 4K | 9.70 s | 6.94 s | **4.87 s** | 1.43× faster | 591 → 843 | 22.08 → 22.41 |
| | 16K | 42.22 s | 28.89 s | **20.48 s** | 1.41× faster | 568 → 801 | 18.54 → 18.78 |
| Muse Glimmer 28B | 512 | 1.71 s | 0.87 s | **0.87 s** | same | 592 → 593 | 25.43 → 25.44 |
| | 4K | 11.78 s | 6.78 s | **4.77 s** | 1.42× faster | 605 → 861 | 24.52 → 24.02 |
| | 16K | 41.65 s | 28.51 s | **20.53 s** | 1.39× faster | 576 → 800 | 23.42 → 22.97 |
| Gemma 4 31B QAT | 512 | 1.36 s* | 2.81 s | **2.75 s** | same | 182 → 187 | 21.58 → 21.58 |
| | 4K | 11.08 s* | 14.13 s | **7.24 s** | 1.95× faster | 290 → 567 | 19.92 → 18.72 |
| | 16K | 49.36 s* | 58.13 s | **30.79 s** | 1.89× faster | 282 → 533 | 17.83 → 16.86 |

\* Gemma's Vulkan reference is the `--ctx-checkpoints 0` rerun.

| Loaded idle (30 s) and VRAM at 32K | Idle W | VRAM ub 512 → ub 2048 |
|---|---|---|
| Qwen 3.8 27B | 42.9 | 17,582 → 18,104 MiB (+522) |
| Muse Glimmer 28B | 44.8 | 16,080 → 16,755 MiB (+675) |

## Findings
1. **The llama-bench gain carries over to serving.** Qwen and Muse reach their first token 1.4× sooner at 4K and 16K. Server prefill goes from about 570–605 to 800–861 tok/s, close to llama-bench at ub 2048 (Qwen 824, Muse 821 at 16K).
2. **Against Phase 1 on Vulkan,** a 16K-token prompt now gets its first token about **2.0× sooner** for Qwen and Muse (42 s → 20.5 s), and **1.6× sooner** for Gemma (49 s → 31 s).
3. **Short prompts don't change.** 512 tokens fit in one micro-batch either way. Gemma's 512-token gap against Vulkan (2.8 s vs 1.4 s) remains; Phase 5 Part B looks into it.
4. **The costs are small:**
   - Generation is within 2% for Qwen and Muse (Muse −1.9% at 16K, Qwen +1.3%). Gemma's is 5–6% slower.
   - VRAM at 32K is 0.5–0.7 GB higher.
   - Loaded idle is unchanged (43–45 W).
