# Intel Arc Pro B65 benchmarks

Measured local-LLM performance on an Intel Arc Pro B65 32 GB: llama.cpp **Vulkan and SYCL**, three 4-bit GGUF models, throughput, server latency, board power, cache behavior, and small quality checks. The main experiments ran on October 12–13, 2026, with registry checks on October 14.

- **[Article: the settings I'd use](findings/article-b65-settings.md)** — backend comparisons, per-model results with standard deviations, practical commands, and an experiment log.
- **[Recommended settings](findings/recommended-settings.md)** — the final recipe and its supporting measurements.
- **[Findings and raw-run index](findings/README.md)** — each experiment, its findings, and run identifiers; dry runs are identified separately and excluded from conclusions.
- **[Frozen article evidence](https://github.com/snowopsdev/b65-benchmarks/tree/b65-evidence-2026-10-15)** — the evidence snapshot cited by the article. Article citations use the full commit ID so they continue to identify the same files after updates.

**Tested stack:** llama.cpp build 11574 (`8bb3cf0d2`), oneAPI 2026.0, compute-runtime 26.31.39395.13, Mesa 26.2.2, kernel 7.2.5-3-omarchy. B65 only; an RTX 3080 drove the display and was excluded from inference. Power readings measure the GPU board, not the whole PC.

The repository includes scripts, raw JSONL/CSV/logs, model-file SHA-256 manifests, findings, and share-card images. Model weights and vendor/build directories are excluded. Recorded local paths and device identifiers in the raw files describe the test machine; adjust paths and device selection when reproducing a run.

## Layout
| Path | What |
|---|---|
| `findings/` | Per-phase findings (verified against the raw data) + an index |
| `run.sh`, `report.py`, `powerwin.py`, `models.conf` | Phase 0 kit (prefill + decode sweep); `raw/` and `charts/` are its runs; `results.csv` is the merged table |
| `b65-phase05/` | Phase 0.5 kit (flash attention off vs on) and its `raw/` runs |
| `b65-phase1/` | Phase 1 kit (context depth, llama-server, loaded idle), the Gemma checkpoint rerun script, Forge's `HANDOFF.md` and its `raw/` runs |
| `b65-phase2/` | Phase 2 kit (Vulkan vs SYCL), local fixes listed in its README, and its `raw/` runs |
| `dashboard/` | Live tailnet dashboard + share cards (`server.py`, one page per phase, `share.html`) |
| `holds.conf` | Results withheld from share cards (currently none) |
| `dist/` | Release tarballs (not committed; regenerated from the raw runs) |

Raw run folders are never edited after a run; new runs always go to new folders.

## Phase 0 Vulkan setup (no sudo needed)
The commands below reproduce the initial Vulkan baseline. For the final SYCL setup, see [the article's build instructions](findings/article-b65-settings.md#reproducing-the-build-and-a-throughput-test) and [the Phase 2 kit](b65-phase2/README.md).

Everything lives in the project dir; `vendor/`, `.venv/` are not part of the results.

    uv venv .venv && uv pip install --python .venv/bin/python cmake ninja matplotlib
    # headers matching the installed vulkan-icd-loader (1.4.357), installed to vendor/prefix
    git clone --depth 1 -b v1.4.357 https://github.com/KhronosGroup/Vulkan-Headers vendor/Vulkan-Headers
    git clone --depth 1 -b vulkan-sdk-1.4.357 https://github.com/KhronosGroup/SPIRV-Headers vendor/SPIRV-Headers
    # (cmake -B build + cmake --install build -DCMAKE_INSTALL_PREFIX=vendor/prefix for each)
    git clone https://github.com/ggml-org/llama.cpp vendor/llama.cpp && git -C vendor/llama.cpp checkout b11574
    cmake -S vendor/llama.cpp -B vendor/llama.cpp/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DGGML_VULKAN=ON -DGGML_CUDA=OFF -DGGML_NATIVE=ON -DLLAMA_CURL=OFF \
      -DCMAKE_PREFIX_PATH=$PWD/vendor/prefix -DVulkan_INCLUDE_DIR=$PWD/vendor/prefix/include
    cmake --build vendor/llama.cpp/build -j --target llama-bench llama-completion

Find the B65's Vulkan index with `vendor/llama.cpp/build/bin/llama-bench --list-devices` (on this machine: `1`; `0` is the 3080).
Unload LM Studio models first (`lms unload --all`); run.sh refuses to start with < 28 GB free on the B65.

## Run
    B65_VK_INDEX=1 DRY=1 ./run.sh   # one model, pp512 + spot-check
    B65_VK_INDEX=1 ./run.sh         # full run, ~1 h

Each test: llama-bench's built-in warmup, then 5 repeats (mean +/- sd), flash attention on, all layers on GPU.
Tests: prefill 512 / 4096 / 16384 tokens; decode 128 tokens at 0 / 4K / 16K context depth.
Each model also gets a greedy 96-token spot-check generation, to catch fast-but-garbage output.

### Power
B65 board power from the xe hwmon `card` energy counter (not wall power), sampled at 10 Hz during each test.
`board_w_avg` averages over the timed reps only (the trailing `sum(samples_ns)` window before llama-bench exits),
which excludes model load and warmup. It is left blank for `-d` depth tests, because llama-bench runs an untimed
depth prefill inside every rep and the window would mix prefill and decode power. `invocation_w_avg` (whole
process including load) is kept for transparency but is not a headline number.

## Output
- `raw/<run_id>/`: env.txt, llama-bench JSONL + logs, power traces, energy.csv, spot-checks, model sha256s (never edit)
- `results.csv`: one row per model x test (failures recorded with `status`), appended every run
- `charts/<run_id>-pp.png`, `-tg.png`: 16:9 charts with versions in the footer

## Machine notes (logged in env.txt)
- The B65 links at **PCIe 4.0 x4** via the X570 chipset (card supports x16). Arc's on-card switch makes the
  endpoint itself report 2.5 GT/s x1; the real link is read from the upstream bridge.
- ReBAR is on (BAR2 = 32768 MiB).
- With nothing loaded, Vulkan reports ~29.3 GB of 32 GB free on the B65 (driver-reserved; no process holds it).

## Live dashboard (tailnet only)
The dashboard is optional and runs on your own machine or tailnet. Public benchmark evidence is available directly in this repository; no dashboard login or tailnet access is needed to read it.

Example: `https://benchmark-host.example.ts.net:8445/` serves live board power/temps/fan, current test and rep, results
table as tests finish, spot-checks, env. Read-only; it never touches the GPU.

    systemd-run --user --unit=b65-dashboard --working-directory=$PWD .venv/bin/python dashboard/server.py --port 8765
    tailscale serve --bg --https=8445 http://127.0.0.1:8765      # off: tailscale serve --https=8445 off

Start long runs as a user service so they survive the terminal/agent session that launched them:

    systemd-run --user --unit=b65-bench-run --working-directory=$PWD -E B65_VK_INDEX=1 -E PATH=$PATH -E HOME=$HOME \
      bash -c './run.sh > full-run.log 2>&1'
    systemctl --user stop b65-bench-run    # abort

### Share cards
`/share` has one tab per phase (`/share#p0`, `#p05`, `#p1`, `#p2`; the sidebar's Share cards link opens the current phase's tab). Each tab shows that phase's run status, then **Post now** (no measured numbers) and **Results** (unlock when that phase's run finishes). Only the open tab is drawn. A new card joins a tab through its `group`; a new phase needs an entry in `SHARE_PHASES` in `share.html`.

On your dashboard, `/share` serves social-size PNG cards (16:9 for X/LinkedIn, 4:5 for
Instagram/Threads) with Download / Copy image / Share and a suggested caption for each.
- **Teasers** (live progress, proof: the model's own spot-check output, redacted results, lineup, methodology, test rig) never contain measured values. While a run is
  in progress `/api/share` sends only per-test status (`done` / `running` / `pending`; failures are also reported
  as `done`) and a unitless power shape, so the page has nothing to leak. Redaction blocks are all the same width.
- **Results** cards (findings, per-model build card / spec sheet, decode, prefill, tokens per joule, headline) unlock only when
  the latest run has a `done` marker and every planned test has finished.
- **Phase 0.5 cards** (own section): teasers (preview, live sweep grid, poll, exact model versions) and results
  (% change with flash attention off, settings from here on, Gemma before/after) that unlock when the sweep finishes.
  Holds apply to both flash-attention settings; the Gemma card stays locked until its prefill is released.
- **Phase 1 cards** (own section): teasers (preview, live grid, "time to first word" poll) and results (context-fit grid,
  time to first token, key findings) that unlock when the Phase 1 run completes. OOMs report as "done" until then.
- **Holds:** `holds.conf` lists results that stay unpublished even after a run completes (`model|test|reason`). The server
  strips them from `/api/share`, and cards show "held". Delete a line to release it.
- One card at its exact size: `share?solo=1&card=<live|proof|p05|p05-live|p05-bets|p05-prov|p05-findings|p05-delta|p05-decode|p05-settings|p05-gemma|p1-preview|p1-live|p1-guess|p1-context|p1-ttft|p1-findings|redacted|lineup|method|rig|findings|build|decode|prefill|efficiency|headline>&fmt=<wide|tall>[&model=<name>][&handle=@you][&price=<what you paid>]`
- Captions come in variants (post / short take / reply), written short, first person, ending in a question, with a 280-character counter.
  Card price is typed in by hand on the page and only appears once set.

### Phase dashboards
Every page has a left sidebar (`dashboard/nav.js`, statuses from `/api/nav`) linking all phases, share cards, findings and files, with a live status dot per phase. To add a phase, add it to the `PHASES` list in `nav.js` and to `nav_status()` in `server.py`.

- `/p05`: Phase 0.5 flash-attention sweep (off vs on, with Phase 0 reference and provenance).
- `/p1`: Phase 1 (decode by context depth with OOMs, llama-server TTFT, loaded idle power + VRAM, drift check vs Phase 0.5).
- `/p2`: Phase 2, Vulkan (FA off) vs SYCL (FA off/on) per model and test, SYCL build state, decode verdict so far.
- `/p1g`: Phase 1 follow-up, Gemma llama-server rerun (`b65-phase1/gemma_server_rerun.sh` → `raw/p1-swa-*`): `--ctx-checkpoints 0` / `--swa-full` / defaults vs the Phase 1 baseline.

### Files
On your dashboard, `/files/` is a read-only browser/download route for `findings/`, `dist/`, `charts/`, `raw/`, the phase kits,
`results.csv` and this README (nothing else in the project or on the machine). From the Mac you can also use
`scp user@benchmark-host:/path/to/b65-benchmarks/dist/<file> .` over your configured SSH connection.
Findings moved from `dist/*-findings.md` to `findings/phase{0,05,1}.md` on 2026-10-13.
