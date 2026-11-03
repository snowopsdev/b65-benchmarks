# Arc Pro B65: Phase 8 findings (TensorFold's XPU engine)

The question: does [TensorFold](https://tensorfold.dev)'s unofficial Intel XPU port beat Intel llm-scaler vLLM (Phase 7's A5, the setting `b65-llm` serves) for Qwen3.8-27B on the B65? Run on 2026-11-02 with the Phase 7 client (`b65-phase7/oai_bench.py`) and an agent-shaped long-context test (`b65-phase8/longctx.py`).

**Setup:**
- **Engine:** [ashhart/TensorFold](https://github.com/ashhart/TensorFold) at `16d95cc`. Built from source with Zig 0.17.0, the host's `ocloc`, and the nGEN headers from oneDNN's `third_party/ngen`, following [the B70 recipe](https://github.com/ashhart/TensorFold/blob/main/docs/xpu/RECIPE-qwen38-27b-b70.md).
- **Weights:** SergiioB's `Qwen3.8-27B-GPTQ-Int4-sym-G128-MTP-BF16` at `9d189a6`, plus the `z-lab/Qwen3.8-27B-DFlash2` drafter at `50307d4`, about 23 GB in all.
- **Fewer Xe-cores than the B70:** the port was written for the B70 (32 GB), but the B65 has the same memory and the same `bmg` kernel target.
- **One patch:** the engine opens only PCI id `0xe223` (the B70). [`xpu-device-id.patch`](../b65-phase8/xpu-device-id.patch) adds an `XPU_DEVICE_ID` override, and the runs use `XPU_DEVICE_ID=e222`. Nothing else changed.
- **Correctness on the B65:** all of the engine's own checks pass.
  - Drafted output equals serial output, with both perfect and wrong drafts.
  - DFlash2 trees equal serial output.
  - 8 streams in shared rounds equal serial output.
  - 32 greedy tokens give sensible code.
- **Load:** 33 s, against 5–8 min for vLLM, which quantizes on load.

**Runs (`b65-phase8/results/`):**

| run | server | what |
|---|---|---|
| `tf-20261102-133335` | `--parallel 8 --context 16384` (7 streams fit), bf16 KV | Phase 7 speed, concurrency and coding suites |
| `tf-20261102-133335-80k` | `--parallel 2 --context 81920` (1 stream fits), bf16 KV | speed at 16K, 32K and 64K |
| `tf-20261102-133335-80k-kv8` | as above + `XPU_KV_INT8=1 --prompt-cache-gib 1` (2 streams fit) | speed from 512 to 64K |
| `longctx-tf.json`, `longctx-vllm.json` | TensorFold 80K kv8 vs `b65-llm` (vLLM A5, 80K) | real Zig source as context, then a coding request; greedy, thinking off, 512 tokens |

## Results

| test | TensorFold | Intel vLLM A5 | |
|---|---|---|---|
| Coding suite, decode tok/s on answers | **157.5** (30/30) | 74.2 (29/30) | **2.1×** |
| Decode, 512-token prompt (markdown, `oai_bench speed`) | 79.0 | 45.2 | 1.7× |
| Decode, 32K prompt (markdown) | 22 | 51.6 | **0.43×** |
| Prompt reading, 32K cold (first token) | 28.6 s | 27.5 s | same |
| 8 users at once, total tok/s (512-token prompts) | 168.9 | 136.8 (k=5); 197.0 (k=3) | between the two |

**Agent-shaped test:** code as context, then a coding answer. The figures are decode tok/s, as the median of 2 reps.

| context | 512 | 8K | 16K | 32K |
|---|---|---|---|---|
| TensorFold | **150.7** | **93.4** | 65.6 | 43.3 |
| Intel vLLM A5 | 69.4 | 77.9 | **76.7** | **68.8** |

- **TensorFold is about 2× faster on short contexts,** with the biggest margin on code, where DFlash2 trees accept about 7 tokens a round.
- **Its decode falls with context; vLLM's barely moves.** The lines cross near 14K tokens.
- **The int8 KV cache does not help with that.** It decodes at the same speed as bf16 at every length. So the slowdown is attention compute, not cache bandwidth. Its gain is capacity: 2 streams of 80K instead of 1.
- **Coding agents in T3 usually run with 15–40K tokens of context,** which is where vLLM is ahead.
- **Prompt reading (first-token time):** both read a cold prompt at about 1,150–1,350 tok/s. In the long-context test each size's first rep begins with the previous size's prompt. vLLM's prefix cache reused that part, at 7.5 s for 16K against 13.0 s. TensorFold's cache keeps state only at the points it plans, so it missed.

## Prefill option: `XPU_PREFILL_INT8=1`

Run on 2026-11-03 with `b65-phase8/prefill_int8.sh` (`results/prefill-20261103-172116`): one fresh server per mode (`--parallel 1 --context 81920`), cold prompts, 3 reps, then the coding suite. No GPU resets were logged.

| prompt | 512 | 4K | 8K | 16K | 32K | 64K |
|---|---|---|---|---|---|---|
| default (fp16), tok/s | 1,269 | 1,357 | 1,330 | 1,264 | 1,144 | 949 |
| **int8, tok/s** | **1,605** | **1,730** | **1,686** | **1,583** | **1,399** | **1,118** |
| gain | +26% | +28% | +27% | +25% | +22% | +18% |
| first token, default → int8 | 0.4 → 0.3 s | 3.0 → 2.4 s | 6.2 → 4.9 s | 13.0 → 10.4 s | 28.6 → 23.4 s | 69.0 → 58.6 s |

- **Against the other engines:** int8 now beats Intel vLLM's cold prefill (2.4 s vs 3.0 s at 4K, 23.4 s vs 27.5 s at 32K). exl3xpu is still faster (1.9 s and 18.5 s). The B70's published gain at 4K is +33%, against +28% here.
- **Decode doesn't change.** The coding suite gives 157.3 tok/s (30/30) against 157.2 (30/30), and decode still falls with context, so the 14K crossover with vLLM stands.
- **Correctness:** with int8 on, drafted output equals serial, DFlash2 trees equal serial and 8 shared streams equal serial. The first 32 greedy tokens match default mode.
- **Answers are not always identical to default mode.** 27 of the 30 coding replies had the same hash; 3 differed, and all 30 passed. The prompt is computed at lower precision, so expect occasional differences on near-ties.
- **Not tested:** rotated weights with `XPU_PREFILL_INT4=1`, the B70's fastest prefill. They need a second ~19 GB copy of the model, and the disk had 13 GB free.

## Problems

- **One GPU hang.** At the end of the 80K bf16 session, after the 64K prompts, a compute job timed out. The kernel logged `Engine reset: engine_class=ccs … Timedout job … in tensorfold-nati`, and the engine exited with `a command list did not drain (Level Zero 0x70000001)`. The card recovered, and the next sessions were clean. It happened once in four sessions, too few to call it a pattern.
- **VRAM is held for a few seconds after the process exits.** A vLLM start right after TensorFold stopped saw only 6.2 of 31.9 GiB free and failed. `b65-llm`'s restart picked it up 30 s later. Wait about 10 s between engines.
- **No grammar library by default.** Structured output and `tool_choice: required` need `libtfgrammar.so`, built from xgrammar v0.2.8. Plain tool calls work without it: `get_weather` returned a correct `tool_calls` reply. Reasoning comes back as `reasoning_content`, where vLLM uses `reasoning`.
- **Not on the community board.** tensorfold.dev's `tensorfold benchmark` and its leaderboard cover Apple silicon and NVIDIA only, so these figures can't be submitted there.

## Verdict

- **Keep Intel vLLM (A5) for T3.** Coding agents carry long contexts, and vLLM holds 69–78 tok/s from 512 to 32K tokens. It also keeps 80K context with prefix caching.
- **TensorFold is the better engine for short-context work:** chat, one-off code generation, and many users with short prompts. On the B65 it decodes code at **2.1×** vLLM's speed and loads in 33 s.
- **To try it as a second server,** stop `b65-llm` first; only one 27B engine fits on the card. Then run:

```sh
XPU_PREFILL_INT8=1 XPU_DEVICE_ID=e222 ~/src/TensorFold/zig-out/xpu/bin/tensorfold-native serve ~/models/Qwen3.8-27B-GPTQ-g128 \
  --drafter ~/models/Qwen3.8-27B-DFlash2 --parallel 8 --context 16384 --host 127.0.0.1 --port 8081 --name qwen
```

- **Worth revisiting** if upstream speeds up long-context decode on XPU, or if a DFlash2-style drafter comes to vLLM.
