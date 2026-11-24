import asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8")
URL="https://cokvilbl.89qjb-6ptj9-aswmes.xyz:16677/topic/702058.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome", headless=True)
        for i in range(1,6):
            p=await b.new_page()
            await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
            await p.wait_for_timeout(1200)
            t=await p.locator("body").inner_text()
            lines=[x.strip() for x in t.splitlines() if x.strip()]
            print(f"=== {i} 长度{len(t)} 行{len(lines)} section_name命中{t.count('「平特一肖」独家提供')}")
            for l in lines[3:7]: print("     ", l[:70])
            await p.close()
        await b.close()
asyncio.run(main())
