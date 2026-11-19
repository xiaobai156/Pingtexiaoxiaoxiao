import asyncio, sys, json, re
sys.stdout.reconfigure(encoding="utf-8")
URL="https://gboqrz.hmf0d-gnako-vspyqi.work/topic/231872.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome", headless=True)
        p=await b.new_page()
        await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await p.wait_for_timeout(3000)
        t=await p.locator("body").inner_text()
        open("_audit/318修复/bodies_wsqs.txt","w",encoding="utf-8").write(t)
        lines=[x.strip() for x in t.splitlines()]
        pat=re.compile(r"^(\d{3})期【([^】]+)】开([0-9.]+)?(准|错)?$")
        rows=[(m.group(1),m.group(2),m.group(3),m.group(4)) for l in lines for m in [pat.match(l)] if m]
        print("严格格式行数", len(rows), "期号唯一", len({r[0] for r in rows})==len(rows))
        for r in rows[:5]: print("  ", r)
        print("含『平特玄机』行数", sum(1 for l in lines if "平特玄机" in l))
        await b.close()
asyncio.run(main())
