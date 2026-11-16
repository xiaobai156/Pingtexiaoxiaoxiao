"""列出 AAAAA『肖系列』卡片：所属专区、期数、平特一肖值。"""
from __future__ import annotations
import asyncio
import re
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
        await page.wait_for_timeout(8000)
        await page.add_style_tag(content="*{content-visibility:visible!important}")
        await page.wait_for_timeout(1500)

        rows = await page.evaluate(
            """() => {
              const cards = [...document.querySelectorAll('*')].filter(
                e => e.className && String(e.className).includes('card_content'));
              const out = [];
              for (const c of cards) {
                const t = c.innerText || '';
                if (!t.includes('平特一肖 ：')) continue;
                const lines = t.split('\\n').map(x => x.trim()).filter(Boolean);
                const title = lines.find(x => x.includes('AAAAA级大公开')) || '';
                const xiao = lines.find(x => x.includes('平特一肖 ：')) || '';
                let el = c, zone = '';
                for (let up = 0; up < 14 && el; up++) {
                  el = el.parentElement; if (!el) break;
                  const p = el.innerText || '';
                  for (const z of ['澳门AI专区','香港AI专区']) if (p.includes(z)) { zone = z; break; }
                  if (zone) break;
                }
                out.push({zone, title, xiao});
              }
              return out;
            }"""
        )
        print("肖系列卡片数", len(rows))
        for r in rows[:10]:
            print(f"  {r['zone']} | {r['title']} | {r['xiao']}")
        print("  最新期:", [re.search(r"(\d+)期", r["title"]).group(1) for r in rows[:4] if re.search(r"(\d+)期", r["title"])])
        await browser.close()


asyncio.run(main())
