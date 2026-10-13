# Phase 3 kit: quality checks (Forge kit, local changes)

Plan, stop rules and upload instructions: `HANDOFF.md`. Runs: `raw/p3-*` (dry: `raw/p3-dry-*`). Live view: `/p3`. Share cards: the Phase 3 tab.

## Local changes
- **`phase3.sh`:**
  - Prechecks that SYCL0 is the B65 with at least 28 GB VRAM free. The kit's check, which looked for "intel" in the server log, could never pass, because the SYCL server log doesn't name the device; it's been removed.
  - `kill` of a server that has already exited no longer aborts the run under `set -e`.
  - Writes `pid` and `done` markers and `>>` progress lines for the dashboard. `env.txt` records the device and Gemma's flags.
  - Gemma also gets `-b 2048 -ub 2048`, its SYCL server default after the Gemma diagnostic (16K time to first token 58 s → 31 s). This changes speed, not grading.
- **`quality.py`:**
  - Records `finish_reason` (`length` means the reply hit max_tokens), completion tokens and reasoning length for every item, so truncated thinking-model replies are visible.
  - A failed coding, notes or writing request is recorded as a fail, instead of crashing the model's whole run. Only the tools section was protected before.
- **`tasks/notes/b65-phase1-findings.md`:** replaced with the verified `findings/phase1.md`. Forge's copy was the early draft, written before the Gemma rerun, which recommends `--swa-full`. With it, n02 ("What server flag fixed Gemma's slow time to first token?") couldn't be answered correctly from the notes. The corpus grows from about 14 KB to 19 KB. The other notes files are unchanged, and the questions are unchanged.

## Dry run (`raw/p3-dry-20261013-135213`, Qwen only, 2 items per section)
- Coding 2/2, tools 2/2, notes 2/2. All replies finished normally (`stop` / `tool_calls`).
- One writing reply used 1,755 of its 2,048 tokens (most of them thinking), so watch `finish` in the full run.

## Privacy of the blind key
The dashboard never serves dot-files, so `.blind_key.json` stays out of `/files` until AJ has ranked `blind_packet.md`.
