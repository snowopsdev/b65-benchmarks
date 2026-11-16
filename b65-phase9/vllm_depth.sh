#!/usr/bin/env bash
# Phase 9 part V: after the chain, restart b65-llm (Intel vLLM A5, sym_int4 + MTP k=5) and run tf_depth.py's prompts against it,
# so TensorFold's XPU_ATTN_PREF numbers have a same-day vLLM reference. 80K context: no 131K cell. Its prefix cache stays on.
cd "$(dirname "$0")"
while systemctl --user is-active --quiet b65-p9-run; do sleep 30; done
T=$(ls -d raw/p9t-2* | grep -v dry | tail -n1); OUT=raw/p9v-$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"
cp "$T/code.txt" "$T/prose.txt" "$OUT/"
systemctl --user start b65-llm
for _ in $(seq 1 240); do curl -sf http://127.0.0.1:8100/v1/models >/dev/null && break; sleep 5; done
{ echo "date=$(date -Iseconds)"; echo "server=b65-llm $(systemctl --user show b65-llm -p ExecStart --value | head -c 300)"; echo "prompts_from=$T"; } > "$OUT/env.txt"
$HOME/.local/share/unsloth-xpu/bin/python tf_depth.py http://127.0.0.1:8100 qwen3.8-27b $HOME/models/tokenizers/Qwen3.8-27B/tokenizer.json \
  "$OUT/code.txt" "$OUT/prose.txt" "$OUT/depth.json" vllm-a5 --sizes 68,8000,32600 --nodraft "" > "$OUT/run.log" 2>&1
echo "V exit $? $OUT" >> chain.log
