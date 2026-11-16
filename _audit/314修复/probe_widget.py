"""确认 AAAAA 两个栏目的最新期数：肖系列 vs 必中系列。"""
from __future__ import annotations
import asyncio
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
URL = "https://mwcyukkk.agx2u-9h1th-ycwtgx.cyou:17488/"
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
        await page.wait_for_timeout(10000)
        await page.add_style_tag(content="*{content-visibility:visible!important}")
        await page.wait_for_timeout(1000)
        for _ in range(6):
            await page.mouse.wheel(0, 20000)
            await page.wait_for_timeout(700)
        await page.wait_for_timeout(3000)

        data = await page.evaluate(
            """() => {
              const pick = (needle) => {
                const el = [...document.querySelectorAll('*')].filter(
                  e => e.children.length === 0 && (e.innerText||'').includes(needle)
                );
                return el.length;
              };
              const cards = [...document.querySelectorAll('*')].filter(e =>
                e.className && String(e.className).includes('card_content'));
              const rows = cards.map(c => {
                const t = c.innerText || '';
                const first = (t.split('\\n').filter(x => x.trim())[0] || '').trim();
                return {first, hasXiao: t.includes('①肖'), hasTail: t.includes('必中⑦尾'), len: t.length};
              });
              return rows;
            }"""
        )
        print("card_content 数量", len(data))
        seen = {}
        for r in data:
            m = re.search(r"(\d+)期", r["first"])
            if not m:
                continue
            key = ("肖" if r["hasXiao"] else "尾" if r["hasTail"] else "?")
            seen.setdefault(key, []).append(m.group(1))
        for key, issues in seen.items():
            print(f"栏目类型 {key}: 卡片 {len(issues)} 张, 最新 3 个 {issues[:3]}")
        await browser.close()


asyncio.run(main())
