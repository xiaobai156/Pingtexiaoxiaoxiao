import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        p=await b.new_page()
        await p.goto("https://bb.48kk47.com:1888/", wait_until="domcontentloaded", timeout=40000)
        await p.wait_for_timeout(1500)
        html=await p.content()
        i=html.find("洋洋得意")
        print("len",len(html),"idx",i)
        print(html[max(0,i-900):i+400])
        await b.close()
asyncio.run(main())
