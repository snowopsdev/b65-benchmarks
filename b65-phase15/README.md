# Phase 1.5: registry recipes for the Arc Pro B65

Goal: get the B65 into [local-ai-registry](https://github.com/sybil-solutions/local-ai-registry) with one recipe per model that passes the registry's six lab gates (load, chat, reasoning, tools, context at 85% of the window, decode ≥ 15 tok/s).

Unblocked 2026-10-14: the registry merged a llama.cpp SYCL recipe for the Arc B390 on 2026-10-10 (`a8e64af`), so llama.cpp recipes are accepted. The recipe kit's own first target (Qwen3.8-Flash-Next offload) needs 68 GB free RAM and doesn't fit this 48 GB machine.

## Pieces
| file | what |
|---|---|
| `precheck.sh` + `gates.py` | the registry's `gates()` (imported unmodified from the clone) against our native SYCL `llama-server` on the recommended settings, 32K, thinking on. A first pass, not a registry proof. |
| `make_launches.py` | writes the B65 launches into the registry clone: official `server-intel-b11515` image (the B390 recipe's digest), our flags (`-fa on -b 2048 -ub 2048`, all layers, 32K), weights pinned to the Hugging Face commits that match our files byte for byte |
| `setup-docker.sh` | one-time, needs sudo (AJ): starts Docker and adds the user to the `docker` group |
| `registry_run.sh` | per model: checks the local GGUF against the pinned commit, starts the pinned image like the registry SDK does (`--device /dev/dri`, published on 127.0.0.1 only), runs `lab.py try --on endpoint`, stops it |

Registry clone: `~/src/ext/local-ai-registry-20261014`, branch `b65-arc-pro-recipes` (card `intel-arc-pro-b65-32gb`, three launches). Nothing is pushed; a PR is AJ's call.

## Pinned weights (lmstudio-community, matched by sha256 on 2026-10-14)
- Qwen3.8-27B-GGUF `5a7da681f60570ab5b439a587e912d2e5eddb582` (Q4_K_M)
- gemma-4-31B-it-QAT-GGUF `12e5eae7a583b0a8bac91919fa99ae1fb27e6de4` (Q4_0)
- Muse-Glimmer-30B-GGUF `c34cb7372a72fd3bec29e3a21e6c8e04e337d5ae` (Q4_K_M)

## Run
```bash
./setup-docker.sh                                    # AJ, once
docker pull ghcr.io/ggml-org/llama.cpp@sha256:86b37d266ce85b485127adea68c9dc6d04d0ec9a64b0979844d5bbd8d66c53c5
systemd-run --user --unit=b65-p15-registry --working-directory=$PWD -E REG=$HOME/src/ext/local-ai-registry-20261014 \
  -E HOME=$HOME -E PATH=$PATH bash -c "./registry_run.sh > registry_run.log 2>&1"
```

## Notes
- The image is llama.cpp b11515; our native build is b11574. Registry numbers come from the image, so they can differ slightly from the findings.
- The reasoning gate needs thinking to come back separately, so thinking stays on here (unlike the coding recipe for Qwen).
- The speed gate measures decode over the first 30 s of an uncapped answer at concurrency 1, on an empty context.
