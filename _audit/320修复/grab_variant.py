import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
URL="https://cokvilbl.89qjb-6ptj9-aswmes.xyz:16677/topic/702058.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome", headless=True)
        for i in range(8):
            p=await b.new_page(); await p.goto(URL, wait_until="domcontentloaded", timeout=30000); await p.wait_for_timeout(1000)
            t=await p.locator("body").inner_text(); await p.close()
            if t.count("「平特一肖」独家提供")==2:
                open("_audit/320修复/bodies/凉风有信-variant2.txt","w",encoding="utf-8").write(t)
                lines=[x.strip() for x in t.splitlines()]
                print("抓到双命中变体，行数", len(lines))
                for i,l in enumerate(lines):
                    if "「平特一肖」独家提供" in l or "平特一肖" in l: print(f"{i+1:4d}: {l[:90]}")
                break
        await b.close()
asyncio.run(main())
