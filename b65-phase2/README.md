# Phase 2 kit: Vulkan vs SYCL (Forge kit, local changes)

Plan and rules: `HANDOFF.md`. Run outputs go to `raw/p2-*` (dry runs: `raw/p2-dry-*`). Live view: `/p2` on the dashboard.

## Step 0 (Gemma llama-server): already answered, not rerun
`gemma_swa.sh` tests baseline, `--swa-full`, `--swa-full --ctx-checkpoints 0` and `--ctx-checkpoints 0`. The same question was
run on 2026-10-13 as `../b65-phase1/raw/p1-swa-20261013-081841` (same build, flags, prompts and reps):

| Variant | 512 TTFT | 4K TTFT | 16K TTFT |
|---|---|---|---|
| baseline (defaults, same-session control) | 25.29 s | 108.49 s | 146.75 s |
| `--ctx-checkpoints 0` | **1.36 s** | 11.08 s | 49.36 s |
| `--swa-full` | out of VRAM at 32K (KV cache allocation failed at load) | | |

- **`--ctx-checkpoints 0` passes the plan's test:** 512-token TTFT is under 3 s.
- **`--swa-full` fails at context creation,** before any request, so `--swa-full --ctx-checkpoints 0` would hit the same allocation. It wasn't run.
- **Decision for the plan:** use `--ctx-checkpoints 0`, not `--swa-full`, as Gemma's llama-server default.
- **Not measured:** the multi-turn cost of having no checkpoints, since the run used prompt cache off.
- **Details:** `../findings/phase1.md`.

## Packages
Arch no longer ships `intel-oneapi-basekit`, the package the handoff names. The SYCL build needs the DPC++ compiler, oneMKL
(SYCL BLAS) and Level Zero:

    sudo pacman -S --needed intel-oneapi-dpcpp-cpp intel-oneapi-mkl-sycl level-zero-loader level-zero-headers intel-compute-runtime

oneDNN is optional for llama.cpp SYCL and isn't installed. Arch's `onednn` package isn't a GPU build. Installed versions
are recorded in `packages.txt` and in each run's `env.txt`.

## Build and checks (2026-10-13)
- AJ installed the packages listed above; versions are in `packages.txt`.
- `build_sycl.sh` built in about 10 minutes and reports `version: 0.6.0-dev (build 11574, commit 8bb3cf0d2)`. `sycl-ls` shows `[level_zero:gpu][level_zero:0] Intel(R) Arc(TM) Pro B65 Graphics`. The log is `build_sycl.log` (723 compiler warnings, no errors).
- Dry run `raw/p2-dry-20261013-091018`, Qwen only: all 6 cells ok. SYCL `gpu_info` reads "Intel(R) Arc(TM) Pro B65 Graphics".
- **Gibberish check** (`raw/p2-spot-20261013-091431`): Qwen ran in llama-server at temperature 0 on SYCL and on Vulkan, with the same prompt and 120 tokens. The text was **identical**, all 583 characters, at 23.92 tok/s on SYCL vs 19.11 on Vulkan.
- The dry run's `env.txt` has a device-table header where the SYCL version belongs, because `grep version` matched "Driver version". This is fixed for the full run (`grep '^version:'`).

## Local changes
- `phase2.sh`:
  - Uses the vendor Vulkan build by default (`../vendor/llama.cpp/build/bin`), and uses awk instead of `bc`, which isn't installed.
  - Prechecks that Vulkan sees only the B65 with at least 28 GB VRAM free, and that SYCL0 is the B65.
  - Picks the xe `card` energy channel by label, rather than the first `energy*_input`.
  - Measures board W over the timed reps only (stamped `--progress` plus a 10 Hz trace), the same method as Phases 0–1.
  - Checks every test's `gpu_info` strictly: it must be Intel or BMG, and never NVIDIA. The old check also matched the word "intel" in file paths.
  - Writes pid and done markers, plus a `t_end` column, for the dashboard.
  - Names dry runs `p2-dry-*`, and adds optional `TESTS_SPEC` and `RUNS_SPEC` overrides.
- `summarize2.py`:
  - Model names contain dots (`qwen3.8-27b`), so tags are split from the right.
  - Board W is now over the timed reps; the whole-invocation average is kept as `invocation_w`.
  - Adds a W table and `gpu_info`.
- `build_sycl.sh`:
  - Clones from the local `../vendor/llama.cpp` checkout (same commit, no network). The Vulkan tree and build stay untouched.
  - Uses cmake and ninja from the project `.venv`, with a fallback from `setvars.sh` to `oneapi-vars.sh`.
  - Lists the devices llama-bench sees.
  - Logs everything to `build_sycl.log`.
  - Turns off `set -u` while sourcing `setvars.sh`, because oneAPI's `vars.sh` reads unset variables (`OCL_ICD_FILENAMES`).
