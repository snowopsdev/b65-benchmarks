# Gemma SYCL diagnostic: handoff

**Question:** On SYCL, llama-server prefills Gemma at about 282 tok/s, while llama-bench gets about 397 tok/s at 16k. As a result, Gemma's time to first token on SYCL (58 s at 16k) is worse than on Vulkan (49 s). What is causing the gap?

## What it runs (Gemma only, SYCL with flash attention on, ~25 min)
1. llama-bench pp16384 with micro-batch 512 vs 2048. This checks whether batch size alone accounts for the gap.
2. llama-server prompts of 512, 4k and 16k tokens, 3 reps each, in five configurations:

| Variant | Flags | Tests |
|---|---|---|
| ckpt0 | `--ctx-checkpoints 0`, ctx 32k | Reproduces Phase 1S (should be ~58 s at 16k) |
| default | no extra flags | Do checkpoints still hurt on SYCL? |
| ckpt0_ub2048 | `-b 2048 -ub 2048` | Server batch size |
| ckpt0_swafull_16k | `--swa-full`, ctx 17k | Full sliding-window cache (ran out of memory at 32k on Vulkan) |
| ckpt0_ctx16k | ctx 17k | Does the 32k context allocation itself slow prefill? |

## Run
```
tar xzf b65-gemmadiag.tar.gz && cd b65-gemmadiag
export SYCL_BIN=~/src/llama.cpp/build-sycl/bin
DRY=1 ./gemmadiag.sh     # ~3 min
./gemmadiag.sh
```
If a variant runs out of memory, the script records it in `notes.txt` and moves on. That counts as a result, not a failure.

## Upload
Upload `raw/gd-*` (including each variant's `server.log`) as one tarball.

## How I'll read it
- **If one variant brings 16k TTFT under about 45 s:** that flag becomes Gemma's SYCL default, and SYCL wins for all three models.
- **If none does:** Gemma stays on Vulkan with `--ctx-checkpoints 0` for long prompts, and I file a llama.cpp issue with this data.
