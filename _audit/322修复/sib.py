import asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8")
HOST="https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/"
PAGES=["741250.html","741254.html","741257.html","741276.html","741267.html","741249.html","741274.html","741281.html"]
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        for pg in PAGES:
            p=await b.new_page()
            try:
                await p.goto(HOST+pg, wait_until="domcontentloaded", timeout=25000)
                await p.wait_for_timeout(600)
                t=await p.locator("body").inner_text()
            except Exception as e:
                print(pg,"ERR",e); await p.close(); continue
            await p.close()
            hits=[x.strip() for x in t.splitlines() if "326" in x and "平特" in x and ("尾" in x or "肖" in x)]
            print(pg, "|", " || ".join(hits[:4]))
        await b.close()
asyncio.run(main())
