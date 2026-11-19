import asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8")
URL="https://gboqrz.hmf0d-gnako-vspyqi.work/topic/454146.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome", headless=True, args=[])
        p=await b.new_page()
        await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await p.wait_for_timeout(3000)
        t=await p.locator("body").inner_text()
        open("_audit/318修复/bodies_dafaci.txt","w",encoding="utf-8").write(t)
        lines=[x.strip() for x in t.splitlines() if x.strip()]
        print("总行数", len(lines), "长度", len(t))
        for i,l in enumerate(lines):
            if "成语平特" in l or re.search(r"32[0-9]期", l): print(f"  {i+1}: {l[:110]}")
        await b.close()
asyncio.run(main())
