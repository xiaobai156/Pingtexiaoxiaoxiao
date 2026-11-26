import asyncio,sys,re
sys.stdout.reconfigure(encoding="utf-8")
URL="https://rh2fgz.cxg5b-ueme6-sfoybf.work/topic/536229.html"
STYLE="*{content-visibility:visible!important}"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        for n in range(1,4):
            p=await b.new_page()
            try:
                await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(n,"ERR",e); await p.close(); continue
            await p.add_style_tag(content=STYLE)
            for _ in range(6):
                await p.mouse.wheel(0,4000); await p.wait_for_timeout(200)
            t=await p.locator("body").inner_text()
            await p.close()
            rows=[l.strip() for l in t.splitlines() if re.match(r"^\d{3}期四字平特", l.strip())]
            print(n,"len",len(t),"结果行",len(rows),"最新",rows[0][:36] if rows else "-","330行",[r for r in rows if r.startswith("330")])
        await b.close()
asyncio.run(main())
