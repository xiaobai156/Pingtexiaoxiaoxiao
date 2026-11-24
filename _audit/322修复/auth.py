import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
HOST="https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        for pg in ["741286.html","741287.html","741285.html"]:
            p=await b.new_page()
            await p.goto(HOST+pg, wait_until="domcontentloaded", timeout=25000)
            await p.wait_for_timeout(500)
            t=await p.locator("body").inner_text()
            await p.close()
            lines=[x.strip() for x in t.splitlines() if x.strip()]
            print("=====",pg)
            for x in lines[:60]:
                if "发表于" in x or "期" in x and ("平特" in x or "尾" in x):
                    print("   ",x[:80])
        await b.close()
asyncio.run(main())
