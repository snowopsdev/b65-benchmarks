#!/usr/bin/env bash
# Phase 9 full run, one GPU job at a time: L (llama-bench A/B), T (TensorFold fork XPU_ATTN_PREF), S (llama-server A/B + MTP).
cd "$(dirname "$0")"
./bench.sh > p9l-run.log 2>&1; echo "L exit $?" >> chain.log
while systemctl --user is-active --quiet b65-p9-tfbuild; do sleep 20; done
if [ -x "$HOME/src/ext/TensorFold-sergiiob/zig-out/xpu/bin/tensorfold-native" ]; then ./tf_attnpref.sh > p9t-run.log 2>&1; echo "T exit $?" >> chain.log
else echo "T skipped: no tensorfold-native" >> chain.log; fi
./serve.sh > /dev/null 2>&1; echo "S exit $?" >> chain.log
echo "chain done $(date -Iseconds)" >> chain.log
