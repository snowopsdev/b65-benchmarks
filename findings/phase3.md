# Arc Pro B65 benchmark: Phase 3 findings (quality checks)

Run `p3-20261013-135609`, 2026-10-13, 1:56–2:27 PM ET. Package: `b65-phase3-p3-20261013-135609.tar.gz`.

## Setup
- **Engine:** llama-server, SYCL build 11574 (`8bb3cf0d2`), flash attention on, `--jinja`, 32K context.
- **Gemma flags:** `--ctx-checkpoints 0 -b 2048 -ub 2048`, its SYCL default after the Gemma diagnostic.
- **Sampling:** temperature 0, one try per task.
- **Token caps (Forge's kit):** 2,048 for coding and writing, 1,024 for tools and notes.
- **Tasks:** Forge's kit. The notes corpus uses the verified Phase 1 findings; see `b65-phase3/README.md`.
- **Caveat:** this is a small, self-made test set. It's a sanity check, not a leaderboard.

## Scores

| Model | Coding (10) | Tool calling (10) | Notes recall (5) | Time, all 30 tasks | Completion tokens |
|---|---|---|---|---|---|
| Muse Glimmer 28B | **10** | **10** | **5** | **8 min 11 s** | 11,684 |
| Qwen 3.8 27B | 9 | **10** | **5** | 10 min 9 s | 13,326 |
| Gemma 4 31B QAT | 9 | **10** | **5** | 11 min 48 s | 13,410 |

### Writing, ranked blind by AJ (1 = best of three)
AJ ranked every prompt from `blind_packet.md` before the key was opened. The ranks and the unblinded mapping are in `b65-phase3/writing_ranks.json`.

| Model | w01 LinkedIn post | w02 SEO vs AEO | w03 Why local AI | w04 Decline email | w05 Clarity rewrite | 1st places | Mean rank |
|---|---|---|---|---|---|---|---|
| **Gemma 4 31B QAT** | 3 | **1** | **1** | 2 | **1** | **3** | **1.6** |
| Qwen 3.8 27B | **1** | 2 | 2 | 3 | 3 | 1 | 2.2 |
| Muse Glimmer 28B | 2 | 3 | 3 | **1** | 2 | 1 | 2.2 |

**Caveats:**
- One rater and five prompts.
- AJ ranked the first-shown answer (A) last on all five prompts. A was a different model across prompts (Gemma, Muse, Muse, Qwen, Qwen), so this doesn't single out a model, but it may be position bias. No adjustment was made.

## Findings
1. **There's no single best model.** Muse leads on coding and speed, while Gemma leads on writing (blind). All three tie on tool calling and notes recall.
2. **All three models are strong on these tasks.**
   - All three got every tool call right, including the two prompts that should make no call.
   - All three got every notes-recall question right, with specific answers ("43.1 W", "`--ctx-checkpoints 0`", "Qwen 3.8 27B regressed at 32K").
3. **The only coding failure is the same task for two models,** c08: extract `<link rel="canonical">` with the standard library. Qwen and Gemma both used the whole 2,048-token budget thinking (8,568 and 7,692 characters of reasoning) and never wrote code. Muse thought for 2,861 characters and passed. The failures are about thinking length under the cap, not wrong code.
4. **Side check** (`raw/p3-c08check-20261013-142822`, not part of the score): c08 was re-asked alone with an 8,192-token cap.
   - **Gemma:** finished in 3,326 tokens, and its `HTMLParser` solution passes. It just needed more room.
   - **Qwen:** still hadn't answered after 8,192 tokens (372 s). Its reasoning kept listing possible hidden tests with ever more exotic Unicode spaces (` `, ` `, …). No text repeats verbatim, but it's going round in circles. That's close to the handoff's "loops" stop rule, so it's flagged here rather than treated as an ordinary fail.
5. **Muse is the quickest and the most token-efficient:** 8 min for all 30 tasks and the fewest completion tokens, despite also thinking (about 37K reasoning characters overall). Qwen and Gemma spend most of their extra time on coding (305 s and 401 s, against Muse's 187 s), and c08 alone took 89 s and 100 s.
6. **All three are thinking models in this setup:** each returned separate reasoning, 36K–40K characters across the 30 tasks. Compare total time with that in mind, as the handoff notes.

## Checks
- Apart from the two c08 cases, every reply finished normally: `stop`, or `tool_calls` for tool prompts. No writing reply hit its token cap.
- The device precheck confirmed `level_zero:0` = Arc Pro B65. The run had no errors.
- Dry run: `raw/p3-dry-20261013-135213` (Qwen, 2 items per section, 6/6).

## Open
- **Writing:** ranked. Gemma leads (mean rank 1.6). A second rater, or more prompts, would firm it up.
- **Qwen's runaway reasoning on c08:** worth checking whether a thinking budget or `/no_think` style prompt changes it, before using Qwen for agent-style coding.
- **Token cap:** a 4,096-token coding cap would remove the cap effect for Gemma. Whether to change the test is Forge's call; these scores are first attempts at 2,048 as specified.
