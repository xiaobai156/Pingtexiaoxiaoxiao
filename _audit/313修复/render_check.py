"""对失败清单每个 URL 对比 inner_text 与「强制渲染后」的正文，判断是否惰性渲染漏读。"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ISSUE = "317"


def load_urls() -> list[tuple[str, str]]:
    text = (HERE / "failure.txt").read_text(encoding="utf-8")
    seen: dict[str, list[str]] = {}
    for name, url in re.findall(r"失败 (\S+) (\S+) 方向", text):
        seen.setdefault(url, []).append(name)
    return [(names[0], url, ",".join(names)) for url, names in seen.items()]  # type: ignore[misc]


RESULT = re.compile(rf"(?<!\d){ISSUE}(?!\d)\s*期?[^\n]{{0,40}}?[\u4e00-\u9fa5]{{0,8}}肖?[^\n]{{0,12}}?[【〖\[]?([{chr(0x4E00)}-{chr(0x9FFF)}]{{2,4}})[】〗\]]?[^\n]{{0,10}}开")


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
        report = []
        for name, url, allnames in load_urls():
            page = await browser.new_page()
            row = {"name": name, "all": allnames, "url": url}
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)
                plain = await page.locator("body").inner_text(timeout=45000)
                html = await page.content()
                await page.add_style_tag(
                    content="*{content-visibility:visible!important;"
                    "contain-intrinsic-size:auto!important}"
                )
                await page.wait_for_timeout(800)
                forced = await page.locator("body").inner_text(timeout=45000)
            except Exception as exc:  # noqa: BLE001
                row["error"] = f"{type(exc).__name__}: {exc}"
                report.append(row)
                await page.close()
                continue
            row["plain_len"] = len(plain)
            row["forced_len"] = len(forced)
            row["html_len"] = len(html)
            row["plain_rows"] = len(
                [l for l in plain.splitlines() if re.search(rf"(?<!\d){ISSUE}(?!\d)", l)]
            )
            row["forced_rows"] = len(
                [l for l in forced.splitlines() if re.search(rf"(?<!\d){ISSUE}(?!\d)", l)]
            )
            row["forced_hits"] = [
                l.strip()[:110]
                for l in forced.splitlines()
                if re.search(rf"(?<!\d){ISSUE}(?!\d)", l) and "开" in l
            ][:6]
            print(
                f"{name:<8} plain={row['plain_len']:<7} forced={row['forced_len']:<7} "
                f"html={row['html_len']:<8} 行数 {row['plain_rows']}->{row['forced_rows']}"
            )
            for hit in row["forced_hits"]:
                print("      |", hit)
            report.append(row)
            await page.close()
        (HERE / f"render-check-{ISSUE}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        await browser.close()


asyncio.run(main())
