import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
URL="https://gboqrz.hmf0d-gnako-vspyqi.work/topic/231872.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome", headless=True, args=["--ignore-certificate-errors"])
        ctx=await b.new_context(ignore_https_errors=True)
        p=await ctx.new_page()
        await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await p.wait_for_timeout(3000)
        t=await p.locator("body").inner_text()
        print("=== 正文 ===")
        for l in [x.strip() for x in t.splitlines() if x.strip()]: print(" ", l[:100])
        await b.close()
asyncio.run(main())
