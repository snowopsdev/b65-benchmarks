#!/usr/bin/env bash
# Phase 9 part T: SergiioB's TensorFold fork (branch b70-attn-prefix-20261113, XPU_ATTN_PREF) on the B65.
# Same binary, one session: default path vs XPU_ATTN_PREF=256, each on a fresh server shaped like the receipt
# (--parallel 1 --context 139264 --prompt-cache-gib 0 --no-thinking, bf16 K/V, DFlash2 drafts).
# Usage: ./tf_attnpref.sh   SIZES=68,8000,32600,131000  MODES="default pref256"  TF=<tensorfold-native>
set -u
cd "$(dirname "$0")"
TF="${TF:-$HOME/src/ext/TensorFold-sergiiob/zig-out/xpu/bin/tensorfold-native}"; PORT=8081
PY=$HOME/.local/share/unsloth-xpu/bin/python; TOK=$HOME/models/tokenizers/Qwen3.8-27B/tokenizer.json
SIZES="${SIZES:-68,8000,32600,131000}"; MODES="${MODES:-default pref256}"; CTX="${CTX:-139264}"
OUT=raw/p9t-$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"; echo $$ > "$OUT/pid"
# prompt sources: TensorFold's own Zig sources (code) and markdown docs (prose), fixed order so every server sees the same text
SRCDIR="$HOME/src/ext/TensorFold-sergiiob"
find "$SRCDIR/zig/src" -name '*.zig' | LC_ALL=C sort | xargs cat > "$OUT/code.txt"
{ find "$SRCDIR/docs" -name '*.md' | LC_ALL=C sort; find ../findings -name '*.md' | LC_ALL=C sort; } | xargs cat > "$OUT/prose.txt"
{ echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"; echo "tf_commit=$(git -C "$SRCDIR" rev-parse --short HEAD) (+ b65-phase8/xpu-device-id.patch)"
  echo "tf=$TF"; echo "ocloc=$(ocloc --version 2>&1 | head -n1)"; echo "compute_runtime=$(pacman -Q intel-compute-runtime 2>/dev/null)"
  echo "weights=$HOME/models/Qwen3.8-27B-GPTQ-g128 drafter=$HOME/models/Qwen3.8-27B-DFlash2"
  echo "server=--parallel 1 --context $CTX --prompt-cache-gib 0 --no-thinking"; echo "sizes=$SIZES modes=$MODES"
  echo "power1_cap_uw=$(cat /sys/class/hwmon/hwmon*/power1_cap 2>/dev/null | head -n1)"; echo "kit_commit=$(git rev-parse HEAD)"; } > "$OUT/env.txt"; cat "$OUT/env.txt"
for MODE in $MODES; do
  curl -s -o /dev/null http://127.0.0.1:$PORT/ && { echo "!! port $PORT is already in use"; exit 1; }
  SW=(); [ "$MODE" = pref256 ] && SW=(XPU_ATTN_PREF=256)
  echo ">> $MODE: ${SW[*]:-(switch unset)}"
  env -u XPU_ATTN_PREF -u XPU_PREFILL_INT8 -u XPU_KV_INT8 XPU_DEVICE_ID=e222 "${SW[@]}" "$TF" serve "$HOME/models/Qwen3.8-27B-GPTQ-g128" \
    --drafter "$HOME/models/Qwen3.8-27B-DFlash2" --parallel 1 --context "$CTX" --prompt-cache-gib 0 --no-thinking \
    --host 127.0.0.1 --port $PORT --name qwen > "$OUT/$MODE.server.log" 2>&1 &
  pid=$!; echo "$pid" > "$OUT/.spid"
  for _ in $(seq 1 120); do curl -sf http://127.0.0.1:$PORT/v1/models >/dev/null && break; kill -0 $pid 2>/dev/null || { echo "!! $MODE server died"; tail -5 "$OUT/$MODE.server.log"; exit 1; }; sleep 3; done
  "$PY" tf_depth.py http://127.0.0.1:$PORT qwen "$TOK" "$OUT/code.txt" "$OUT/prose.txt" "$OUT/depth.json" "$MODE" --sizes "$SIZES" ${CLIENT_ARGS:-} || echo "!! $MODE client failed"
  kill $pid 2>/dev/null; wait $pid 2>/dev/null; rm -f "$OUT/.spid"; sleep 15   # VRAM lingers after exit (Phase 8)
done
journalctl -k --since '-3h' --no-pager | grep -E 'xe 0000:06.*(Timedout|Engine reset|CAT)' > "$OUT/gpu-resets.txt" || echo "no GPU resets logged" > "$OUT/gpu-resets.txt"
date -Iseconds > "$OUT/done"; echo "OUT=$OUT"
