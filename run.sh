#!/usr/bin/env bash
# B65 Bench Phase 0: llama-bench (Vulkan) on the Arc Pro B65 only.
# Usage: ./run.sh          full run
#        DRY=1 ./run.sh    one model, pp512 only (~10 min sanity check)
# Env: LLAMA_BENCH=path/to/llama-bench   B65_VK_INDEX=<vulkan device index of the B65>
set -euo pipefail
cd "$(dirname "$0")"
LB="${LLAMA_BENCH:-vendor/llama.cpp/build/bin/llama-bench}"
LC="$(dirname "$LB")/llama-completion"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
command -v "$LB" >/dev/null || { echo "llama-bench not found; set LLAMA_BENCH"; exit 1; }
[ -n "${B65_VK_INDEX:-}" ] || { echo "Set B65_VK_INDEX. Devices:"; "$LB" --list-devices 2>&1 || vulkaninfo --summary 2>/dev/null | grep -E "GPU[0-9]|deviceName"; exit 1; }
export GGML_VK_VISIBLE_DEVICES="$B65_VK_INDEX"
REPS="${REPS:-5}"
calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }

# --- precheck: only the B65 visible, and its VRAM free (LM Studio models unloaded) ---
DEVS=$("$LB" --list-devices 2>&1)
echo "$DEVS" | grep -q "BMG" && ! echo "$DEVS" | grep -q "NVIDIA" || { echo "!! Visible devices are not just the B65:"; echo "$DEVS"; exit 2; }
FREE=$(echo "$DEVS" | grep -oP 'MiB, \K[0-9]+(?= MiB free)' | head -n1)
[ "${FREE:-0}" -ge 28000 ] || { echo "!! Only ${FREE:-?} MiB free on the B65. Unload LM Studio models (lms unload --all)."; exit 2; }

RUN_ID="$(date +%Y%m%d-%H%M%S)"; OUT="raw/$RUN_ID"; mkdir -p "$OUT"

# --- environment snapshot ---
BDF=$(lspci -nn | grep -i 'e222' | awk '{print $1}' | head -n1)
PDEV=$(readlink -f "/sys/bus/pci/devices/0000:$BDF")
{
  echo "run_id=$RUN_ID"; echo "date=$(date -Iseconds)"
  echo "kernel=$(uname -r)"
  echo "mesa=$(pacman -Q mesa 2>/dev/null)"; echo "vulkan_intel=$(pacman -Q vulkan-intel 2>/dev/null)"
  echo "omarchy=$(omarchy-version 2>/dev/null || echo unknown)"
  echo "llama_bench=$("$LB" --version 2>&1 | grep -E '^(version|built)' | tr '\n' ' ')"
  echo "vk_device=$(echo "$DEVS" | grep -m1 'ggml_vulkan: 0 =' | sed 's/^ggml_vulkan: 0 = //')"
  echo "vram_free_mib=$FREE"
  echo "lmstudio_runtime=$(lms runtime ls 2>/dev/null | tr -s ' \n' ' ')"
  echo "gpu_pci=$(lspci -nn -s "$BDF")"
  # Arc cards sit behind an on-board PCIe switch: the endpoint reports 2.5GT/s x1, the real link is upstream
  echo "pcie_endpoint=$(cat "$PDEV/current_link_speed") x$(cat "$PDEV/current_link_width")"
  UP=$(dirname "$(dirname "$PDEV")")
  echo "pcie_link=$(cat "$UP/current_link_speed") x$(cat "$UP/current_link_width") (max $(cat "$UP/max_link_speed") x$(cat "$UP/max_link_width"), at $(basename "$UP"))"
  echo "rebar_bar2_mib=$(awk 'NR==3 { printf "%d", (strtonum($2) - strtonum($1) + 1) / 1048576 }' "$PDEV/resource")"
  echo "cpu=$(lscpu | sed -n 's/^Model name: *//p')"
  echo "ram_gib=$(free -g | awk '/^Mem:/ {print $2}')"
  echo "cpu_governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
  echo "vk_visible=$GGML_VK_VISIBLE_DEVICES"
  echo "bench_args=-ngl 99 -fa on -r $REPS"
} > "$OUT/env.txt"

# --- B65 energy counter (xe hwmon "card" channel, microjoules) ---
ENERGY=""; HW=""
for h in /sys/class/hwmon/hwmon*; do
  [ "$(cat "$h/name" 2>/dev/null)" = "xe" ] || continue
  HW="$h"
  for l in "$h"/energy*_label; do
    [ "$(cat "$l")" = "card" ] && { ENERGY="${l%_label}_input"; break 2; }
  done
done
echo "energy_file=${ENERGY:-none}" >> "$OUT/env.txt"
[ -n "$HW" ] && echo "power1_cap_uw=$(cat "$HW/power1_cap" 2>/dev/null)" >> "$OUT/env.txt"
read_e() { [ -n "$ENERGY" ] && cat "$ENERGY" || echo ""; }
# 10 Hz energy trace -> file (epoch seconds, microjoules); report.py averages over the timed reps only
trace() { while :; do echo "$EPOCHREALTIME,$(<"$ENERGY")"; sleep 0.1; done > "$1"; }

