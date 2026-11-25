"""three.js のページを1コマずつ PNG に撮る（GitHub Actions 用）。

約束（ページ側）：
- jobs/<名前>/index.html を ?render=1 で開く。
- window.setFrame(n) を用意する。n コマ目の状態にして描き終えたら返す（Promise でもよい）。
- 時計（Date.now / performance.now / requestAnimationFrame の経過時間）で動かさず、n だけで画が決まるようにする。
使い方：python render_threejs.py <jobフォルダ> <start> <end> <出力> <幅> <高さ> <fps>
"""
import asyncio, pathlib, sys
from playwright.async_api import async_playwright


async def main():
    job, start, end, out, w, h, fps = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    url = pathlib.Path(job, "index.html").resolve().as_uri() + f"?render=1&fps={fps}"
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.on("console", lambda m: print("console:", m.text))
        pg.on("pageerror", lambda e: print("pageerror:", e))
        await pg.goto(url, wait_until="load")
        await pg.wait_for_function("typeof window.setFrame === 'function'", timeout=120000)
        for n in range(start, end + 1):
            await pg.evaluate("n => window.setFrame(n)", n)
            await pg.screenshot(path=str(out / f"{n:05d}.png"), full_page=False)
            if n % 10 == 0:
                print("frame", n, flush=True)
        await b.close()


asyncio.run(main())
