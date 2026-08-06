from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

from pingte.domain.models import TargetProfile

from .documents import make_source_document, serialize_source_documents
from .image_resource import (
    browser_image_issue_lines_from_sections,
    decode_data_image_uri,
)


FETCH_RETRIES = 3


@dataclass(frozen=True)
class BrowserFetchSpec:
    url: str
    required_anchors: tuple[str, ...] = ()
    image_headers: tuple[tuple[str, str], ...] = ()

    @property
    def capture_images(self) -> bool:
        return bool(self.image_headers)


@dataclass(frozen=True)
class BrowserCapture:
    requested_url: str
    final_url: str
    body: str
    image_sections: tuple[tuple[str, tuple[str, ...]], ...] = ()


def browser_url_matches(requested_url: str, final_url: str) -> bool:
    requested = urlsplit(requested_url)
    final = urlsplit(final_url)
    requested_path = requested.path.rstrip("/") or "/"
    final_path = final.path.rstrip("/") or "/"
    return (
        requested.scheme.lower() == final.scheme.lower()
        and requested.netloc.lower() == final.netloc.lower()
        and requested_path == final_path
        and requested.query == final.query
        and requested.fragment == final.fragment
    )


def retryable_browser_navigation_error(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}"
    return any(
        token in message
        for token in (
            "ERR_CONNECTION_CLOSED",
            "ERR_CONNECTION_RESET",
            "ERR_CONNECTION_REFUSED",
            "ERR_NETWORK_CHANGED",
            "ERR_TIMED_OUT",
            "TimeoutError",
        )
    )


async def navigate_browser_page_with_retry(
    page,
    url: str,
    timeout: int,
    *,
    retries: int = FETCH_RETRIES,
    logger: Callable[[str], None] | None = None,
) -> None:
    emit = logger or (lambda message: print(message, flush=True))
    for attempt in range(1, retries + 1):
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=max(1, timeout) * 1000,
            )
            return
        except Exception as exc:
            if attempt >= retries or not retryable_browser_navigation_error(exc):
                raise
            emit(
                f"[浏览器重试 {attempt}/{retries - 1}] 当前：{url}，"
                f"原因：{type(exc).__name__}: {exc}"
            )
            await page.wait_for_timeout(250 * attempt)


async def fetch_browser_main_text_with_retry(
    page,
    url: str,
    timeout: int,
    required_anchors: Iterable[str] = (),
    *,
    retries: int = FETCH_RETRIES,
    logger: Callable[[str], None] | None = None,
) -> str:
    emit = logger or (lambda message: print(message, flush=True))
    anchors = tuple(
        dict.fromkeys(
            anchor.strip()
            for anchor in required_anchors
            if anchor.strip()
        )
    )
    body_poll_attempts = 3 if anchors else 1
    last_reason = "浏览器主文档DOM为空"
    for attempt in range(1, retries + 1):
        await navigate_browser_page_with_retry(
            page,
            url,
            timeout,
            retries=retries,
            logger=emit,
        )
        await page.wait_for_timeout(min(1500, max(500, timeout * 100)))
        if not browser_url_matches(url, page.url):
            raise RuntimeError(f"浏览器最终URL不匹配：{page.url}")
        for body_attempt in range(1, body_poll_attempts + 1):
            body = await page.locator("body").inner_text(
                timeout=max(1, timeout) * 1000
            )
            if not body.strip():
                last_reason = "浏览器主文档DOM为空"
            else:
                missing = [anchor for anchor in anchors if anchor not in body]
                if not missing:
                    return body
                last_reason = "浏览器主文档缺少专属区块锚点：" + "、".join(
                    missing
                )
            if body_attempt < body_poll_attempts:
                await page.wait_for_timeout(250)
        if attempt < retries:
            emit(
                f"[浏览器DOM重试 {attempt}/{retries - 1}] 当前：{url}，"
                f"原因：{last_reason}"
            )
            await page.wait_for_timeout(250 * attempt)
    raise RuntimeError(last_reason)