# idle board power (model unloaded), 30 s
if [ -n "$ENERGY" ]; then
  e0=$(read_e); t0=$EPOCHREALTIME; sleep 30; e1=$(read_e); t1=$EPOCHREALTIME
  echo "idle_unloaded_w=$(calc "($e1-$e0)/1000000/($t1-$t0)")" >> "$OUT/env.txt"
fi

# --- tests: label|llama-bench args ---
TESTS=( "pp512|-p 512 -n 0" "pp4096|-p 4096 -n 0" "pp16384|-p 16384 -n 0"
        "tg128|-p 0 -n 128" "tg128@d4096|-p 0 -n 128 -d 4096" "tg128@d16384|-p 0 -n 128 -d 16384" )
[ "${DRY:-0}" = 1 ] && TESTS=( "pp512|-p 512 -n 0" )

echo "test,model,quant,file,status,exit_code,energy_j,seconds,t_end" > "$OUT/energy.csv"
# run bookkeeping for the dashboard: pid, planned tests, current test, done marker
echo "$$" > "$OUT/pid"
while IFS='|' read -r NAME _ _; do
  [[ -z "$NAME" || "$NAME" == \#* ]] && continue
  for T in "${TESTS[@]}"; do echo "$NAME|${T%%|*}"; done; echo "$NAME|spotcheck"
  [ "${DRY:-0}" = 1 ] && break
done < models.conf > "$OUT/plan.txt"
# prefix each stderr line with the epoch time, so report.py can cut exact per-rep power windows
stamp() { while IFS= read -r l; do echo "$EPOCHREALTIME $l"; done; }
while IFS='|' read -r NAME QUANT GLOB; do
  [[ -z "$NAME" || "$NAME" == \#* ]] && continue
  FILE=$(find ~/.lmstudio ~/.cache/lm-studio -iname "$GLOB" 2>/dev/null | grep -v mmproj | head -n1 || true)
  [ -n "$FILE" ] || { echo "!! no file for $NAME ($GLOB), skipping"; continue; }
  sha256sum "$FILE" >> "$OUT/models.sha256"
  for T in "${TESTS[@]}"; do
    LABEL="${T%%|*}"; ARGS="${T#*|}"
    echo ">> $NAME $LABEL"; echo "$NAME|$LABEL|$EPOCHREALTIME" > "$OUT/current"
    TP=""; [ -n "$ENERGY" ] && { trace "$OUT/$NAME.$LABEL.power.csv" & TP=$!; }
    e0=$(read_e); t0=$EPOCHREALTIME
    rc=0
    # shellcheck disable=SC2086
    "$LB" -m "$FILE" -ngl 99 -fa on -r "$REPS" $ARGS -o jsonl --progress \
      > "$OUT/$NAME.$LABEL.jsonl" 2> >(stamp > "$OUT/$NAME.$LABEL.log") || rc=$?
    e1=$(read_e); t1=$EPOCHREALTIME
    [ -n "$TP" ] && { kill "$TP"; wait "$TP" 2>/dev/null || true; }
    wait   # trace is gone; this lets the stderr stamper flush
    EJ=""; [ -n "$e0" ] && EJ=$(calc "($e1-$e0)/1000000")
    STATUS=ok; [ $rc -ne 0 ] && { STATUS=failed; echo "!! $NAME $LABEL failed (exit $rc), see $OUT/$NAME.$LABEL.log"; }
    echo "$LABEL,$NAME,$QUANT,$(basename "$FILE"),$STATUS,$rc,$EJ,$(calc "$t1-$t0"),$t1" >> "$OUT/energy.csv"
    # device check on every successful test: abort if it didn't run on the B65
    if [ $rc -eq 0 ] && ! grep -q '"gpu_info": *"[^"]*BMG' "$OUT/$NAME.$LABEL.jsonl"; then
      echo "!! gpu_info is not the B65. Check B65_VK_INDEX. Aborting."; exit 2
    fi
  done
  # spot-check: greedy generation, to catch fast-but-garbage output
  echo ">> $NAME spot-check"; echo "$NAME|spotcheck|$EPOCHREALTIME" > "$OUT/current"
  "$LC" -m "$FILE" -ngl 99 -fa on -c 2048 -n 96 --temp 0 --seed 1 -no-cnv \
    -p "Explain in three sentences why GPU memory bandwidth matters for LLM token generation." \
    > "$OUT/$NAME.spotcheck.txt" 2> "$OUT/$NAME.spotcheck.log" < /dev/null || echo "!! $NAME spot-check failed"
  [ "${DRY:-0}" = 1 ] && break
done < models.conf

rm -f "$OUT/current"
"$PY" report.py "$OUT"
date -Iseconds > "$OUT/done"
echo "Done: $OUT"
