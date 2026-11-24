import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
URL="https://cokvilbl.89qjb-6ptj9-aswmes.xyz:16677/topic/702058.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome", headless=True)
        for i in range(1,4):
            p=await b.new_page()
            await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
            await p.wait_for_timeout(1500)
            t=await p.locator("body").inner_text()
            lines=[x.strip() for x in t.splitlines() if x.strip()]
            print(f"=== 第{i}次 长度{len(t)} 行{len(lines)} 含凉风有信={t.count('凉风有信')}")
            for l in lines[3:8]: print("   ", l[:80])
            await p.close()
        await b.close()
asyncio.run(main())
