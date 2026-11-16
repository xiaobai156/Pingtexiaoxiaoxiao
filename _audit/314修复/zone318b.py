"""按专区列出 AAAAA 肖系列卡片的最新期数，确认 318 是否存在于任一专区。"""
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
        await page.wait_for_timeout(1200)
        for _ in range(4):
            await page.mouse.wheel(0, 15000)
            await page.wait_for_timeout(600)

        data = await page.evaluate(
            """() => {
              const zones = ['澳门AI专区','香港AI专区'];
              const out = {};
              for (const z of zones) {
                const holders = [...document.querySelectorAll('*')].filter(e => {
                  const t = e.innerText || '';
                  return e.children.length > 0 && t.includes(z) && t.length < 4000000;
                });
                // 取包含该专区名且含 AAAAA 的最小容器
                const cand = holders
                  .filter(e => (e.innerText || '').includes('AAAAA级大公开'))
                  .sort((a,b) => (a.innerText||'').length - (b.innerText||'').length);
                const root = cand[0];
                if (!root) { out[z] = null; continue; }
                const txt = root.innerText || '';
                const xiao = [...txt.matchAll(/AAAAA级大公开(\\d+)期[\\s\\S]{0,200}?平特一肖\\s*[：:]/g)]
                  .map(m => m[1]);
                const tail = [...txt.matchAll(/AAAAA级大公开(\\d+)期/g)].map(m => m[1]);
                out[z] = {xiaoCount: xiao.length, xiaoNewest: xiao.slice(0,5),
                          titleNewest: tail.slice(0,5), len: txt.length};
              }
              return out;
            }"""
        )
        for z, v in data.items():
            print(z, v)
        body = await page.locator("body").inner_text()
        print("全页 318期:平特一肖 出现:", body.count("318期:平特一肖"))
        print("全页 平特一肖 ： 出现:", body.count("平特一肖 ："))
        await browser.close()


asyncio.run(main())
