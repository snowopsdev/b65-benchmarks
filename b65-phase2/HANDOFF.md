# B65 benchmarks: Phase 2 plan and handoff

## Part 1: Plan

### Goal
Find the B65's best llama.cpp engine before anything goes to the registry. Phase 1 decode on Vulkan sits at about 55% of the card's memory-bandwidth ceiling (around 19 tok/s against roughly 34). The registry's B70 entry shows 81.6 tok/s on vLLM, so Vulkan alone undersells the card.

### Steps
| Step | What | Time | Done when |
|---|---|---|---|
| 0 | Gemma llama-server rerun (`gemma_swa.sh`): baseline vs `--swa-full` vs `--ctx-checkpoints 0` | ~20 min | One TTFT table per variant. A fix counts if 512-token TTFT drops from 25 s to under 3 s. |
| 1 | Build llama.cpp SYCL at the same commit, `8bb3cf0d2` (`build_sycl.sh`) | 30–60 min | `sycl-ls` shows the B65 on Level Zero, and `llama-bench --version` prints build 11574. |
| 2 | Backend sweep (`phase2.sh`): Vulkan with FA off vs SYCL with FA off and on. Tests: pp512, pp4096, pp16384, tg128 at depth 0, 4k, 16k and 32k. 5 reps. | 2–3 h | `phase2_summary.md` shows every cell as ok or oom. |
| 3 (stretch) | vLLM on Intel XPU, Qwen only, to compare with the registry's B70 number | open-ended | Optional. Only if steps 0–2 finish cleanly. |

### Decision rules after Phase 2
- If SYCL beats Vulkan by at least 10% on decode, SYCL becomes the default engine. Phase 1 time-to-first-token reruns on SYCL (about an hour), and registry recipes use it if the registry accepts llama.cpp.
- If SYCL is within ±10%, or slower, keep Vulkan. "SYCL isn't worth it on B65 yet" is the post.
- If `--swa-full` fixes Gemma's wait, it becomes the default for Gemma, and Cal gets the second one-flag post.
- Phase 1.5 (registry recipes) waits on two things: @0xSero's answer about llama.cpp recipes, and this engine decision.

### Known SYCL pitfalls (already handled in the scripts)
- Large-allocation limits: the scripts set `UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1`. Without it, single allocations over about 4 GB fail, and about 19 GB has been reported failing on B70 even with it. That matters for Gemma at 32k context.
- No AOT builds, because they've produced gibberish on Battlemage. The scripts build JIT only.
- The scripts pin the device with `ONEAPI_DEVICE_SELECTOR=level_zero:0`. The RTX 3080 isn't a Level Zero device, but check `sycl-ls` to make sure index 0 is the B65.
- The first SYCL run of each model is slow because of JIT compilation. llama-bench's warmup absorbs it, so don't panic.

---

## Part 2: Handoff (for the local agent)

You're the local agent on AJ's Omarchy machine running the Arc Pro B65 benchmarks in `~/Projects/b65-benchmarks`.
Phases 0, 0.5 and 1 are done. Findings are in `b65-phase1-findings.md`.

### Context
- GPU under test: Arc Pro B65 32 GB (PCI 8086:e222). The RTX 3080 drives the display and is NEVER benchmarked. Use the same `B65_VK_INDEX` as before.
- Software is pinned: llama.cpp commit `8bb3cf0d2` (build 11574), Mesa 26.2.2, kernel 7.2.5-3-omarchy, Omarchy 4.0.4-1. You may install oneAPI and Level Zero packages for this phase. Don't update the kernel, Mesa, or the Vulkan llama.cpp build. Record every package you install.
- Models are unchanged and verified against Hugging Face (see `models.conf`): Qwen 3.8 27B Q4_K_M, Gemma 4 31B QAT Q4_0, Muse Glimmer 28B Q4_K_M.
- Flash attention stays off for Vulkan. SYCL is tested both ways, because its FA code path is different.
- Power is GPU board power from xe hwmon only. Never call it wall power.

### Steps
1. Quit LM Studio so it isn't holding VRAM. Copy `b65-phase2/` into the repo.
2. **Step 0:** run `B65_VK_INDEX=<idx> ./gemma_swa.sh`, then save the printed table.
3. **Step 1:** install the packages: `sudo pacman -S intel-oneapi-basekit intel-compute-runtime level-zero-loader`. Then run `./build_sycl.sh`. Confirm that `sycl-ls` lists the Arc Pro B65 under level_zero and that the version line shows commit `8bb3cf0d2`.
4. **Dry run:** `B65_VK_INDEX=<idx> SYCL_BIN=~/src/llama.cpp/build-sycl/bin DRY=1 ./phase2.sh`. It should run pp512 and tg128 on both backends for one model.
5. **Full run:** the same command without `DRY=1`. Don't use the GPU for anything else while it runs.

### Rules
- Write new runs to new `raw/p2-*` and `raw/p2swa-*` folders only. Never edit earlier raw data.
- An `oom` result is valid and gets recorded. Don't lower settings to make it fit.
- If SYCL output looks like gibberish or the speeds are absurd (far above Vulkan with near-zero power), stop and report. Don't publish.
- If the SYCL build fails, send back the last 50 lines of the build output and skip to reporting. Don't try other commits.
- Retry a failed test once at most.

### Report back (to AJ, who passes it to Forge)
Tar up `raw/p2swa-*`, `raw/p2-*` and the `build_sycl.sh` output, plus the output of `pacman -Q | grep -iE "oneapi|level-zero|compute-runtime"`.
Done when: the Gemma variant table exists, `phase2_summary.md` has every cell as ok or oom (or the SYCL build failure is documented), and `env.txt` records the oneAPI and compute-runtime versions.
