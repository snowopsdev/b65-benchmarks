#!/usr/bin/env bash
# Phase 7 share cards -> charts/phase7/*.png at 2x, through the share page's solo mode (needs the dashboard on :8765
# and b65-phase7/FINAL, which unlocks the numbers). Usage: ./export_cards.sh [card ...]
set -euo pipefail
cd "$(dirname "$0")/.."; OUT=charts/phase7; mkdir -p "$OUT"
CARDS=("${@:-p7-verdict p7-single p7-strata p7-serve p7-ttft p7-recipe p7-traps p7-proscons p7-audit}"); CARDS=(${CARDS[@]})
for c in "${CARDS[@]}"; do
  if [ "$c" = p7-audit ]; then fmts="4x5"; else fmts="wide tall"; fi
  for f in $fmts; do
    case $f in wide) wh=1200,675 ;; tall) wh=1080,1350 ;; 4x5) wh=1200,1500 ;; esac
    q=$([ $f = 4x5 ] && echo wide || echo $f)
    chromium --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --window-size=$wh --virtual-time-budget=8000 \
      --screenshot="$OUT/b65-${c}-${f}.png" "http://127.0.0.1:8765/share?solo=1&card=$c&fmt=$q" >/dev/null 2>&1
    echo "$OUT/b65-${c}-${f}.png"
  done
done
