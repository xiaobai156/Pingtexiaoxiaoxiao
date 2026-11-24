import asyncio, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
SITES = {
 "气冲牛斗": "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741286.html",
 "大公无私": "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741288.html",
 "澳门资料库": "https://bb.48kk47.com:1888/",
}
async def main():
    from playwright.async_api import async_playwright
    out = Path(__file__).resolve().parent / "bodies"; out.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        for name, url in SITES.items():
            p = await b.new_page()
            try:
                await p.goto(url, wait_until="domcontentloaded", timeout=30000)
                await p.wait_for_timeout(1500)
                t = await p.locator("body").inner_text()
            except Exception as exc:
                print("ERR", name, type(exc).__name__, exc); await p.close(); continue
            (out / f"{name}.txt").write_text(t, encoding="utf-8")
            lines = [x.strip() for x in t.splitlines() if x.strip()]
            print(f"=== {name} 长度{len(t)} 行{len(lines)} 326命中{t.count('326')} 325命中{t.count('325')}")
            for l in lines[:14]: print("   ", l[:86])
            await p.close()
        await b.close()
asyncio.run(main())
