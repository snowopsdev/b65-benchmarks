#!/usr/bin/env bash
# B65 Bench Phase 0.5: flash-attention on/off sweep (Vulkan, llama-bench) + HF provenance.
# Usage: B65_VK_INDEX=<idx> ./phase05.sh        (DRY=1 for a 1-test sanity check)
# Env: LLAMA_BENCH, REPS (default 5), SKIP_SLOW=1 skips gemma fa=1 pp16384 (already measured: 37.98 tok/s, 43 min)
set -euo pipefail
cd "$(dirname "$0")"
LB="${LLAMA_BENCH:-../vendor/llama.cpp/build/bin/llama-bench}"
command -v "$LB" >/dev/null || { echo "llama-bench not found; set LLAMA_BENCH"; exit 1; }
[ -n "${B65_VK_INDEX:-}" ] || { echo "Set B65_VK_INDEX"; "$LB" --list-devices 2>&1 || true; exit 1; }
export GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX"
REPS="${REPS:-5}"; SKIP_SLOW="${SKIP_SLOW:-1}"
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }   # local: no bc on this machine
# local: only the B65 visible, and its VRAM free (LM Studio models unloaded)
DEVS=$("$LB" --list-devices 2>&1)
echo "$DEVS" | grep -q "BMG" && ! echo "$DEVS" | grep -q "NVIDIA" || { echo "!! Visible devices are not just the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1)
[ "${FREE:-0}" -ge 28000 ] || { echo "!! Only ${FREE:-?} MiB free on the B65. Unload LM Studio models (lms unload --all)."; exit 2; }
# local: RUN_PREFIX keeps follow-up runs apart
RUN_ID="${RUN_PREFIX:-p05}-$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"

{ echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"; echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null)"
  echo "omarchy=$(omarchy-version 2>/dev/null || cat ~/.local/share/omarchy/version 2>/dev/null || git -C ~/.local/share/omarchy describe --tags 2>/dev/null || echo unknown)"
  echo "llama_bench=$("$LB" --version 2>&1 | head -n 3 | tr '\n' ' ')"
  echo "vk_visible=$GGML_VK_VISIBLE_DEVICES"; echo "reps=$REPS"; echo "vram_free_mib=$FREE"; } > "$OUT/env.txt"

ENERGY=""
for h in /sys/class/hwmon/hwmon*; do   # local: pick the xe "card" channel by label, not just the first counter
  [ "$(cat "$h/name" 2>/dev/null)" = "xe" ] || continue
  for l in "$h"/energy*_label; do [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }; done
done
echo "energy_file=${ENERGY:-none}" >> "$OUT/env.txt"
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
# local: 10 Hz energy trace + time-stamped --progress lines, so board W covers the timed reps only (same as Phase 0)
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }
stamp() { while IFS= read -r l; do echo "$EPOCHREALTIME $l"; done; }

TESTS=( "pp512|-p 512 -n 0" "pp4096|-p 4096 -n 0" "pp16384|-p 16384 -n 0" "tg128@d16384|-p 0 -n 128 -d 16384" )
[ "${DRY:-0}" = 1 ] && TESTS=( "pp512|-p 512 -n 0" )
# local: TESTS_SPEC="label|args;label|args" and FA_LIST="0 1" override the test list and settings for follow-ups
[ -n "${TESTS_SPEC:-}" ] && IFS=';' read -r -a TESTS <<< "$TESTS_SPEC"
FA_LIST="${FA_LIST:-0 1}"

echo "test,model,fa,file,status,energy_j,seconds,t_end" > "$OUT/energy.csv"
echo "$$" > "$OUT/pid"
while IFS='|' read -r NAME QUANT GLOB; do
  [[ -z "$NAME" || "$NAME" == \#* ]] && continue
  FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$FILE" ] || { echo "!! no file for $NAME"; continue; }
  sha256sum "$FILE" >> "$OUT/models.sha256"
  for FA in $FA_LIST; do
    for T in "${TESTS[@]}"; do
      LABEL="${T%%|*}"; ARGS="${T#*|}"
      if [ "$SKIP_SLOW" = 1 ] && [ "$FA" = 1 ] && [ "$LABEL" = pp16384 ] && [[ "$NAME" == gemma* ]]; then
        echo "$LABEL,$NAME,$FA,$(basename "$FILE"),skipped,,," >> "$OUT/energy.csv"; continue; fi
      echo ">> $NAME fa=$FA $LABEL"
      TP=""; [ -n "$ENERGY" ] && { trace "$OUT/$NAME.fa$FA.$LABEL.power.csv" & TP=$!; }
      e0=$(read_e); t0=$EPOCHREALTIME; st=ok
      # shellcheck disable=SC2086
      "$LB" -m "$FILE" -ngl 99 -fa "$FA" -r "$REPS" $ARGS -o jsonl --progress \
        > "$OUT/$NAME.fa$FA.$LABEL.jsonl" 2> >(stamp > "$OUT/$NAME.fa$FA.$LABEL.log") || st=fail
      e1=$(read_e); t1=$EPOCHREALTIME
      [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }
      wait   # trace is gone; this lets the stderr stamper flush
      EJ=""; [ -n "$e0" ] && EJ=$(calc "($e1-$e0)/1000000")
      echo "$LABEL,$NAME,$FA,$(basename "$FILE"),$st,$EJ,$(calc "$t1-$t0"),$t1" >> "$OUT/energy.csv"
      [ $st = fail ] && echo "!! $NAME fa=$FA $LABEL failed, see $OUT/$NAME.fa$FA.$LABEL.log"
      # local: device check on every successful test, not just the first
      if [ $st = ok ] && ! grep -q '"gpu_info": *"[^"]*BMG' "$OUT/$NAME.fa$FA.$LABEL.jsonl"; then
        echo "!! not the B65, aborting"; exit 2; fi
    done
  done
  [ "${DRY:-0}" = 1 ] && break
done < models.conf

python3 provenance.py "$OUT" || echo "!! provenance lookup failed (offline?), fill hf_commit by hand"
python3 summarize05.py "$OUT"
date -Iseconds > "$OUT/done"
echo "Done: $OUT"
