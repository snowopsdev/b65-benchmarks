# Arc Pro B65 benchmark: Phase 2 findings (Vulkan vs SYCL)

Run `p2-20261013-091509`, 2026-10-13, 9:15–10:53 AM ET. All 63 tests ok, no out-of-memory results. Package: `b65-phase2-p2-20261013-091509.tar.gz`.

## Setup
- **Engines:** the same llama.cpp commit `8bb3cf0d2` (build 11574) built two ways:
  - Vulkan: the existing build, Mesa 26.2.2.
  - SYCL: a new build, oneAPI DPC++ 2026.0.0, oneMKL SYCL 2026.0.0, intel-compute-runtime 26.31.39395.13, level-zero-loader 1.32.0, IGC 2.40.13. JIT only, no AOT.
- **Packages:** Arch no longer ships `intel-oneapi-basekit`, so the equivalent split packages were installed. They're listed in `b65-phase2/packages.txt`.
- **Device:** the SYCL device is `level_zero:0`, "Intel(R) Arc(TM) Pro B65 Graphics". Every result's `gpu_info` names the B65; the RTX 3080 isn't a Level Zero device.
- **Kernel and OS:** 7.2.5-3-omarchy, Omarchy 4.0.4.
- **Tests:** llama-bench, 5 reps each:
  - pp512, pp4096, pp16384
  - tg128 at depth 0, 4K, 16K and 32K
- **Configurations:**
  - Vulkan with flash attention off (the Phase 0.5 setting).
  - SYCL with flash attention off, and with it on.
- **Power:** GPU board power from xe hwmon only, averaged over the timed reps. No wall meter. The board power cap is 200 W.

## Headline
**SYCL with flash attention on is 21.8% faster than Vulkan on decode and 31.2% faster on prefill, averaged over all three models.** That clears the plan's +10% decode rule.

**Decision (Forge, 2026-10-13):** SYCL with flash attention on is the default engine. Per the plan, Phase 1 is rerun on SYCL with flash attention on.

| SYCL setting vs Vulkan (FA off) | Decode, mean of 12 | Prefill, mean of 9 |
|---|---|---|
| **SYCL, FA on** | **+21.8%** (−5.6% to +51.3%) | **+31.2%** (−0.9% to +56.2%) |
| SYCL, FA off | +4.4% (−22.2% to +24.2%) | +27.5% (+10.5% to +48.9%) |

Per model, SYCL with FA on vs Vulkan:

| Model | Decode | Prefill |
|---|---|---|
| Qwen 3.8 27B | +10.4% | +49.8% |
| Gemma 4 31B QAT | +18.6% | +9.0% |
| Muse Glimmer 28B | +36.5% | +34.9% |

## Results (tok/s, mean of 5)

| Model | Test | Vulkan FA off | SYCL FA off | SYCL FA on | Best SYCL vs Vulkan |
|---|---|---|---|---|---|
| Qwen 3.8 27B | pp512 | 445.55 | **663.55** | 639.96 | +49% |
| | pp4096 | 431.84 | 635.10 | **645.52** | +49% |
| | pp16384 | 388.17 | 571.17 | **606.15** | +56% |
| | tg128 | 19.08 | **23.69** | 23.68 | +24% |
| | tg128 @4K | 18.84 | 21.87 | **22.22** | +18% |
| | tg128 @16K | 17.69 | 17.79 | **18.63** | +5% |
| | tg128 @32K | **16.16** | 14.11 | 15.26 | −6% |
| Gemma 4 31B QAT | pp512 | 414.48 | **468.64** | 410.75 | +13% |
| | pp4096 | 378.54 | **418.36** | 414.44 | +11% |
| | pp16384 | 335.29 | 384.63 | **397.37** | +19% |
| | tg128 | 19.16 | 22.18 | **22.45** | +17% |
| | tg128 @4K | 17.39 | 17.09 | **20.46** | +18% |
| | tg128 @16K | 16.00 | 13.37 | **18.29** | +14% |
| | tg128 @32K | 12.84 | 9.99 | **16.06** | +25% |
| Muse Glimmer 28B | pp512 | 539.92 | 688.19 | **691.22** | +28% |
| | pp4096 | 483.03 | 580.08 | **651.98** | +35% |
| | pp16384 | 429.73 | 508.84 | **608.70** | +42% |
| | tg128 | 20.94 | 25.15 | **25.66** | +23% |
| | tg128 @4K | 18.71 | 21.07 | **24.64** | +32% |
| | tg128 @16K | 16.79 | 18.41 | **23.56** | +40% |
| | tg128 @32K | 14.73 | 15.74 | **22.29** | +51% |

