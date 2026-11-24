import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
URL="https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/741286.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome",headless=True)
        p=await b.new_page()
        await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await p.wait_for_timeout(800)
        links = await p.eval_on_selector_all("a", "els=>els.map(e=>[e.innerText.trim(), e.getAttribute('href')])")
        for t,h in links:
            if t and ("平特" in t or "买码" in t):
                print(repr(t), h)
        await b.close()
asyncio.run(main())
