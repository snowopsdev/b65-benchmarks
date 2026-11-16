#!/usr/bin/env bash
# Phase 9 share cards -> charts/phase9/*.png at 2x (1200x675 wide, 1080x1350 tall), straight from b65-phase9/cards.html.
set -euo pipefail
cd "$(dirname "$0")/.."; OUT=charts/phase9; mkdir -p "$OUT"; SRC="file://$PWD/b65-phase9/cards.html"
for c in llama llama-plain tf tf-plain; do for f in wide tall; do
  case $f in wide) wh=1200,675 ;; tall) wh=1080,1350 ;; esac
  chromium --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --window-size=$wh --virtual-time-budget=4000 \
    --screenshot="$OUT/b65-p9-$c-$f.png" "$SRC?card=$c&fmt=$f" >/dev/null 2>&1
  echo "$OUT/b65-p9-$c-$f.png"; done; done
