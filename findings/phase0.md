# Arc Pro B65 benchmark: Phase 0 findings

Run `20261012-140638`, 2026-10-12, started 2:06 PM ET, finished 3:30 PM ET. Package: `b65-phase0-20261012-140638.tar.gz`.

## Setup

- **GPU:** Intel Arc Pro B65, 32 GB (BMG G31, PCI ID 8086:e222). About 29.3 GB is usable; Vulkan reports the rest as driver-reserved with nothing loaded. The RTX 3080 drives the display and was excluded (`GGML_VK_VISIBLE_DEVICES=1`, and every test's `gpu_info` was checked for the B65).
- **Host:** Ryzen 7 5700X, 48 GB RAM (46 GiB usable), CPU governor set to performance.
- **OS:** Omarchy 4.0.4 (Arch Linux, Hyprland 0.56.2), kernel 7.2.5-3-omarchy. The run's `env.txt` says `omarchy=unknown` because the script read the wrong file; that's fixed for future runs.
- **Driver:** Mesa 26.2.2 (vulkan-intel, ANV) on the xe kernel driver. Cooperative-matrix acceleration (KHR_coopmat) is available.
- **Engine:** llama.cpp `llama-bench`, build 11574 (commit 8bb3cf0d2), built from source with GCC 16.2.1, Vulkan backend.
- **Bench flags:** `-ngl 99 -fa on -r 5`. Each test gets llama-bench's warmup run plus 5 measured runs, and the **mean** is reported. For the depth tests the warmup runs before the context is filled, so the first measured run is the first decode at that depth.
- **PCIe:** 4.0 x4, in a slot wired through the X570 chipset (the card supports 5.0 x16). The GPU endpoint itself reports 2.5 GT/s x1, which is an artifact of Arc's on-card PCIe switch; the real link is read at the upstream bridge. ReBAR is on, with a 32 GB BAR.
- **Power:** GPU board power only, from the xe hwmon `card` energy counter sampled at 10 Hz, averaged over the timed runs only (not model load or warmup). Board power cap: 200 W. No wall meter.

## Models

| Model | Params (llama.cpp) | Quant | File | Size | sha256 |
|---|---|---|---|---|---|
| Qwen 3.8 27B | 27.32B | Q4_K_M | Qwen3.8-27B-Q4_K_M.gguf | 16.8 GB | e00082f7…e520 |
| Gemma 4 31B QAT | 30.70B | Q4_0 | gemma-4-31B-it-QAT-Q4_0.gguf | 17.7 GB | 6f63619c…6a7b |
| Muse Glimmer 30B | 27.85B | Q4_K_M | Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf | 16.8 GB | 4cc57c0f…f60e |

All three are from lmstudio-community: `Qwen3.8-27B-GGUF`, `gemma-4-31B-it-QAT-GGUF` and `Muse-Glimmer-30B-GGUF`. LM Studio doesn't keep the Hugging Face commit locally, so the commits still need to be recorded. Full hashes are in `raw/models.sha256`.

**Naming:** Muse Glimmer's release name is 30B, but llama.cpp counts 27.85B parameters. Pick one name and use it everywhere. The share cards currently say "Muse Glimmer 30B" and the draft replies say "28B".

## Results (tokens per second, mean of 5 runs)

| Model | pp512 | pp4096 | pp16384 | tg128 | tg @4k depth | tg @16k depth |
|---|---|---|---|---|---|---|
| Qwen 3.8 27B | 434.2 | 358.1 | 221.1 | 19.02 | 18.75 | 17.33 |
| Gemma 4 31B QAT | 294.8 | 111.4 ⚠ | 38.0 ⚠ | 18.45 | 16.43 | 14.26 † |
| Muse Glimmer 30B | 522.2 | 375.0 | 274.5 | 20.93 | 15.10 | 11.23 |

All 18 tests passed, and none ran out of memory. Run-to-run variation is under 1% except for Gemma's tg @4k (1.0%) and tg @16k (4.5%).

† Gemma tg @16k: the first run was 13.12 tok/s, and the next four were 14.51–14.57. The first run was the first decode at 16K depth (see Bench flags), so the 4.5% spread comes from one cold run. The reported mean of 14.26 includes it; the median is 14.52.

## Power (GPU board, average over timed runs)

| Model | Prefill (W) | Decode (W) | Decode tokens per joule |
|---|---|---|---|
| Qwen 3.8 27B | 142–149 | 167–170 | 0.104–0.112 |
| Gemma 4 31B QAT | 143–152 | 164–179 | 0.087–0.103 |
| Muse Glimmer 30B | 136–156 | 130–175 | 0.086–0.119 |

Idle draw with no model loaded was 43.1 W, measured over 30 s at the start of the run.

## Findings

1. **The data is clean and publishable.** Device pinning was correct, every test passed, run-to-run variation is small, and the model hashes are recorded.
2. **Decode speed is close across models at short context (18.4 to 20.9 tok/s), but the order changes at 16K.** Qwen loses only 9% from 0 to 16K context, Gemma loses 23%, and Muse loses 46%.
3. **Gemma's prefill collapses, which is likely a software problem.** Prefill drops from 295 to 38 tok/s as the prompt grows, and the pp16384 test alone took 43.3 minutes. Over the same range Qwen and Muse roughly halve (−49% and −47%). The leading hypothesis is the Vulkan flash-attention path combined with Gemma's attention layout. That's untested, so don't publish Gemma's prefill numbers until a rerun with `-fa 0` (Gemma only) confirms or rules it out.
4. **Decode reaches about 53–58% of the memory-bandwidth ceiling.** The ceiling is approximated as 608 GB/s divided by the file size: Qwen 36.2 tok/s (19.02 measured, 53%), Gemma 34.4 (18.45, 54%), Muse 36.3 (20.93, 58%). This is typical for llama.cpp on Vulkan and gives an honest "headroom" angle. Two caveats: 608 GB/s is the published spec and hasn't been measured here, and file size only approximates the bytes read per token.
5. **Registry check (decode must be at least 15 tok/s):** Qwen passes at every depth. Gemma fails at 16K (14.3). Muse is borderline at 4K (15.1) and fails at 16K (11.2). The registry measures with its own harness, not these llama-bench numbers.
6. **PCIe 4.0 x4 through the chipset:** with every layer on the GPU, it should mainly affect model load time rather than these timed tests. Its effect wasn't measured. Mention it in the methodology section.
7. **Board power stays under the 200 W cap.** At short context decode draws more than prefill (170–179 W against 136–156 W). That reverses at long context for Muse, whose decode falls to 148 W at 4K and 130 W at 16K, along with its speed.

## Gaps and next steps

- Rerun Gemma's prefill (pp512, pp4096, pp16384) with `-fa 0` as a separate run. Optionally run all three models with `-fa 0` as a control.
- Record each model's Hugging Face commit, which the registry recipes need. The repo names are listed above.
- Optional: add prefill tok/J to `report.py`. It's left blank for prefill rows by design, since the metric was defined for decode.
- Optional: warm up at each test's depth (or drop the first run) so depth tests don't include a cold first run.
- ~~Record the Omarchy version~~: it's 4.0.4, and `run.sh` now records it.
- Phase 1: serving and time-to-first-token runs, a table of which context sizes fit, and idle power with a model loaded.
- Phase 1.5: registry recipes, blocked until @0xSero answers whether llama.cpp Vulkan counts.

## Cleared for posting

- **Cleared:** decode speed for all three models (footnote Gemma's 16K value, or give the median), Qwen's full row, the power numbers, and the methodology.
- **Hold:** all of Gemma's prefill numbers (pp512, pp4096, pp16384) until the `-fa 0` rerun. These are listed in `holds.conf`, and the share cards withhold them on the server side.

### Notes on the draft replies

- Reply 1: "Muse Glimmer 28B" should match whatever name you settle on (see Naming).
- Reply 2: 142–170 W for Qwen is correct.
- Reply 3: "1 warmup plus 5 runs per test, mean reported" is correct.
