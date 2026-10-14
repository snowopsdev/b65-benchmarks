# Arc Pro B65: Phase 6 findings (confirming the Phase 5 recipes)

Run `p6-20261013-211819`, 2026-10-13, 9:18–10:13 PM ET (55 min). All three parts completed with no errors. Package: `b65-phase6-p6-20261013-211819.tar.gz`.

- **Versions:** unchanged since Phase 2. Kernel 7.2.5-3-omarchy, Mesa 26.2.2, oneAPI 2026.0, compute-runtime 26.31.39395.13, llama.cpp 11574 (`8bb3cf0d2`).
- **Builds:** SYCL `level_zero:0`, and the pinned Vulkan build with `GGML_VK_VISIBLE_DEVICES=1`.
- **Kit:** Forge's, with the local fixes in `b65-phase6/README.md`.
- **Two fixes affect how to read A:**
  - **Prompt:** the coding prompt now carries Phase 3's system message, so it compares like for like.
  - **Proof of thinking:** a `reasoning_chars` column records whether thinking was actually off.
- **Dry run:** `raw/p6-dry-20261013-205752`.

## A. Coding with thinking off: Phase 3's 10 tasks, 3 tries each

The server ran with `--reasoning-budget 0` and `enable_thinking: false`.
- **Tries:** 1 is greedy; 2–3 use temperature 0.3 with fixed seeds.
- **Token cap:** 4,096.
- **Server:** SYCL, ub 2048.

| Model | Greedy | All tries | Median tokens per answer | Time, 30 tries | Thinking actually off? | Phase 3 (thinking on, 2K cap, greedy) |
|---|---|---|---|---|---|---|
| Qwen 3.8 27B | **10/10** | **30/30** | 130 | 203 s | yes: 0 reasoning characters in 30 of 30 | 9/10 (c08 hit the cap), median 555 tokens, 305 s for 10 |
| Muse Glimmer 28B | 10/10 | 30/30 | 440 | 531 s | **no: it reasoned on 30 of 30** (44,887 characters) | 10/10, median 442 tokens, 187 s for 10 |

1. **Qwen with thinking off passes everything.**
   - It scores 10/10 greedy and 30/30 over all tries, including c08, the task it ran out of tokens on in Phase 3. Here c08 takes 254–280 tokens and 11–12 s.
   - Under Forge's rule (at least 9/10 greedy and 27/30 overall), **"thinking off for coding" becomes the Qwen recipe.**
   - The greedy pass takes 73 s for all 10 tasks, against 305 s in Phase 3, about 4× faster.
2. **Muse can't be switched to thinking off this way.**
   - **The evidence:** it returned separate reasoning on all 30 tries. Its greedy answers match Phase 3 token for token (c01 205 tokens, c02 571), and so does the total time (187.6 s against 187.5 s).
   - **Neither switch works:** not `--reasoning-budget 0`, not `enable_thinking: false`.
   - **What its row measures:** Muse with thinking on and a 4K cap, which passes 30/30. It doesn't show Muse with thinking off.
   - **Qwen's template does have the switch:** its GGUF chat template contains `enable_thinking`. In the header of Muse's GGUF I found neither `enable_thinking` nor an embedded chat template.

## B. Regenerate and edit, checkpoints on vs off

A 6-turn chat of about 9.4–9.5K tokens, followed by five steps. Each cell shows tokens reprocessed and time to first token.
- **SYCL:** ub 2048, flash attention on.
- **Vulkan:** ub 512, flash attention off.

The edits change the question at the end of a user message: "main risk" becomes "main opportunity" or "biggest win". That's why editing the last message only needs about 14 tokens when the cache can roll back, and editing turn 3 has to redo everything after the edit point (about 6.2K).

| Model | Engine | Checkpoints | Regenerate | Edit last message | Edit turn 3 | Back to original |
|---|---|---|---|---|---|---|
| Gemma 4 31B QAT | SYCL | on | 1 · 0.41 s | 14 · 1.7 s | 6,236 · 15.3 s | 6,236 · 18.5 s |
| | SYCL | off | 1 · 0.09 s | 14 · 1.2 s | **9,362 · 18.0 s** | **9,362 · 18.3 s** |
| | Vulkan | on | 1 · **49.4 s** | 14 · **99.1 s** | 5,204 · **135.5 s** | 5,204 · **135.4 s** |
| | Vulkan | off | 1 · 0.09 s | 14 · 0.8 s | **9,362 · 78.4 s** | **9,362 · 78.5 s** |
| Qwen 3.8 27B | SYCL | on | 4 · 0.17 s | 1,531 · 2.2 s | 6,250 · 10.1 s | 1,531 · 3.2 s |
| | SYCL | off | **9,413 · 11.3 s** | **9,413 · 11.3 s** | **9,413 · 11.5 s** | **9,413 · 11.7 s** |
| Muse Glimmer 28B | SYCL | on | 1 · 0.26 s | 8 · 0.40 s | 6,292 · 9.6 s | 9 · 0.72 s |
| | SYCL | off | 1 · 0.20 s | 8 · 0.33 s | **9,502 · 11.7 s** | **9,502 · 11.7 s** |

Regenerating a second time gave the same result as the first in every setup.

1. **Checkpoints off isn't safe as a default for every model. It breaks Qwen.**
   - With checkpoints off, Qwen re-reads the entire chat on every regenerate and every edit: 9,413 tokens and 11.3 s, against 4 tokens and 0.17 s with them on.
   - This is the control model in Forge's plan, and in Phase 5's append-only test it looked fine. The server log doesn't say why it can't roll back.
