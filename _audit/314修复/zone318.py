"""定位 AAAAA 卡片所属专区（澳门/香港）与卡内最新期。"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

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
        await page.wait_for_timeout(8000)
        await page.add_style_tag(content="*{content-visibility:visible!important}")
        await page.wait_for_timeout(1200)

        data = await page.evaluate(
            """() => {
              const cards = [...document.querySelectorAll('*')].filter(
                e => e.className && String(e.className).includes('card_content'));
              return cards.map((c, i) => {
                const t = c.innerText || '';
                const lines = t.split('\\n').map(x => x.trim()).filter(Boolean);
                // 找最近的专区标题
                let el = c, zone = '';
                for (let up = 0; up < 12 && el; up++) {
                  el = el.parentElement;
                  if (!el) break;
                  const txt = (el.innerText || '');
                  for (const z of ['澳门AI专区', '香港AI专区', '澳门AI', '香港AI']) {
                    if (txt.includes(z)) { zone = z; break; }
                  }
                  if (zone) break;
                }
                return {
                  idx: i, zone, first: lines[0] || '', n: lines.length,
                  hasXiao: t.includes('平特一肖 ：'), hasTail: t.includes('必中⑦尾'),
                };
              });
            }"""
        )
        print("卡片总数", len(data))
        for r in data:
            if r["hasXiao"]:
                print(f"  card#{r['idx']} zone={r['zone']!r} first={r['first']!r} 行={r['n']} 肖={r['hasXiao']} 尾={r['hasTail']}")
        await browser.close()


asyncio.run(main())
