"""DOM 级复核：强制渲染后统计 322 期成语平特相关节点，排除懒渲染/隐藏。"""
import asyncio, re, sys
sys.stdout.reconfigure(encoding="utf-8")
URL="https://gboqrz.hmf0d-gnako-vspyqi.work/topic/454146.html"
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b=await pw.chromium.launch(channel="chrome", headless=True)
        p=await b.new_page()
        await p.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await p.wait_for_timeout(2500)
        await p.add_style_tag(content="*{content-visibility:visible!important}")
        for _ in range(3):
            await p.mouse.wheel(0, 2000); await p.wait_for_timeout(600)
        html=await p.content()
        text=await p.locator("body").inner_text()
        open("_audit/318修复/dafaci_dom.html","w",encoding="utf-8").write(html)
        print("HTML 长度", len(html), "innerText 长度", len(text))
        for pat in ["322期: 成语平特", "322期:成语平特", "成语平特"]:
            print(f"HTML『{pat}』次数", html.count(pat))
        print("innerText『成语平特』行:")
        for l in [x.strip() for x in text.splitlines() if "成语平特" in x]: print("  ", l[:80])
        print("HTML 中所有 322期 + 成语 邻近片段:")
        for m in re.finditer(r"322期[^<]{0,40}", html):
            seg=m.group(0)
            if "成语" in seg or "平特" in seg: print("  ", seg[:80])
        await b.close()
asyncio.run(main())
