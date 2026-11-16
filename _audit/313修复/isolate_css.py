"""隔离验证：到底是哪条 CSS 让 innerText 漏读。"""
from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")

URL = sys.argv[1] if len(sys.argv) > 1 else "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/"
VARIANTS = [
    ("基线", ""),
    ("只 content-visibility", "*{content-visibility:visible!important}"),
    ("只 contain-intrinsic-size", "*{contain-intrinsic-size:auto!important}"),
    ("只 contain:style", "*{contain:style!important}"),
    (
        "可见性生效后的自动值",
        "*{content-visibility:visible!important;contain-intrinsic-size:auto!important}",
    ),
]


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
        for label, css in VARIANTS:
            page = await browser.new_page()
            await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            before = await page.locator("body").inner_text(timeout=45000)
            if css:
                await page.add_style_tag(content=css)
                await page.wait_for_timeout(800)
            after = await page.locator("body").inner_text(timeout=45000)
            count = await page.evaluate(
                "() => [...document.querySelectorAll('*')].filter("
                "e => getComputedStyle(e).contentVisibility === 'auto').length"
            )
            print(
                f"{label:<26} 前={len(before):<7} 后={len(after):<7} "
                f"含蛇蛇蛇={after.count('蛇蛇蛇')} contentVisibility=auto 元素数={count}"
            )
            await page.close()
        await browser.close()


asyncio.run(main())
