import asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8")
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        for name,u in [("气冲牛斗","https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741286.html"),
                       ("大公无私","https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741288.html")]:
            p=await b.new_page()
            await p.goto(u, wait_until="domcontentloaded", timeout=30000)
            await p.wait_for_timeout(900)
            html=await p.content()
            await p.close()
            print("=====",name,"html len",len(html))
            for m in re.finditer(r"326\s*期[^<]{0,40}", html):
                s=m.group(0)
                if "平特" in s or "尾" in s or "肖" in s:
                    print("   ",repr(s))
            i=html.find("326期平特")
            print("   snippet:", repr(html[max(0,i-260):i+160]) if i>=0 else "NONE")
        await b.close()
asyncio.run(main())
