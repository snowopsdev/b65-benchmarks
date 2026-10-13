# Arc Pro B65 benchmark: Phase 1S findings (Phase 1 rerun on SYCL, flash attention on)

Run `p1s-20261013-111949`, 2026-10-13, 11:19–11:50 AM ET. Package: `b65-phase1s-p1s-20261013-111949.tar.gz`.
- **Results:** all 15 decode tests ok, no out-of-memory results. All three servers started at 32K context, and all 27 requests completed.
- **Stop rules:** none triggered.
- **Throttling:** none. Decode reps are flat, including Muse at 190–198 W.

## Setup
- **Engine:** llama.cpp `8bb3cf0d2` (build 11574), SYCL build from Phase 2 (oneAPI 2026.0, compute-runtime 26.31, JIT, F16), on `level_zero:0` = Arc Pro B65.
- **llama-bench:** `-fa 1`, 5 reps.
- **llama-server:** `-fa on -c 32768 -np 1`, prompt cache off, 3 reps per prompt size. Gemma ran with `--ctx-checkpoints 0`.
- **Power:** GPU board power from xe hwmon only, averaged over the timed reps.
- **Comparison baselines:**
  - Phase 1 on Vulkan with flash attention off (`p1-20261012-180308`).
  - For Gemma's server numbers, the Vulkan rerun with the same `--ctx-checkpoints 0` flag (`p1-swa-20261013-081841`).

## Results
### Decode tok/s by context depth (SYCL, flash attention on), change vs Phase 1 Vulkan

| Model | @0 | @4K | @8K | @16K | @32K |
|---|---|---|---|---|---|
| Qwen 3.8 27B | 23.67 (+24%) | 22.22 (+18%) | 20.80 (+13%) | 18.63 (+5%) | 15.27 (**−5%**) |
| Gemma 4 31B QAT | 22.45 (+17%) | 20.42 (+17%) | 19.77 (+17%) | 18.28 (+14%) | 16.07 (+25%) |
| Muse Glimmer 28B | 25.69 (+23%) | 24.64 (+32%) | 24.32 (+35%) | 23.56 (+40%) | 22.28 (+51%) |

The values match Phase 2's SYCL flash-attention-on results within 0.2% on all 12 shared tests.

### Time to first token, llama-server (median of 3), Vulkan → SYCL

| Model | 512 tokens | 4K | 16K |
|---|---|---|---|
| Qwen 3.8 27B | 1.31 → **0.96 s** (1.4× faster) | 9.70 → **6.94 s** (1.4×) | 42.22 → **28.89 s** (1.5×) |
| Muse Glimmer 28B | 1.71 → **0.87 s** (2.0×) | 11.78 → **6.78 s** (1.7×) | 41.65 → **28.51 s** (1.5×) |
| Gemma 4 31B QAT (both with `--ctx-checkpoints 0`) | 1.36 → **2.81 s** (2.1× slower) | 11.08 → **14.13 s** (1.3× slower) | 49.36 → **58.13 s** (1.2× slower) |

### Loaded idle (30 s) and VRAM at 32K context

| Model | Board W | VRAM, SYCL | VRAM, Vulkan (Phase 1) |
|---|---|---|---|
| Qwen 3.8 27B | 44.9 | 17,582 MiB | 19,095 MiB |
| Gemma 4 31B QAT | 44.9 | 20,916 MiB | 24,244 MiB |
| Muse Glimmer 28B | 44.9 | 16,080 MiB | 18,164 MiB |

## Findings
1. **Everything fits at 32K context with room to spare.** VRAM held at 32K is 8–14% lower than on Vulkan: −1.5 GiB for Qwen, −3.3 GiB for Gemma, −2.0 GiB for Muse. The likeliest reason for Gemma's large drop is that the padded V cache Vulkan needed without flash attention is gone; that hasn't been checked in the logs.
2. **Decode gains hold up the way Phase 2 predicted.** Gains with context:
   - Muse gains more as context grows (+23% to +51%), and its 0-to-32K falloff is only −13%.
   - Gemma gains 14–25% at every depth.
   - Qwen's gain shrinks with context and turns negative at 32K: −5%, 15.27 vs 16.14 tok/s.

   Every model now decodes above 15 tok/s at 32K; Qwen is the closest, at 15.27.
3. **First word is 1.4–2.0× faster for Qwen and Muse:** under 1 s on a 512-token prompt, about 7 s at 4K and about 29 s at 16K.
4. **Gemma's first word is slower on SYCL than on Vulkan with the same checkpoint fix:** 2.8 / 14.1 / 58.1 s against 1.4 / 11.1 / 49.4 s.
   - Its server prompt speed is 182–290 tok/s, well below what llama-bench measures for Gemma on SYCL with flash attention on (397–414 tok/s).
   - On Vulkan the server matched llama-bench (370 vs 379 at 4K), so this gap is new on SYCL.
   - It's still far better than Gemma with default checkpoints (25 / 108 / 147 s).
   - The cause is unexplained; the server log shows steady processing, not the checkpoint stall.
5. **Server generation now matches llama-bench:** within 1–4% at the same depth for all three, against up to 15% below on Vulkan. Server prompt speed for Qwen and Muse is 5–16% below llama-bench prefill, about as on Vulkan.
6. **Idle with a model loaded is 44.9 W for all three,** the same as on Vulkan.
7. **Power:**
   - Decode draws 165–198 W.
   - Muse sits closest to the 200 W cap (190–198 W), but its reps don't decline, so there's no sign of throttling.
   - Server requests draw 156–195 W.

## Open
- **Gemma's server prompt speed on SYCL:** 29–56% below llama-bench. That's the opposite of Vulkan, where it matched once checkpoints were off. Possible next steps:
  - Try a larger `-ub`/`-b` on the server, to match llama-bench's batch settings.
  - Try Gemma on SYCL with flash attention off for the server only.
- **Qwen's 32K decode regression on SYCL (−5%)** is still open from Phase 2.
- **Multi-turn cache test with checkpoints off** is still open. So is the optional `GEMMA_CKPT=32` control, which wasn't run.

## Kit notes
`b65-phase1s/README.md` covers this. In short, `phase1s.sh` was built from the fixed Phase 1 script, because Forge's copy still had several Phase 1 bugs:
- `bc`, which isn't installed.
- The AMD VRAM path.
- An unlabelled energy channel.
- Invocation-average power.
- A device check on the first test only.

## Posting status
- **Cleared:** everything.
- **When posting Gemma's time to first token:** compare it with the Vulkan checkpoints-off numbers, not Phase 1's default-checkpoint numbers. The share cards already do this.
