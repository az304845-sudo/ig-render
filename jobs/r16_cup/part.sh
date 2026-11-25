#!/bin/bash
# R16 コップ（クラウド）：frames.txt の S〜E 行目のコマ（偶数）を描く。--samples 32 --res 100（手元の本番と同じ）
S=$1; E=$2; OUT=$3; D="$(cd "$(dirname "$0")" && pwd)"
for f in $(sed -n "$((S+1)),$((E+1))p" "$D/frames.txt"); do
  "$BLENDER" -b -noaudio -P "$D/blender/cup.py" -- --anim --fs $f --fe $f --step 2 --samples 32 --res 100 --outdir "$OUT" 2>&1 | grep -E "^FRAME|Error|Traceback"
done
