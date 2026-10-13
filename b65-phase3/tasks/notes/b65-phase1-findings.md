# Arc Pro B65 benchmark: Phase 1 findings

Run `p1-20261012-180308`, 2026-10-12, started 6:03 PM ET, finished 6:52 PM ET. Package: `b65-phase1-p1-20261012-180308.tar.gz`.

## Setup
- llama.cpp build 11574 (`8bb3cf0d2`), for both llama-bench and llama-server, on Vulkan. The B65 is pinned with `GGML_VK_VISIBLE_DEVICES=1`, and the RTX 3080 is excluded.
- Mesa 26.2.2, kernel 7.2.5-3-omarchy, Omarchy 4.0.4.
- Flash attention was off for every test, per Phase 0.5.
- **llama-bench:** 5 reps per test, `tg128` at depths 0, 4K, 8K, 16K and 32K.
- **llama-server:** `-ngl 99 -fa off -c 32768 -np 1`, with everything else at its defaults, including context checkpoints (default 32 per slot). Each prompt size ran 3 times with streaming on, prompt cache off and 128 tokens generated.
- **Power:** GPU board power from xe hwmon only. There's no wall meter.

## Headlines
1. **All three models fit 32K context.** None ran out of memory. VRAM held by the loaded server process at 32K was 19,095 MiB (18.6 GiB) for Qwen, 24,244 MiB (23.7 GiB) for Gemma and 18,164 MiB (17.7 GiB) for Muse; these readings come from xe fdinfo. Gemma's server log warns that its V cache is padded to 4096 because flash attention is off, which accounts for part of the gap.
2. **Decode speed at 32K:** Qwen 16.1, Muse 14.7, Gemma 12.8 tok/s. From empty context to 32K, Qwen drops 15%, Muse 30% and Gemma 33%.
3. **Time to first token for Qwen and Muse:**
   - 512-token prompt: 1.3 s and 1.7 s.
   - 4K: 9.7 s and 11.8 s.
   - 16K: 42.2 s and 41.7 s.
4. **Idle power with a model loaded is about 45 W** for all three models. With nothing loaded it was 43.1 W, measured in Phase 0 and not re-measured here, so loading a model adds about 2 W.
5. **Server decode for Qwen and Muse runs 1–8% below llama-bench at a similar depth** (0.1–1.3 tok/s). The largest gap is Qwen at 16K: 16.33 against 17.67. Gemma's server numbers are held (see 6).
6. **Gemma's slow first token is a llama-server default, and one flag fixes it** (confirmed by the 2026-10-13 rerun below).
   - **What happens:** Gemma takes 24–25 s to first token even on a 512-token prompt, and the GPU draws only 72–93 W while it waits.
   - **What the server log shows:**
     - At 4K, the first 3,581 tokens take about 8 s (431 tok/s average). The last 516 tokens then take about 100 s, in two steps of about 50 s each: 512 tokens, then the final 4.
     - At 16K the pattern is the same. The first 15,869 tokens take 46 s (345 tok/s). The last 516 take about 100 s in the same two steps.
   - **Likely cause:** that split matches llama-server's context-checkpoint logic for sliding-window-attention models. Before saving a checkpoint, it processes the last `n_ubatch + 4` tokens separately (`tools/server/server-context.cpp`). llama-bench doesn't exercise this, and Qwen and Muse don't trigger it.
   - **Rerun result:** with `--ctx-checkpoints 0`, Gemma's time to first token is 1.36 / 11.08 / 49.36 s, in line with Qwen and Muse and with llama-bench prefill. `--swa-full` ran out of VRAM at 32K context.

## Gemma llama-server rerun (`p1-swa-20261013-081841`)

Gemma only, 2026-10-13 8:18 AM ET. Same build and server flags as the Phase 1 run (`-ngl 99 -fa off -c 32768 -np 1`) plus one change per config. Each config ran 3 reps per prompt size, and the default config was rerun in the same session as a control. Package: `b65-phase1-swa-rerun-p1-swa-20261013-081841.tar.gz`.

| Config | 512 TTFT | 4K TTFT | 16K TTFT | Prompt tok/s (512 / 4K / 16K) | Gen tok/s (512 / 4K / 16K) | Board W while serving |
|---|---|---|---|---|---|---|
| Phase 1 baseline (defaults) | 25.25 s | 108.30 s | 146.58 s | 20 / 38 / 112 | 17.58 / 16.52 / 13.64 | 72–93 |
| Control (defaults, same session) | 25.29 s | 108.49 s | 146.75 s | 20 / 38 / 112 | 17.57 / 16.52 / 13.63 | 71–92 |
| `--ctx-checkpoints 0` | **1.36 s** | **11.08 s** | **49.36 s** | 377 / 370 / 332 | 17.57 / 16.52 / 13.64 | 155–167 |
| `--swa-full` | out of VRAM at 32K (a 1 GiB KV-cache allocation failed) | | | | | |

