# Phase 3 plan and handoff: quality checks

**Goal:** Phases 0–2 measured speed. Phase 3 measures whether the answers are any good. It uses the default engine (SYCL with flash attention on), with temperature 0 so runs are repeatable. Gemma's server keeps `--ctx-checkpoints 0`.

## What it tests (per model, target under 20 minutes)
| Section | Count | How it's graded |
|---|---|---|
| Coding | 10 Python tasks | Runs the model's code against the tests (pass/fail) |
| Tool calling | 10 prompts, 4 tools | Checks the right tool and arguments (2 cases should make no call) |
| Notes recall | 5 questions | Answers from our own findings files (~14 KB in context), checked by keyword |
| Writing | 5 prompts | Not auto-graded; goes into a blind packet AJ ranks |

**Repo tasks (optional):** put tasks from AJ's own repos in `tasks/coding_repo.json`, using the same format (`id`, `prompt`, `test`). They're picked up automatically.

## Run
```
tar xzf b65-phase3.tar.gz && cd b65-phase3
export SYCL_BIN=~/src/llama.cpp/build-sycl/bin
DRY=1 ./phase3.sh        # one model, 2 items per section, ~3 min
./phase3.sh              # all three models
```
Requires Python 3 and the same SYCL build as Phase 2 and Phase 1S. The server runs with `--jinja` so tool calls work.

## Stop rules
- If a model scores 0 on every tool-calling prompt in the dry run, its chat template isn't handling tools. Note it, upload the server log, and keep going.
- If output is garbled or loops, stop and upload what you have.
- If a coding task hangs, the test is killed after 20 s and counts as a fail. That's expected.

## Upload
Upload `raw/p3-*` as one tarball. It contains the scores, `phase3_summary.md` and `blind_packet.md`. Rank the answers in `blind_packet.md` best to worst, without opening `.blind_key.json`, then send me your rankings.

## Caveats for any post
- This is a small, self-made test set. It's a sanity check, not a leaderboard.
- Temperature 0, one try per task, so the results are the model's first attempt.
- Thinking models (Qwen) may use more tokens, so compare total time with that in mind.

## After this
- Gemma's server-prefill diagnostic on SYCL is still open.
- Phase 1.5, the registry recipes, waits on @0xSero.
- Phase 4 is the canary rerun after driver or oneAPI updates.