The "Best SYCL" column takes whichever SYCL setting is faster on each test. Against the chosen default alone (SYCL with flash attention on), prefill is lower in three places:
- Gemma pp512: −0.9%, a tie, not +13%.
- Gemma pp4096: +9.5%, not +11%.
- Qwen pp512: +44%, not +49%.

Decode is the same either way, except that Qwen at 32K is −5.6% with flash attention on and −12.7% with it off. From here on, the share cards compare SYCL with flash attention on against Vulkan.

Board W per cell is in `phase2_summary.md` and `backend_compare.csv`.

## Findings
1. **SYCL is the faster engine on this card,** as long as flash attention is on.
   - Decode at 0 context goes from 19.1–20.9 tok/s on Vulkan to 22.4–25.7 on SYCL.
   - At 32K context it goes from 12.8–16.2 to 15.3–22.3.
   - Muse gains the most (+51% at 32K).
2. **Flash attention flips between engines.**
   - On Vulkan it hurt everywhere (Phase 0.5).
   - On SYCL it helps decode by 18.5% on average, and more as context grows: Gemma +61% and Muse +42% at 32K, Qwen +8%.
   - On SYCL it barely changes prefill (+3%).
   - SYCL with flash attention off is slower than Vulkan for Gemma decode at depth (−22% at 32K), so the setting matters.
3. **There's one exception: Qwen at 32K.** SYCL is 5.6% slower than Vulkan there with flash attention on (15.26 vs 16.16), and 12.7% slower with it off. Qwen's decode advantage shrinks with depth: +24%, +18%, +5%, −6%.
   - At 16K Qwen is only +5.3%, so SYCL clears +10% at 0 and 4K context for every model, but not at 16K for Qwen.
   - Qwen's average decode gain, +10.4%, only just clears the bar.
   - **The order of falloff with context changes.** From 0 to 32K tokens of context:
     - Qwen: −15% on Vulkan, −36% on SYCL. It falls off fastest on SYCL.
     - Gemma: −33% on Vulkan, −28.5% on SYCL.
     - Muse: −30% on Vulkan, −13% on SYCL. Its falloff is gentlest on SYCL.
4. **Gemma passes the registry's 15 tok/s line at 32K on SYCL:** 16.06 tok/s, against 12.84 on Vulkan. Its falloff with context is still steep (−28.5%); the gain comes from a faster start, not a flatter curve.
5. **Decode is closer to the bandwidth ceiling.** SYCL decode at 0 context reaches about 400–430 GB/s of the published 608 GB/s (65–71%), compared with Vulkan's 53–58% in Phase 0. This uses the same approximation as Phase 0: tok/s × file size.
6. **SYCL is more efficient, and it doesn't always draw more power.**
   - Decode tokens per joule average 0.115 on SYCL with flash attention on, against 0.100 on Vulkan (+15%). Decode at 0 context improves for all three:
     - Qwen: 0.112 to 0.122
     - Gemma: 0.105 to 0.128
     - Muse: 0.119 to 0.129
   - Power with SYCL and flash attention on, compared with Vulkan:
     - Prefill: 13–33 W more for every model.
     - Qwen and Muse decode: 18–26 W more, except Qwen at 16K (+3 W) and at 32K (−11 W).
     - **Gemma decode: 4–12 W less.**
   - Overall, decode board power is 165–199 W on SYCL and 165–182 W on Vulkan.
   - Muse's SYCL decode at 0 context averaged 199.4 W against the 200 W cap, so it may be power-limited there. Throttling wasn't measured.
   - Prefill is 3.14 tok/J on SYCL with flash attention on, against 2.78 on Vulkan.
