import asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8")
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        p=await b.new_page()
        await p.goto("https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741286.html", wait_until="domcontentloaded", timeout=30000)
        await p.wait_for_timeout(800)
        html = await p.content()
        i = html.find("326期平特")
        print("--- html around 326期平特 ---")
        print(html[max(0,i-700):i+500])
        await p.close()
        # 一尾 and 三肖
        for tag,u in [("一尾","https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741287.html"),("三肖","https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741285.html")]:
            p=await b.new_page()
            await p.goto(u, wait_until="domcontentloaded", timeout=30000)
            await p.wait_for_timeout(700)
            t=await p.locator("body").inner_text()
            await p.close()
            print(f"=== {tag} 正文行（含326）===")
            for x in t.splitlines():
                x=x.strip()
                if "326" in x and "平特" in x: print("   ",x)
        await b.close()
asyncio.run(main())
