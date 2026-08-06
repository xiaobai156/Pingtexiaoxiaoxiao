from __future__ import annotations

import base64
import html
import re
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag.lower() in {
            "br",
            "p",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
            "section",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag.lower() in {
            "p",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
            "section",
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return html.unescape("".join(self.parts))


def html_fragment_to_text(page_html: str) -> str:
    parser = TextExtractor()
    parser.feed(page_html)
    lines = []
    for line in parser.text().splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def decoded_html_chunks(page_html: str) -> list[str]:
    chunks: list[str] = []
    for encoded in re.findall(r'strdecode\("([A-Za-z0-9+/=]+)"\)', page_html):
        try:
            chunks.append(
                base64.b64decode(encoded).decode("utf-8", errors="ignore")
            )
        except Exception:
            continue
    for _target, encoded in re.findall(
        r"decrypt\('([^']+)'\s*,\s*'([^']+)'\)",
        page_html,
    ):
        try:
            chunks.append(
                base64.b64decode(encoded).decode("gb18030", errors="ignore")
            )
        except Exception:
            continue
    return chunks


def html_to_text(page_html: str) -> str:
    return "\n".join(
        text
        for text in (
            html_fragment_to_text(item)
            for item in (page_html, *decoded_html_chunks(page_html))
        )
        if text
    )


def expand_encoded_html(page_html: str) -> str:
    return "\n".join((page_html, *decoded_html_chunks(page_html)))
