from __future__ import annotations

import asyncio
import unittest

from pingte.fetch.browser_fetcher import LAZY_CONTENT_STYLE, reveal_lazy_content


class FakePage:
    def __init__(self, skipped: int, *, evaluate_error: bool = False) -> None:
        self.skipped = skipped
        self.evaluate_error = evaluate_error
        self.styles: list[str] = []
        self.waits: list[int] = []

    async def evaluate(self, script: str) -> int:
        if self.evaluate_error:
            raise RuntimeError("evaluate failed")
        return self.skipped

    async def add_style_tag(self, *, content: str) -> None:
        self.styles.append(content)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


class RevealLazyContentTests(unittest.TestCase):
    def run_reveal(self, page: FakePage) -> bool:
        return asyncio.run(reveal_lazy_content(page))

    def test_forced_render_when_sections_are_skipped(self) -> None:
        page = FakePage(skipped=79)

        revealed = self.run_reveal(page)

        self.assertTrue(revealed)
        self.assertEqual(page.styles, [LAZY_CONTENT_STYLE])
        self.assertIn("content-visibility:visible", LAZY_CONTENT_STYLE)

    def test_untouched_page_without_skipped_sections(self) -> None:
        page = FakePage(skipped=0)

        revealed = self.run_reveal(page)

        self.assertFalse(revealed)
        self.assertEqual(page.styles, [])

    def test_evaluate_failure_is_not_fatal(self) -> None:
        page = FakePage(skipped=0, evaluate_error=True)

        revealed = self.run_reveal(page)

        self.assertFalse(revealed)
        self.assertEqual(page.styles, [])


if __name__ == "__main__":
    unittest.main()
