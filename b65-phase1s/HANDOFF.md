# Phase 1S handoff: rerun Phase 1 on SYCL (flash attention on)

**Why:** In Phase 2, SYCL with flash attention on beat Vulkan by 17-24% on decode and by 11-56% on prefill, which clears the 10% rule. Every Phase 1 user-facing number (decode at depth, TTFT, server decode, power, VRAM) gets re-measured on the new default engine.

## Prereqs
- The Phase 2 SYCL build (JIT, F16) at commit 8bb3cf0d2. No AOT, no rebuild.
- `/opt/intel/oneapi/setvars.sh` present. The script sources it and sets `ONEAPI_DEVICE_SELECTOR=level_zero:0` and `UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1`.
- Nothing else running on the B65. The 3080 keeps the display.

## Run
```
tar xzf b65-phase1s.tar.gz && cd b65-phase1s
export SYCL_BIN=~/src/llama.cpp/build-sycl/bin      # same path as Phase 2
DRY=1 ./phase1s.sh                                  # ~5 min smoke test; must print an Intel device line
./phase1s.sh                                        # full run, all 3 models
GEMMA_CKPT=32 ./phase1s.sh                          # optional: Gemma with default checkpoints, as a control
```
Gemma's server runs with `--ctx-checkpoints 0` by default (the Phase 1 fix). Edit `models.conf` to run Gemma alone for the control.

## What it measures (same as Phase 1)
- llama-bench decode at depths 0, 4k, 8k, 16k and 32k (`-fa 1`).
- llama-server at ctx 32768: TTFT and decode for 512, 4k and 16k-token prompts, 3 reps each, `cache_prompt` off.
- 30 s of loaded-idle power, plus VRAM use.

## Stop rules
- Out of memory at ctx 32768 for any model: note it, drop that model's ctx to 16384, and rerun that model only.
- Garbled or repeated output in the server log: stop and upload what you have.
- Board power pinned at 200 W with tok/s falling across reps (throttling): finish the run and flag it.

## Upload
Upload `raw/p1s-*` along with `env.txt` and the printed summary to the group chat as one tarball.

## After this
- Phase 1.5 (the registry recipes) is still blocked on @0xSero's reply.
- Then Phase 3 and Phase 4 run on SYCL.
- Still open: the multi-turn cache test for checkpoints off, and Qwen's 6% decode drop at 32k.
