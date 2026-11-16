#!/usr/bin/env bash
# Phase 9 part R: a same-day rerun of Phase 7's Intel vLLM A5 (sym_int4 + MTP k=5, graphs; full suite: speed, conc, coding)
# through Phase 7's own harness, then llama.cpp v1.0.0 + MTP k=5 on the coding suite again as a same-session control.
# Stops b65-llm (the B65 must be free) and starts it again at the end, whatever happens.
# Run: systemd-run --user --unit b65-p9-vllm ./vllm_rerun.sh   (user units carry the docker group)
set -u
cd "$(dirname "$0")"
LOG="$PWD/p9r-run.log"; exec > >(tee -a "$LOG") 2>&1
restore() { echo ">> restarting b65-llm"; systemctl --user start b65-llm
  for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8100/health >/dev/null && { echo ">> b65-llm up"; return; }; sleep 5; done
  echo "!! b65-llm did not come back"; }
trap restore EXIT
echo ">> $(date -Iseconds) stopping b65-llm"; systemctl --user stop b65-llm; sleep 10
( cd ../b65-phase7 && SYCL_BIN=$HOME/src/llama.cpp-1.0.0/build-sycl/bin PARTS=A5 ./phase7.sh ) || echo "!! phase7 A5 exited $?"
echo ">> A5 run: $(ls -d ../b65-phase7/raw/p7-2* | tail -n1)"
sleep 15   # VRAM lingers after the container exits
PARTS=NA0mk5 ./serve.sh || echo "!! serve.sh NA0mk5 exited $?"
echo ">> $(date -Iseconds) done"
