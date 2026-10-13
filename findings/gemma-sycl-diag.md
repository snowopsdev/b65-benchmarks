# Arc Pro B65: Gemma SYCL server prefill diagnostic

Run `gd-20261013-123933`, 2026-10-13, 12:39–13:05 ET. Gemma 4 31B QAT Q4_0 only. SYCL build 11574 (`8bb3cf0d2`) with flash attention on, `level_zero:0` = Arc Pro B65. Kit: `b65-gemmadiag` (Forge, with local fixes listed in its README). Package: `b65-gemmadiag-gd-20261013-123933.tar.gz`.

**The question:** in Phase 1S, llama-server prefilled Gemma at about 282 tok/s while llama-bench measured about 397 tok/s. That made Gemma's 16K time to first token 58 s on SYCL, against 49 s on Vulkan. Forge's rule: if a variant brings 16K time to first token under about 45 s, it becomes Gemma's SYCL default.

## Answer: the micro-batch size
With `-b 2048 -ub 2048` (llama-server's default micro-batch is 512), Gemma's 16K time to first token is **30.8 s**:
- **47% less** than SYCL with the default micro-batch (58.2 s)
- **1.6× faster** than Vulkan with `--ctx-checkpoints 0` (49.4 s)

That clears Forge's 45 s target, so under the rule `-ub 2048` becomes Gemma's SYCL default.

| Config (SYCL, flash attention on) | 512 TTFT | 4K TTFT | 16K TTFT | Prompt tok/s (4K / 16K) | Gen tok/s (512 / 4K / 16K) |
|---|---|---|---|---|---|
| Vulkan reference (FA off, `--ctx-checkpoints 0`) | 1.36 s | 11.08 s | 49.36 s | 370 / 332 | 17.57 / 16.52 / 13.64 |
| `ckpt0` (Phase 1S config) | 2.81 s | 14.14 s | 58.17 s | 290 / 282 | 21.59 / 19.92 / 17.83 |
| `default` (checkpoints on) | 2.75 s | 14.92 s | 58.57 s | 275 / 280 | 21.55 / 19.91 / 17.82 |
| **`ckpt0_ub2048`** (`-b 2048 -ub 2048`) | **2.75 s** | **7.24 s** | **30.79 s** | **567 / 533** | 21.58 / 18.72 / 16.86 |
| `ckpt0_ctx16k` (ctx 17K) | 2.81 s | 14.12 s | 58.08 s | 291 / 282 | 21.55 / 19.88 / 17.80 |
| `ckpt0_swafull_16k` (`--swa-full`, ctx 17K) | out of VRAM at load (Level Zero `OUT_OF_DEVICE_MEMORY`) | | | | |
| `ckpt0_fa0` (FA off, local addition) | 2.66 s | 22.01 s | 91.29 s | 186 / 180 | 19.43 / 16.10 / 10.64 |

All values are the median of 3. After the first, cold request, repeat runs agree within 0.1 s, except `default` at 4K (14.92 vs 14.63 s, a 0.28 s spread). The `ckpt0` row reproduces Phase 1S within 0.1%.

llama-bench pp16384 (SYCL, FA on):

| Micro-batch | tok/s |
|---|---|
| `-ub 512` | 397.4 (Phase 2: 397.4) |
| `-ub 2048` | **617.1 (+55%)** |

## Findings
1. **Gemma's SYCL prefill is limited by the 512-token micro-batch.**
   - Raising it to 2048 speeds up prefill by 55% in llama-bench and by 89–96% in the server (290 → 567 tok/s at 4K, 282 → 533 at 16K).
   - At ub 2048 the server is about 14% below llama-bench (533 vs 617). That's the same kind of gap Qwen and Muse show at ub 512, so the extra Gemma-specific server gap is gone.
2. **Checkpoints don't cost anything on SYCL.** The default-checkpoint server is within 6% of `--ctx-checkpoints 0` at every size: −2% / +6% / +1% at 512 / 4K / 16K (58.6 vs 58.2 s at 16K). On Vulkan they added about 100 s per prompt. The flag matters for Vulkan, not SYCL.
3. **The 32K allocation isn't the cause.** At 17K context the results are identical to 32K.
4. **Flash attention has to stay on.** With it off, Gemma's SYCL server is much slower: 91 s at 16K, with generation at 10.6 tok/s.
5. **`--swa-full` doesn't fit** even at 17K context on SYCL, as at 32K on Vulkan.
6. **The trade-off for ub 2048:**
   - Generation is 5–6% slower at depth (18.72 vs 19.92 tok/s at 4K, 16.86 vs 17.83 at 16K). The 512-token generation and time to first token are unchanged, because a 513-token prompt fits in one micro-batch either way.
   - It still fits at 32K context. VRAM wasn't recorded by this kit; the compute buffer grows with ub.
   - Board power during requests is 156–177 W, against 155–162 W.
7. **Gemma on SYCL with ub 2048 vs Vulkan with the fix:** faster to first token at 4K (7.2 vs 11.1 s) and 16K (30.8 vs 49.4 s), and faster generation at every size. Vulkan is only ahead on 512-token prompts (1.4 vs 2.8 s). With this, SYCL is faster for Gemma on everything except very short prompts.

## Implications and next steps
- **Gemma's SYCL server default:** `-fa on -b 2048 -ub 2048`. `--ctx-checkpoints 0` is optional on SYCL.
- **Qwen and Muse weren't tested at ub 2048.** If their SYCL prefill also scales (Phase 2 and 1S both used ub 512), their time to first token could improve too.
- **Phase 2's prefill comparison still stands,** because both engines used the same default ub of 512. A Vulkan ub-2048 check would show whether Vulkan gains as much.
- **Gemma's short-prompt gap** (2.8 s vs 1.4 s at 512 tokens) isn't explained by micro-batch size.

> Reviewed by Forge on 2026-10-13: every number matches the raw serve.csv and llama-bench jsonl. The rep-spread exception above (`default` at 4K) was found in a recheck afterwards.
