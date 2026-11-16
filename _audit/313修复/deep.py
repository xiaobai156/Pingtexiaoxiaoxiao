"""深查单个站点：帧、延迟渲染、正文是否含目标串。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

URL = sys.argv[1]
NEEDLE = sys.argv[2] if len(sys.argv) > 2 else "蛇蛇蛇"
OUT = Path(__file__).resolve().parent / "deep" / "deep.txt"


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
        await page.wait_for_timeout(8000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception as exc:  # noqa: BLE001
            print("networkidle 超时", type(exc).__name__)

        print("最终URL", page.url)
        frames = page.frames
        print("帧数", len(frames))
        for index, frame in enumerate(frames):
            try:
                text = await frame.locator("body").inner_text(timeout=8000)
            except Exception as exc:  # noqa: BLE001
                print(f"  帧{index} 读取失败 {type(exc).__name__}: {exc}")
                continue
            print(
                f"  帧{index} url={frame.url[:90]} 长度={len(text)} "
                f"含目标={text.count(NEEDLE)} 含开={text.count('平特一肖【')}"
            )

        body = await page.locator("body").inner_text(timeout=60000)
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(body, encoding="utf-8")
        print("主文档 inner_text 长度", len(body), "目标计数", body.count(NEEDLE))

        html = await page.content()
        (OUT.parent / "deep.html").write_text(html, encoding="utf-8")
        print("HTML 长度", len(html), "HTML 目标计数", html.count(NEEDLE))
        print(
            "有 iframe 标签", html.count("<iframe"),
            "有 table", html.count("<table"),
        )
        await browser.close()


asyncio.run(main())