7. **The Vulkan numbers are stable.** Vulkan with flash attention off reproduces the Phase 0.5 and Phase 1 values within 0.4% on all 21 tests, so the differences come from the engine, not drift. The largest run-to-run spread is 2.1% (Muse, SYCL with flash attention off, tg @4K); everything else is under 2%.

## Checks
- **Output isn't gibberish.** Each model wrote the same 120-token answer at temperature 0 on SYCL and on Vulkan, in llama-server:
  - Qwen, SYCL flash attention off (`raw/p2-spot-20261013-091431`): output identical to Vulkan.
  - Gemma and Muse, SYCL flash attention on (`raw/p2-spot-20261013-105352`): Muse identical; Gemma coherent and the same until a small wording difference. That difference is expected, because flash attention on vs off changes the arithmetic order.
  - Qwen, SYCL flash attention on (the chosen default; `raw/p2-spot-20261013-110712`): identical to Vulkan as well. All three models are now checked on the default setting.
  - SYCL speed in these runs matched llama-bench: Qwen 23.9, Gemma 22.4, Muse 25.9 tok/s.
- **The speeds aren't absurd.** SYCL draws more power than Vulkan, not near zero.
- **Dry run:** `raw/p2-dry-20261013-091018`. Its `env.txt` recorded a device-table header instead of the SYCL version; that's fixed for the full run.

## Step 0 (Gemma llama-server)
This was answered before Phase 2 by `b65-phase1/raw/p1-swa-20261013-081841`.
- **The fix is `--ctx-checkpoints 0`:** Gemma's 512-token time to first token drops from 25.3 s to 1.36 s.
- **`--swa-full` runs out of VRAM at 32K.**
- Details are in `phase1.md`.

## What's not covered yet
- **llama-server on SYCL wasn't benchmarked.** The plan's Phase 1 time-to-first-token rerun on SYCL (about an hour) would cover it. That rerun should include Gemma with `--ctx-checkpoints 0`, plus a check that 32K context still fits with SYCL and flash attention on.
- **Qwen's long-context regression:** whether SYCL tuning (for example `GGML_SYCL_*` options) changes Qwen at 32K is untested.
- **vLLM on XPU** (the plan's stretch step) wasn't attempted.

## Posting status
- **Cleared:** everything in this run. Nothing is held in `holds.conf`.
- **When posting:** say "best SYCL setting" or "SYCL with flash attention on", and mention Qwen's −6% at 32K so the summary isn't one-sided.

## Review of Forge's Phase 2 findings (2026-10-13)
These are checked against `backend_compare.csv`. The verdict, the table, the Gemma and Muse flash-attention numbers, the biggest wins, and the Muse tok/J example are all correct. Corrections:
- **"Clears the 10% decode rule on all three models at short and mid context."** True at 0 and 4K context (+17–24% and +18–32%). At 16K, Qwen is only +5.3%.
- **"SYCL draws ~10–30 W more."** That holds for prefill (+13–33 W) and for most Qwen and Muse decode. Gemma's decode on SYCL draws 4–12 W *less*, and Qwen at 32K draws 11 W less.
- **"Gemma's long-context decode problem mostly closes."** Gemma is 25% faster at 32K and now above 15 tok/s, but its 0-to-32K falloff only eases from −33% to −28.5%. Meanwhile Qwen's falloff gets worse on SYCL (−15% to −36%).
- **"SYCL best vs Vulkan" column.** It mixes both SYCL settings. Against the chosen default (flash attention on), Gemma pp512 is −0.9% rather than +13%.
- **Output check.** The Qwen check had been run with SYCL flash attention off. It has now been rerun with flash attention on, and the output is identical.
