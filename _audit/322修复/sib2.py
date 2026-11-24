import asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8")
HOST="https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/"
PAGES=["741258.html","741250.html","741276.html","741252.html","741274.html","741281.html","741263.html","741261.html"]
PAT=re.compile(r"326\s*期.*?平特")
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        for pg in PAGES:
            p=await b.new_page()
            try:
                await p.goto(HOST+pg, wait_until="domcontentloaded", timeout=25000)
                await p.wait_for_timeout(500)
                t=await p.locator("body").inner_text()
            except Exception as e:
                print(pg,"ERR",e); await p.close(); continue
            await p.close()
            cand=[x.strip() for x in t.splitlines() if PAT.search(x) and not x.strip().startswith("平特贴")]
            print(pg,"|", " || ".join(cand[:3]))
        await b.close()
asyncio.run(main())