async def browser_image_dom_sections(
    page,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    sections: list[tuple[str, tuple[str, ...]]] = []
    section_nodes = page.locator(".detail_info_forum2_item")
    for index in range(await section_nodes.count()):
        section = section_nodes.nth(index)
        header_node = section.locator(".forum-head")
        header = await header_node.inner_text() if await header_node.count() else ""
        image_nodes = section.locator(".content img")
        sources = [
            await image_nodes.nth(image_index).evaluate(
                "node => node.currentSrc || node.getAttribute('src') || "
                "node.getAttribute('data-original') || ''"
            )
            for image_index in range(await image_nodes.count())
        ]
        sections.append(
            (
                header.strip(),
                tuple(str(source) for source in sources if source),
            )
        )
    return tuple(sections)


def _matching_image_sources(
    sections: tuple[tuple[str, tuple[str, ...]], ...],
    headers: tuple[tuple[str, str], ...],
) -> list[str]:
    return [
        source
        for header, sources in sections
        for name, keyword in headers
        if name in header and keyword in header
        for source in sources
    ]


async def fetch_browser_captures_async(
    specs: Iterable[BrowserFetchSpec],
    timeout: int,
    issue: str | None = None,
    *,
    max_workers: int = 8,
    progress: Callable[[int, int, int, int, float, str], None] | None = None,
) -> tuple[dict[str, BrowserCapture], dict[str, str]]:
    from playwright.async_api import async_playwright

    spec_list = list(specs)
    urls = [spec.url for spec in spec_list]
    if len(urls) != len(set(urls)):
        raise ValueError("浏览器抓取规格 URL 必须唯一")
    captures: dict[str, BrowserCapture] = {}
    errors: dict[str, str] = {}
    limit = asyncio.Semaphore(max(1, max_workers))
    progress_lock = asyncio.Lock()
    completed = 0
    started_at = time.monotonic()

    async with async_playwright() as playwright:
        browser = None
        launch_errors = []
        for channel in ("chrome", "msedge"):
            try:
                browser = await playwright.chromium.launch(
                    channel=channel,
                    headless=True,
                )
                break
            except Exception as exc:
                launch_errors.append(f"{channel}: {type(exc).__name__}: {exc}")
        if browser is None:
            raise RuntimeError("浏览器启动失败：" + "；".join(launch_errors))
        context = await browser.new_context(ignore_https_errors=True)

        async def fetch_one(spec: BrowserFetchSpec) -> None:
            nonlocal completed
            async with limit:
                page = await context.new_page()

                async def block_heavy_resources(route) -> None:
                    resource_type = route.request.resource_type
                    if resource_type in {"media", "font"} or (
                        resource_type == "image" and not spec.capture_images
                    ):
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", block_heavy_resources)
                try:
                    if spec.capture_images:
                        await navigate_browser_page_with_retry(
                            page,
                            spec.url,
                            timeout,
                        )
                        await page.wait_for_timeout(
                            min(1500, max(500, timeout * 100))
                        )
                        if not browser_url_matches(spec.url, page.url):
                            raise RuntimeError(
                                f"浏览器最终URL不匹配：{page.url}"
                            )
                        if not issue:
                            raise RuntimeError("图片专属来源必须指定期数")
                        sections: tuple[
                            tuple[str, tuple[str, ...]], ...
                        ] = ()
                        for _attempt in range(max(1, timeout * 5)):
                            sections = await browser_image_dom_sections(page)
                            matching_sources = _matching_image_sources(
                                sections,
                                spec.image_headers,
                            )
                            if any(
                                decode_data_image_uri(source)
                                for source in matching_sources
                            ):
                                break
                            await page.wait_for_timeout(200)
                        captures[spec.url] = BrowserCapture(
                            requested_url=spec.url,
                            final_url=page.url,
                            body="",
                            image_sections=sections,
                        )
                    else:
                        body = await fetch_browser_main_text_with_retry(
                            page,
                            spec.url,
                            timeout,
                            required_anchors=spec.required_anchors,
                        )
                        captures[spec.url] = BrowserCapture(
                            requested_url=spec.url,
                            final_url=page.url,
                            body=body,
                        )
                except Exception as exc:
                    errors[spec.url] = f"{type(exc).__name__}: {exc}"
                finally:
                    await page.close()
                    async with progress_lock:
                        completed += 1
                        if progress:
                            progress(
                                completed,
                                len(spec_list),
                                len(captures),
                                len(errors),
                                started_at,
                                spec.url,
                            )

        try:
            await asyncio.gather(*(fetch_one(spec) for spec in spec_list))
        finally:
            await context.close()
            await browser.close()
    return captures, errors


def fetch_browser_captures(
    specs: Iterable[BrowserFetchSpec],
    timeout: int,
    issue: str | None = None,
    *,
    max_workers: int = 8,
    progress: Callable[[int, int, int, int, float, str], None] | None = None,
) -> tuple[dict[str, BrowserCapture], dict[str, str]]:
    spec_list = list(specs)
    if not spec_list:
        return {}, {}
    return asyncio.run(
        fetch_browser_captures_async(
            spec_list,
            timeout,
            issue,
            max_workers=max_workers,
            progress=progress,
        )
    )


def fetch_browser_texts(
    targets: Iterable[TargetProfile],
    timeout: int,
    issue: str,
    rule_book,
    image_targets: Mapping[str, str],
    image_extract: Callable[[bytes, str], str | None],
    progress: Callable[[int, int, int, int, float, str], None] | None = None,
    *,
    max_workers: int = 8,
) -> tuple[dict[str, str], dict[str, str]]:
    target_list = list(targets)
    if not target_list:
        return {}, {}
    urls = list(dict.fromkeys(target.url for target in target_list))
    targets_by_url = {
        url: [target for target in target_list if target.url == url]
        for url in urls
    }
    image_targets_by_url = {
        url: [
            target
            for target in targets_by_url[url]
            if image_targets.get(url) == target.name
        ]
        for url in urls
    }
    specs = [
        BrowserFetchSpec(
            url=url,
            required_anchors=tuple(
                anchor
                for target in targets_by_url[url]
                if (
                    anchor := str(
                        rule_book.rule_for(target).get(
                            "browser_required_anchor",
                            "",
                        )
                    ).strip()
                )
            ),
            image_headers=tuple(
                (target.name, target.keyword)
                for target in image_targets_by_url[url]
            ),
        )
        for url in urls
    ]
    captures, errors = fetch_browser_captures(
        specs,
        timeout,
        issue,
        max_workers=max_workers,
        progress=progress,
    )
    texts: dict[str, str] = {}
    for url, capture in captures.items():
        try:
            image_targets_for_url = image_targets_by_url[url]
            if image_targets_for_url:
                lines, diagnostics = browser_image_issue_lines_from_sections(
                    [(header, list(sources)) for header, sources in capture.image_sections],
                    image_targets_for_url,
                    str(issue),
                    extract_zodiac=image_extract,
                )
                documents = [
                    make_source_document(
                        "browser-image-resource",
                        capture.final_url,
                        True,
                        "\n".join(lines),
                    )
                ]
                if diagnostics:
                    documents.append(
                        make_source_document(
                            "diagnostic",
                            capture.final_url,
                            False,
                            "\n".join(
                                f"[[附属资源失败:{item}]]"
                                for item in diagnostics
                            ),
                        )
                    )
            else:
                documents = [
                    make_source_document(
                        "browser-main",
                        capture.final_url,
                        True,
                        capture.body,
                    )
                ]
            texts[url] = serialize_source_documents(documents)
        except Exception as exc:
            errors[url] = f"{type(exc).__name__}: {exc}"
    return texts, errors
