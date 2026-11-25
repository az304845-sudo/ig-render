#!/bin/bash
# R16 地球（クラウド）：frames.txt の S〜E 行目（0から）を描く。行は「コマ番号:step」か「still」。続いているコマは1回の Blender でまとめて描く。
S=$1; E=$2; OUT=$3; D="$(cd "$(dirname "$0")" && pwd)"
python3 - "$D/frames.txt" "$S" "$E" <<'PY' > "$D/runs.txt"
import sys
L=[l.strip() for l in open(sys.argv[1]) if l.strip()][int(sys.argv[2]):int(sys.argv[3])+1]
runs=[]
for l in L:
    if l=='still': runs.append('still'); continue
    f,st=map(int,l.split(':'))
    if runs and runs[-1]!='still' and runs[-1][2]==st and runs[-1][1]+st==f: runs[-1][1]=f
    else: runs.append([f,f,st])
for r in runs: print(r if r=='still' else f'{r[0]} {r[1]} {r[2]}')
PY
cat "$D/runs.txt"
while read a b st; do
  if [ "$a" = still ]; then
    "$BLENDER" -b -noaudio -P "$D/blender/earth.py" -- --t 19.3 --sea 0 --samples 16 --res 200 --out "$OUT/still_2x.png" 2>&1 | grep -E "^WROTE|Error|Traceback"
  else
    "$BLENDER" -b -noaudio -P "$D/blender/earth.py" -- --anim --fs $a --fe $b --step $st --samples 16 --res 100 --outdir "$OUT" 2>&1 | grep -E "^FRAME|Error|Traceback|Time:"
  fi
done < "$D/runs.txt"
