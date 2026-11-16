"""点开 AAAAA 组件的 318 期标签，确认该卡片里到底有什么。"""
from __future__ import annotations
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")
URL = "https://mwcyukkv.agx2u-9h1th-ycwtgx.cyou:17488/"


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
        page = await browser.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(9000)
        await page.add_style_tag(content="*{content-visibility:visible!important}")
        await page.wait_for_timeout(1500)

        before = await page.evaluate(
            """() => {
              const cards = [...document.querySelectorAll('*')].filter(
                e => e.className && String(e.className).includes('card_content'));
              const hit = cards.filter(c => (c.innerText||'').includes('AAAAA级大公开'));
              return hit.slice(0,3).map(c => (c.innerText||'').replace(/\\n+/g,' | ').slice(0,300));
            }"""
        )
        print("点前 前3张卡片:")
        for b in before:
            print("   ", b)

        # 找 318期 标签并点击（AA AAA 组件内的 tab）
        clicked = await page.evaluate(
            """() => {
              const tabs = [...document.querySelectorAll('*')].filter(e =>
                e.children.length === 0 && (e.innerText||'').trim() === '318期');
              const info = tabs.map(t => ({tag: t.tagName, cls: String(t.className).slice(0,60)}));
              if (tabs.length) tabs[0].click();
              return {count: tabs.length, info: info.slice(0,4)};
            }"""
        )
        print("318期 标签:", clicked)
        await page.wait_for_timeout(2500)

        after = await page.evaluate(
            """() => {
              const cards = [...document.querySelectorAll('*')].filter(
                e => e.className && String(e.className).includes('card_content'));
              const hit = cards.filter(c => (c.innerText||'').includes('AAAAA级大公开'));
              return hit.slice(0,3).map(c => (c.innerText||'').replace(/\\n+/g,' | ').slice(0,300));
            }"""
        )
        print("点后 前3张卡片:")
        for a in after:
            print("   ", a)
        await browser.close()


asyncio.run(main())
