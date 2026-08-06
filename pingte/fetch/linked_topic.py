from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlsplit

from .html import html_to_text


def issue_pattern(issue: str) -> str:
    return rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)\s*期"


def fetch_linked_topic_text(
    url: str,
    page_html: str,
    timeout: int,
    issue: str | None,
    rules: Iterable[dict],
    fetch_detail: Callable[[str, int, str, set[str] | None, object], str],
    visited: set[str] | None = None,
    session: object = None,
) -> str:
    if not issue:
        return ""
    marker = issue_pattern(issue)
    matching_urls: list[str] = []
    for item in rules:
        if item.get("mode") != "linked_topic":
            continue
        part = str(item.get("url_contains", ""))
        name = str(item.get("name", ""))
        keyword = str(item.get("keyword", ""))
        if not part or part != url or not name or not keyword:
            continue
        links = re.findall(
            r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            page_html,
            re.I,
        )
        for href, body in links:
            title = html_to_text(body)
            if re.search(marker, title) and name in title and keyword in title:
                linked_url = urljoin(url, href)
                parent = urlsplit(url)
                linked = urlsplit(linked_url)
                if (
                    linked.scheme.lower() != parent.scheme.lower()
                    or linked.netloc.lower() != parent.netloc.lower()
                ):
                    raise RuntimeError(f"关联正文必须同源：{linked_url}")
                if (
                    not re.fullmatch(r"/topic/\d+\.html", linked.path)
                    or linked.query
                    or linked.fragment
                ):
                    raise RuntimeError(f"关联正文不是有效详情链接：{linked_url}")
                if linked_url not in matching_urls:
                    matching_urls.append(linked_url)
    if not matching_urls:
        return ""
    if len(matching_urls) != 1:
        raise RuntimeError(f"关联正文匹配不唯一：{len(matching_urls)}条")
    linked_url = matching_urls[0]
    if linked_url in (visited or set()):
        raise RuntimeError(f"关联正文循环：{linked_url}")
    return fetch_detail(linked_url, timeout, issue, visited, session)
