# Arc Pro B65 benchmark: Phase 1 findings

Run `p1-20261012-180308`, 2026-10-12, 6:03 PM ET.

## Setup
- llama.cpp build 11574 (`8bb3cf0d2`), for both llama-bench and llama-server, on Vulkan.
- Mesa 26.2.2, kernel 7.2.5-3-omarchy, Omarchy 4.0.4-1.
- Flash attention was off for every test, per Phase 0.5. llama-bench ran 5 reps per test. The server ran at 32k context, with 3 reps per prompt size, prompt cache off, and 128 tokens generated per request.
- Power is GPU board power from xe hwmon only, with no wall meter.

## Headlines
1. **All three models fit 32k context.** None ran out of memory. VRAM use with the server loaded was 19.1 GB for Qwen, 24.2 GB for Gemma (its V cache is padded to 4096 with flash attention off) and 18.2 GB for Muse.
2. **Decode speed at 32k:** Qwen 16.1, Muse 14.7, Gemma 12.8 tok/s. Qwen drops 15% from empty context to 32k, Muse 30% and Gemma 33%.
3. **Time to first token (Qwen / Muse):** 1.3 s / 1.7 s for a 512-token prompt, 9.7 s / 11.8 s at 4k and 42.2 s / 41.7 s at 16k.
4. **Idle power with a model loaded is about 45 W** for all three models, only 2 W above idle with nothing loaded (43 W).
5. **Server decode matches llama-bench to within about 1 tok/s.**
6. **Hold the Gemma server numbers.** Gemma takes 25 s to first token even on a 512-token prompt, and the GPU draws only 72 to 93 W while it waits. The log shows the prompt mostly processing at about 500 tok/s, then roughly 50 s stalled on the final chunk. The likely cause is the server's sliding-window-attention handling, which llama-bench doesn't exercise. Next step: rerun Gemma's server tests with `--swa-full`, adding `--ctx-checkpoints 0` if the flag exists in this build.

## Registry check (decode must be at least 15 tok/s)
With flash attention off, all three models pass at 16k context. At 32k only Qwen passes (16.1). Muse (14.7) and Gemma (12.8) fall below the line. The registry's recall test runs at 85% of context, so whether these models pass depends on the context size each recipe declares.

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

### llama-server (median of reps)

| Model | Prompt tokens | TTFT s | Prompt tok/s | Gen tok/s | Board W |
|---|---|---|---|---|---|
| gemma-4-31b-qat | 513 | 25.25 | 20 | 17.58 | 86 |
| gemma-4-31b-qat | 4097 | 108.30 | 38 | 16.52 | 72 |
| gemma-4-31b-qat | 16385 | 146.58 | 112 | 13.64 | 93 |
| muse-glimmer | 513 | 1.71 | 301 | 20.12 | 161 |
| muse-glimmer | 4097 | 11.78 | 348 | 18.57 | 149 |
| muse-glimmer | 16385 | 41.65 | 394 | 16.22 | 157 |
| qwen3.8-27b | 512 | 1.31 | 391 | 18.97 | 166 |
| qwen3.8-27b | 4096 | 9.70 | 422 | 18.32 | 160 |
| qwen3.8-27b | 16384 | 42.22 | 388 | 16.33 | 158 |

### Idle board power with model loaded (30 s)

| Model | W |
|---|---|
| qwen3.8-27b | 44.9 |
| gemma-4-31b-qat | 44.9 |
| muse-glimmer | 45.0 |

## Posting status
- Cleared: decode at every depth for all three models, the 32k fit result, Qwen and Muse server numbers, idle power and the methodology.
- Hold: all Gemma server numbers (time to first token, prompt speed, power) until the `--swa-full` rerun.
