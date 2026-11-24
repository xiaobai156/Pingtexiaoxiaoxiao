import asyncio, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
URL = "https://cokvilbl.89qjb-6ptj9-aswmes.xyz:16677/topic/702063.html"
async def main():
    from playwright.async_api import async_playwright
    out = Path(__file__).resolve().parent / "bodies"
    out.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        for i in range(1, 4):
            p = await b.new_page()
            await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
            await p.wait_for_timeout(1200)
            t = await p.locator("body").inner_text()
            (out / f"一個好人-{i}.txt").write_text(t, encoding="utf-8")
            lines = [x.strip() for x in t.splitlines() if x.strip()]
            print(f"=== {i} 长度{len(t)} 行{len(lines)} 一個好人命中{t.count('一個好人')}")
            for l in lines[:10]:
                print("   ", l[:80])
            await p.close()
        await b.close()
asyncio.run(main())
