import asyncio, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
SITES = {
 "比比皆是": "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741245.html",
 "襟怀坦白": "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741250.html",
 "一身正气": "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741281.html",
}
async def main():
    from playwright.async_api import async_playwright
    out = Path(__file__).resolve().parent / "bodies"
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        for name, url in SITES.items():
            p = await b.new_page()
            await p.goto(url, wait_until="domcontentloaded", timeout=30000)
            await p.wait_for_timeout(1200)
            t = await p.locator("body").inner_text()
            (out / f"{name}.txt").write_text(t, encoding="utf-8")
            lines=[x.strip() for x in t.splitlines() if x.strip()]
            print("=====", name)
            for i,l in enumerate(lines):
                if "326期平特" in l or ("326" in l and "平特" in l) or "平特贴 326" in l:
                    print(f"{i+1:4d}: {l[:110]}")
            await p.close()
        await b.close()
asyncio.run(main())
