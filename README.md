# ig-render
GitHub Actions で three.js / Blender の描き出しをコマごとに分けて回し、mp4 にまとめる。

- `jobs/<名前>/index.html`（three.js：`window.setFrame(n)` を用意）または `jobs/<名前>/scene.py`（Blender：場面を作るだけ）を置く
- Actions の `render` を workflow_dispatch で動かす（入力：job / kind / frames / chunks / fps / width / height）
- 結果は artifact（`video` に `out.mp4`）で受け取る。リポジトリには書き戻さない
