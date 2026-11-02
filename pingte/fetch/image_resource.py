from __future__ import annotations

import base64
import re
from collections.abc import Callable, Iterable, Mapping
from urllib.parse import urljoin

from pingte.domain.models import TargetProfile

from .html import html_to_text


def issue_pattern(issue: str) -> str:
    return rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)\s*期"


def target_image_urls(
    page_html: str,
    target: TargetProfile,
    issue: str,
) -> list[str]:
    forum_parts = re.split(
        r'(?=<div\b[^>]*class=["\'][^"\']*detail_info_forum2_item[^"\']*["\'])',
        page_html,
        flags=re.I,
    )
    matching_forum_parts: list[tuple[str, list[str]]] = []
    for part in forum_parts[1:]:
        head = part.split('<div class="forum-body">', 1)[0]
        head_text = html_to_text(head)
        if target.name not in head_text or (
            target.keyword and target.keyword not in head_text
        ):
            continue
        content_match = re.search(
            r'<div\b[^>]*class=["\'][^"\']*\bcontent\b[^"\']*["\'][^>]*>([\s\S]*?)</div>',
            part,
            re.I,
        )
        urls = (
            re.findall(
                r'<img[^>]+(?:data-original|src)=["\']([^"\']+)["\']',
                content_match.group(1),
                re.I,
            )
            if content_match
            else []
        )
        matching_forum_parts.append((head_text, list(dict.fromkeys(urls))))
    if matching_forum_parts:
        if len(matching_forum_parts) != 1:
            raise RuntimeError(
                f"目标图片标题区块不唯一：{len(matching_forum_parts)}个"
            )
        return matching_forum_parts[0][1]

    marker = issue_pattern(issue)
    blocks = re.findall(
        r"<(?:section|article|div|li)\b[^>]*>[\s\S]*?</(?:section|article|div|li)>",
        page_html,
        re.I,
    )
    matching_blocks: list[list[str]] = []
    for block in blocks:
        block_text = html_to_text(block)
        if not re.search(marker, block_text) or target.name not in block_text:
            continue
        if target.keyword and target.keyword not in block_text:
            continue
        matching_blocks.append(
            list(
                dict.fromkeys(
                    re.findall(
                        r'<img[^>]+(?:data-original|src)=["\']([^"\']+)["\']',
                        block,
                        re.I,
                    )
                )
            )
        )
    if len(matching_blocks) > 1:
        raise RuntimeError(f"目标图片正文区块不唯一：{len(matching_blocks)}个")
    return matching_blocks[0] if matching_blocks else []


def special_image_issue_lines(
    url: str,
    page_html: str,
    timeout: int,
    issue: str | None,
    diagnostics: list[str] | None,
    session: object,
    *,
    image_targets: Mapping[str, str],
    image_result_formats: Mapping[str, str],
    targets: Iterable[TargetProfile],
    fetch_bytes: Callable[[str, int, object], bytes],
    extract_zodiac: Callable[[bytes, str], str | None],
    extract_summary_zodiac: Callable[[bytes, str], str | None],
) -> list[str]:
    if not issue:
        return []
    prefix = image_targets.get(url, "")
    if not prefix:
        return []
    target = next(
        (
            item
            for item in targets
            if item.url == url and item.name == prefix
        ),
        None,
    )
    if target is None:
        return []
    lines: list[str] = []
    extractor = (
        extract_summary_zodiac
        if image_result_formats.get(url) == "exact_summary"
        else extract_zodiac
    )
    for image_url in target_image_urls(page_html, target, issue):
        absolute_url = urljoin(url, image_url)
        try:
            raw = fetch_bytes(absolute_url, timeout, session)
            zodiac = extractor(raw, issue)
        except Exception as exc:
            if diagnostics is not None:
                diagnostics.append(
                    f"图片 {absolute_url}：{type(exc).__name__}: {exc}"
                )
            continue
        if zodiac:
            lines.append(f"{prefix} {int(issue)}期：{zodiac}")
    return lines


def decode_data_image_uri(value: str) -> bytes | None:
    match = re.fullmatch(
        r"data:image/(?:png|jpe?g);base64,([A-Za-z0-9+/=\s]+)",
        value,
        re.I,
    )
    if not match:
        return None
    try:
        return base64.b64decode(
            re.sub(r"\s+", "", match.group(1)),
            validate=True,
        )
    except (ValueError, base64.binascii.Error):
        return None


def browser_image_issue_lines_from_sections(
    sections: list[tuple[str, list[str]]],
    targets: list[TargetProfile],
    issue: str,
    *,
    extract_zodiac: Callable[[bytes, str], str | None],
) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    diagnostics: list[str] = []
    for target in targets:
        matches = [
            sources
            for header, sources in sections
            if target.name in header and target.keyword in header
        ]
        if len(matches) != 1:
            diagnostics.append(
                f"{target.name}：目标标题区块数量为{len(matches)}，必须唯一"
            )
            continue
        candidates = []
        for source in matches[0]:
            raw = decode_data_image_uri(source)
            if not raw:
                continue
            zodiac = extract_zodiac(raw, issue)
            if zodiac:
                candidates.append(zodiac)
        distinct = list(dict.fromkeys(candidates))
        if len(distinct) > 1:
            diagnostics.append(
                f"{target.name}：目标正文图片内同一期出现不同生肖："
                f"{'、'.join(distinct)}"
            )
        elif distinct:
            lines.append(f"{target.name} {int(issue)}期：{distinct[0]}")
        else:
            diagnostics.append(
                f"{target.name}：目标正文图片没有精确识别到{int(issue)}期生肖"
            )
    return lines, diagnostics