2. **Gemma and Muse with checkpoints off handle regenerate and edit-last fine.** They reprocess 1–14 tokens, and are slightly faster than with checkpoints on.
   - Under Forge's Gemma rule (whole context on regen or edit-last with checkpoints off, but not with them on), Gemma doesn't trigger "keep checkpoints on". For Gemma alone, `--ctx-checkpoints 0` would be safe.
3. **Earlier edits cost more with checkpoints off, for every model.**
   - **With checkpoints off:** editing turn 3 re-reads the whole chat in all 4 setups (9.4–9.5K tokens).
   - **With checkpoints on:** it re-reads only from the edit point (5.2–6.3K tokens).
   - **Going back to the original chat:**
     - **Muse:** with checkpoints on, it restores the original from a checkpoint, 9 tokens and 0.7 s against 11.7 s.
     - **Qwen:** with checkpoints on, it reprocesses one turn.
     - **Gemma:** reprocesses from the edit point either way.
4. **Gemma on Vulkan with checkpoints on stays the outlier:**
   - **Cost per request:** 49 s even when only 1 token is reprocessed, and 99–135 s otherwise.
   - **Checkpoints off is faster for every step there,** even when it re-reads the whole chat (78 s against 135 s for the early edit).
5. **What this means for the defaults** (Forge's call):
   - **Qwen:** keep checkpoints on (the default).
   - **Gemma on SYCL and Muse:** off is fine for regenerate and edit-last. It costs 2–3 s more on edits to earlier turns, and Muse loses its fast way back to the original chat.
   - **Gemma on Vulkan:** off is much faster in every case.
   - **So:** `--ctx-checkpoints 0` can't be a default for every model.

## C. Canary at ub 2048 against the Phase 5 baseline

All 8 tests (Qwen and Muse; prefill 512 and 16K; decode at 0 and at 16K) are within 0.03% of `baseline_ub2048.json`: Qwen 640.00 / 824.13 / 23.69 / 18.86 and Muse 690.87 / 820.72 / 25.64 / 23.44 tok/s. Nothing has drifted, so the new canary is ready.
- **Routine canary:** `b65-phase4/canary.sh`. Its main rows now default to `UB=2048` and compare with `baseline_ub2048.json`; `UB=512` uses the original baseline. See `b65-phase4/README.md`.
- **Board W:** the Phase 6 Part C kit doesn't record it (tok/s only). The routine canary does.

## Open, for Forge
- **Checkpoint defaults per model.** Qwen keeps them on. Gemma on Vulkan wants them off. Gemma on SYCL and Muse depend on whether early edits matter (off costs a full re-read there).
- **Muse thinking off.** Its template doesn't respond to `enable_thinking` or `--reasoning-budget 0`. If a no-thinking Muse is wanted, it needs a different switch (for example a system-prompt convention, if the model has one). That would be a new test.

---
## Forge review (checked against the raw CSVs)

The summary tables match `A_coding.csv`, `B_regen.csv` and `C_canary.csv`. I re-counted part A: Qwen passes 30/30 with 0 reasoning characters, and Muse passes 30/30 with reasoning on all 30 tries (44,887 characters). The local fix that adds Phase 3's system message is correct, since my kit had left it out.

**Final decisions**
1. **Qwen recipe:** thinking off for coding (`--reasoning-budget 0`). It scores 10/10 greedy and 30/30 overall, with a median of 130 tokens and about 4× less time than Phase 3. This is confirmed across 10 tasks, not just one.
2. **Muse:** no thinking-off switch was found. Its 30/30 is with thinking on and a 4K cap, and it already uses a similar number of tokens to its Phase 3 run. A Muse thinking-off test isn't worth a phase unless the model card documents a switch.
3. **Checkpoint defaults, per model:**
   - **Qwen:** checkpoints **on** (the default). With them off, every regenerate and edit re-reads the whole chat (9.4K tokens, 11.3 s, against 0.17 s with them on). My best guess is that Qwen 3.8 keeps a recurrent or hybrid state that can't rewind even one token without a checkpoint, but the log doesn't confirm that.
   - **Muse:** checkpoints **on**. Turning them off gains under 0.1 s, and loses fast edits to early turns and the fast return to the original chat (0.7 s against 11.7 s).
   - **Gemma on SYCL:** checkpoints **on** for chat UIs, where edits to early turns are cheaper (15.3 s against 18.0 s). Use `--ctx-checkpoints 0` for append-only agent loops, which Phase 5 measured at 3.2 s against 6.0 s per turn.
   - **Gemma on Vulkan:** checkpoints **off**, which is faster at every step (49–135 s with them on).
   - **Rule:** leave checkpoints at the default, except for Gemma on Vulkan and Gemma agent loops. The Phase 5 suggestion that `--ctx-checkpoints 0` could be a default everywhere is withdrawn.
4. **Canary:** all 8 tests are within 0.03% of the baseline. `b65-phase4/canary.sh` with `UB=2048` is now the routine check, and the fix your agent made to the Vulkan loop (it now uses `VUB`) is right.

The B65 benchmark plan is complete. Phase 1.5, which re-checks the registry recipes, is still blocked on @0xSero. The round 2 blind writing ranks are still waiting on AJ.
