# Gemma SYCL server prefill diagnostic (Forge kit, local changes)

Question, variants and Forge's decision rule are in `HANDOFF.md`. Runs: `raw/gd-*` (dry: `raw/gd-dry-*`). Live view: `/gd` on the dashboard.

## Local changes to `gemmadiag.sh`
- **The run no longer aborts on a failed variant.** `kill` of a server that already exited (for example after OOM) used to end the script under `set -e`. Also, `find` over the missing `~/.cache/lm-studio` used to abort the script before anything ran; this is guarded with `|| true`, as in the other kits.
- **Precheck:** SYCL0 must be the B65, with at least 28 GB VRAM free.
- **Energy** comes from the xe `card` channel, chosen by label.
- **Run markers:** `pid` and `done` markers for the dashboard; `env.txt` records the device and energy file. Dry runs go to `raw/gd-dry-*`.
- **Extra variant `ckpt0_fa0`** (local addition): the server with flash attention off for Gemma only. This shows whether the SYCL flash-attention path in llama-server is behind the gap.

## Dry run (`raw/gd-dry-20261013-123549`)
- llama-bench pp16384 at ub 512: 397.2 tok/s (Phase 2: 397.4).
- Server ckpt0, first 512-token request: 3.25 s, the same as Phase 1S's cold first rep.
