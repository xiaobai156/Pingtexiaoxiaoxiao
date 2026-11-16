"""检查 318 期 AAAAA 区块在 DOM 里是否有 innerText 未体现的内容。"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
URL = "https://mwcyukkv.agx2u-9h1th-ycwtgx.cyou:17488/"
OUT = Path(__file__).resolve().parent / "deep318"
OUT.mkdir(exist_ok=True)


async def main() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = None
        for channel in ("chrome", "msedge"):
            try:
                browser = await pw.chromium.launch(channel=channel, headless=True)
                break
            except Exception as exc:  # noqa: BLE001
                print("launch 失败", channel, exc)
        if browser is None:
            return
        page = await browser.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        await page.add_style_tag(content="*{content-visibility:visible!important}")
        await page.wait_for_timeout(1500)

        info = await page.evaluate(
            """() => {
              const out = [];
              const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
              let node;
              while ((node = walker.nextNode())) {
                const t = (node.textContent || '').trim();
                if (t.includes('AAAAA级大公开318期')) {
                  let el = node.parentElement;
                  for (let i = 0; i < 3 && el && el.parentElement; i++) el = el.parentElement;
                  out.push({text: t, len: t.length});
                }
              }
              const holders = [...document.querySelectorAll('*')].filter(
                e => (e.innerText || '').includes('AAAAA级大公开318期')
              ).slice(0, 8).map(e => ({
                tag: e.tagName, cls: e.className,
                html: e.innerHTML.slice(0, 2500),
                text: (e.innerText || '').slice(0, 800),
              }));
              return {count: out.length, holders};
            }"""
        )
        print("文本节点命中", info["count"])
        for i, h in enumerate(info["holders"]):
            print(f"--- holder {i} tag={h['tag']} cls={h['cls'][:60]}")
            print("TEXT:", h["text"][:600].replace("\n", " | "))
            (OUT / f"holder{i}.html").write_text(h["html"], encoding="utf-8")
            (OUT / f"holder{i}.txt").write_text(h["text"], encoding="utf-8")
        html = await page.content()
        (OUT / "page.html").write_text(html, encoding="utf-8")
        print("页面 HTML 长度", len(html), "318 计数", html.count("AAAAA级大公开318期"))
        await browser.close()


asyncio.run(main())
