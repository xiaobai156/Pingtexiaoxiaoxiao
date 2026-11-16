"""对失败清单每个 URL 保存「强制渲染后」正文，供离线重新解析。"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT = HERE / "forced"
OUT.mkdir(exist_ok=True)
ISSUE = "317"

FORCE_CSS = (
    "*{content-visibility:visible!important;"
    "contain-intrinsic-size:auto!important;"
    "contain:style!important}"
)


def safe(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name)


def load_urls() -> list[tuple[str, str, str]]:
    text = (HERE / "failure.txt").read_text(encoding="utf-8")
    seen: dict[str, list[str]] = {}
    for name, url in re.findall(r"失败 (\S+) (\S+) 方向", text):
        seen.setdefault(url, []).append(name)
    return [(names[0], url, ",".join(names)) for url, names in seen.items()]  # type: ignore[misc]


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
        for name, url, allnames in load_urls():
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)
                plain = await page.locator("body").inner_text(timeout=45000)
                await page.add_style_tag(content=FORCE_CSS)
                await page.wait_for_timeout(1200)
                forced = await page.locator("body").inner_text(timeout=45000)
            except Exception as exc:  # noqa: BLE001
                print(f"ERR {name} {type(exc).__name__}: {exc}")
                await page.close()
                continue
            (OUT / f"{safe(name)}-plain.txt").write_text(plain, encoding="utf-8")
            (OUT / f"{safe(name)}-forced.txt").write_text(forced, encoding="utf-8")
            print(
                f"OK {name:<10} plain={len(plain):<7} forced={len(forced):<7}"
                f" 同URL={allnames}"
            )
            await page.close()
        await browser.close()


asyncio.run(main())
