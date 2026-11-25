#!/bin/bash
# k32 城（クラウド）：番号 S〜E（0から）＝ コマ 501+S 〜 501+E を描く。castle.blend は Release k32-blend から取る。
S=$1; E=$2; OUT=$3; D="$(cd "$(dirname "$0")" && pwd)"
curl -sSL -o "$D/castle.blend" https://github.com/az304845-sudo/ig-render/releases/download/k32-blend/castle.blend
ls -la "$D/castle.blend"
cd "$D" && "$BLENDER" -b castle.blend -noaudio -P castle_anim.py -t 0 -o "$OUT/f_" -F PNG -x 1 -s $((501+S)) -e $((501+E)) -a 2>&1 | grep -E "^Fra:.*Time|Saved|Error|Traceback" | grep -vE "Synchroniz|Updating" | tail -n 400
