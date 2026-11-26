import asyncio,sys,re
sys.stdout.reconfigure(encoding="utf-8")
URL="https://gboqrz.hmf0d-gnako-vspyqi.work/topic/454146.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        for n in range(1,5):
            p=await b.new_page()
            try:
                await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
                await p.wait_for_timeout(800)
                t=await p.locator("body").inner_text()
            except Exception as e:
                print(n,"ERR",e); await p.close(); continue
            await p.close()
            hits=[l.strip() for l in t.splitlines() if "成语平特" in l and "期:" in l]
            top=[h for h in hits if h.startswith("329")]
            print(n,"len",len(t),"行数",len(hits),"最新",hits[0][:50] if hits else "-","329行",top)
        await b.close()
asyncio.run(main())
