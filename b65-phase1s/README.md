# Phase 1S kit: Phase 1 rerun on SYCL, flash attention on (Forge kit, local changes)

Plan and stop rules: `HANDOFF.md`. Runs go to `raw/p1s-*` (dry runs: `raw/p1s-dry-*`). Live view: `/p1s` on the dashboard; share cards under the Phase 1S tab.

    SYCL_BIN=~/src/llama.cpp/build-sycl/bin DRY=1 ./phase1s.sh   # one model: tg128 + one 512-token request
    SYCL_BIN=~/src/llama.cpp/build-sycl/bin ./phase1s.sh         # full run
    GEMMA_CKPT=32 ...                                             # Gemma default-checkpoint control (edit models.conf to run Gemma alone)
    CTX_muse_glimmer=16384 ...                                    # per-model ctx override, for Forge's OOM-at-32k rule

## Local changes
`phase1s.sh` is built from the fixed Phase 1 script (`../b65-phase1/phase1.sh`) rather than Forge's copy. Forge's version still had the Phase 1 kit bugs:
- `bc`, which isn't installed.
- The AMD-only `mem_info_vram_used` path, so VRAM came out blank. The fixed script reads xe fdinfo instead.
- The first `energy*_input` file rather than the xe `card` channel.
- Invocation-average power. The fixed script measures over the timed reps (stamped `--progress` plus a 10 Hz trace).
- A device check on the first test only, which matched "intel" anywhere. The fixed script checks `gpu_info` on every test.

SYCL changes in the fixed script:
- `SYCL_BIN`; `setvars.sh` sourced with `set +u`.
- Environment: `ONEAPI_DEVICE_SELECTOR=level_zero:0`, `UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1`.
- A precheck that SYCL0 is the B65.
- Flash attention: `-fa 1` for bench, `-fa on` for the server.
- Gemma runs with `--ctx-checkpoints ${GEMMA_CKPT:-0}`.
- Level Zero OOM strings are detected.
- `env.txt` records the backend, device, compute-runtime, oneAPI version and gemma_ckpt.
- Optional per-model `CTX_<model>` overrides.

`summarize1.py` is the fixed Phase 1 summary script, with these changes:
- It splits tags from the right.
- It adds a timed-rep W table.
- It labels the backend and FA setting from `env.txt`.

## Dry run (2026-10-13, `raw/p1s-dry-20261013-111753`)
Qwen results:
- tg128: 23.68 tok/s. Phase 2 measured 23.68 for SYCL with FA on.
- 512-token time to first token: 1.39 s.
- Server generation: 23.38 tok/s.
- Loaded idle: 43.6 W.
- VRAM at 32K context: 17,582 MiB (Phase 1 on Vulkan: 19,095).
- `gpu_info`: "Intel(R) Arc(TM) Pro B65 Graphics".