- **The penalty reproduces exactly.** The same-session control is within 0.2% of the Phase 1 baseline at every size.
- **Turning checkpoints off removes it:** first token arrives 18.6× faster at 512 tokens, 9.8× at 4K and 3.0× at 16K. The GPU now draws 155–167 W during requests, like the other models, instead of 70–90 W.
- **The server now matches llama-bench.** Prompt speed (377 / 370 / 332 tok/s) is within 9% of Phase 0.5 llama-bench prefill with flash attention off (413 / 379 / 335). Generation speed is unchanged, so the checkpoints only cost prompt time.
- **Trade-off (not measured):** checkpoints exist so llama-server can reuse a sliding-window model's cached conversation when the next request only partly matches the previous one, as chat turns usually do. Without them, each new turn may reprocess the whole conversation. This test ran with prompt caching off, so it doesn't measure that cost. Before recommending the flag broadly, run a multi-turn test with caching on, comparing checkpoints on and off.
- **`--swa-full` isn't an option at 32K** on this card with flash attention off. It might fit at a smaller context, but that wasn't tested; the rule is not to retry an OOM with lower settings.
- **Loaded idle:** 42.8 W (checkpoints off) and 44.8 W (control). VRAM was 24,244 MiB in both, identical to Phase 1, so checkpoints don't change resident VRAM at idle. The 2 W spread is within measurement noise; Phase 0 measured 43.1 W with nothing loaded.
- **Gemma server generation is still below llama-bench at depth:** 13.64 against 16.00 tok/s at 16K (−15%), with checkpoints on or off. Qwen is −8% and Muse −3% there. That's unexplained, but small next to the prompt-time fix.

## Registry check (decode must be at least 15 tok/s)
With flash attention off, all three models pass at 16K context (Qwen 17.7, Muse 16.8, Gemma 16.0). At 32K only Qwen passes (16.1). Muse (14.7) and Gemma (12.8) fall below the line. The registry's recall test runs at 85% of context, so whether these models pass depends on the context size each recipe declares.

## Open questions
- **Muse's server prompt speed** (prompt tokens divided by time to first token) is well below llama-bench prefill from Phase 0.5: 301 vs 540 tok/s at 512, 348 vs 483 at 4K, and 394 vs 430 at 16K. At 512 tokens, per-request overhead is part of it. The 28% gap at 4K is unexplained. Qwen's server speed is within 13% of llama-bench at every size.

## Raw tables
### Decode tok/s by context depth (fa=0; OOM = did not fit)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 19.16 | 17.39 | 16.94 | 16.00 | 12.84 |
| muse-glimmer | 20.94 | 18.71 | 18.03 | 16.79 | 14.73 |
| qwen3.8-27b | 19.08 | 18.85 | 18.43 | 17.67 | 16.14 |

### Decode board W (timed reps)

| Model | @0 | @4096 | @8192 | @16384 | @32768 |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 180.8 | 179.1 | 179.1 | 181.9 | 181.5 |
| muse-glimmer | 173.8 | 170.5 | 170.3 | 168.7 | 166.2 |
| qwen3.8-27b | 167.9 | 170.6 | 172.0 | 173.8 | 176.4 |

### llama-server (median of 3 reps)

| Model | Prompt tokens | TTFT s | Prompt tok/s | Gen tok/s | Board W |
|---|---|---|---|---|---|
| gemma-4-31b-qat ⚠ | 513 | 25.25 | 20 | 17.58 | 86 |
| gemma-4-31b-qat ⚠ | 4097 | 108.30 | 38 | 16.52 | 72 |
| gemma-4-31b-qat ⚠ | 16385 | 146.58 | 112 | 13.64 | 93 |
| muse-glimmer | 513 | 1.71 | 301 | 20.12 | 161 |
| muse-glimmer | 4097 | 11.78 | 348 | 18.57 | 149 |
| muse-glimmer | 16385 | 41.65 | 394 | 16.22 | 157 |
| qwen3.8-27b | 512 | 1.31 | 391 | 18.97 | 166 |
| qwen3.8-27b | 4096 | 9.70 | 422 | 18.32 | 160 |
| qwen3.8-27b | 16384 | 42.22 | 388 | 16.33 | 158 |

⚠ Held: llama-server checkpoint penalty (see headline 6).

### Idle board power with model loaded (30 s)

| Model | W | VRAM MiB |
|---|---|---|
| qwen3.8-27b | 44.9 | 19,095 |
| gemma-4-31b-qat | 44.9 | 24,244 |
| muse-glimmer | 45.0 | 18,164 |

## Posting status
- **Cleared:** decode at every depth for all three models, the 32K fit result, the Qwen and Muse server numbers, idle power and VRAM, and the methodology.
- **Gemma server numbers: released** by AJ on 2026-10-13, with the hold removed from `holds.conf`. Post them together with the checkpoint finding, either the `--ctx-checkpoints 0` numbers or the defaults labelled as a llama-server default. The Phase 1 cards footnote this, and the new "Gemma: one server flag" card shows before and after.

## Corrections to the draft
- VRAM figures were MiB read as GB (for example 19,095 MiB is 18.6 GiB, not 19.1 GB).
- Gemma's stall is about 100 s per prompt at 4K and 16K (two ~50 s steps), not about 50 s.
- "Server decode within about 1 tok/s of llama-bench" holds for Muse, but not for Qwen at 16K (1.34 tok/s) or for Gemma (up to 2.36 tok/s).
- `--ctx-checkpoints` does exist in build 11574 (default 32).
