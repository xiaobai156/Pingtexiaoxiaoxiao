import asyncio,sys,re
sys.stdout.reconfigure(encoding="utf-8")
URL="https://rh2fgz.cxg5b-ueme6-sfoybf.work/topic/536229.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        p=await b.new_page()
        await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await p.wait_for_timeout(1500)
        h=await p.content()
        await p.close(); await b.close()
    open('_audit/326修复/raw330.html','w',encoding='utf-8').write(h)
    print("html len",len(h))
    print("330期四字 count",h.count("330期四字"))
    print("四字平特 count",h.count("四字平特"))
    for m in re.finditer(r"330期[^<>]{0,40}",h):
        s=m.group(0)
        if "平特" in s or "四字" in s: print("HIT",s[:60])
    # 期号列表
    print("329期四字 count",h.count("329期四字"))
asyncio.run(main())
