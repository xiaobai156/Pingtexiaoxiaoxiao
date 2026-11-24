import asyncio, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
SITES = {
 "气冲牛斗": "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741286.html",
 "大公无私": "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741288.html",
}
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        for name, url in SITES.items():
            seen = collections.Counter()
            print("=====", name)
            for i in range(8):
                p = await b.new_page()
                await p.goto(url, wait_until="domcontentloaded", timeout=30000)
                await p.wait_for_timeout(900)
                t = await p.locator("body").inner_text()
                await p.close()
                hits = [x.strip() for x in t.splitlines() if "326期平特" in x or ("326" in x and "平特" in x)]
                key = tuple(hits)
                seen[key] += 1
                print(f"  {i+1} len={len(t)} {hits}")
            print("  统计:", dict(seen))
        await b.close()
asyncio.run(main())
