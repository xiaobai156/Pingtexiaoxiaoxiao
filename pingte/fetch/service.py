from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from urllib.parse import urljoin, urlsplit

from pingte.domain.models import SourceDocument, TargetProfile

from .documents import (
    deserialize_source_documents,
    make_source_document,
    serialize_source_documents,
)
from .dynamic_record import fetch_vue_hash_text
from .html import decoded_html_chunks, expand_encoded_html, html_fragment_to_text
from .image_resource import special_image_issue_lines
from .linked_topic import fetch_linked_topic_text


def _dynamic_document_id(text: str) -> str:
    match = re.search(r"\[\[FORUM:(\d+)\]\]", text)
    return match.group(1) if match else ""


RawFetch = Callable[[str, int, object], str]
BytesFetch = Callable[[str, int, object], bytes]
ImageExtract = Callable[[bytes, str], str | None]


class FetchService:
    def __init__(
        self,
        *,
        targets: Iterable[TargetProfile],
        rules: Iterable[dict],
        image_targets: Mapping[str, str],
        raw_fetch: RawFetch,
        bytes_fetch: BytesFetch,
        image_extract: ImageExtract,
        image_summary_extract: ImageExtract,
    ) -> None:
        self.targets = tuple(targets)
        self.rules = tuple(rules)
        self.image_targets = dict(image_targets)
        self.raw_fetch = raw_fetch
        self.bytes_fetch = bytes_fetch
        self.image_extract = image_extract
        self.image_summary_extract = image_summary_extract
        self.image_result_formats = {
            str(rule.get("url_contains", "")): str(
                rule.get("image_result_format", "")
            )
            for rule in self.rules
            if rule.get("source_strategy") == "image_resource"
            and rule.get("image_result_format")
        }

    def fetch_text(
        self,
        url: str,
        timeout: int,
        issue: str | None = None,
        visited: set[str] | None = None,
        session: object = None,
    ) -> str:
        seen = set(visited or ())
        if url in seen:
            raise RuntimeError(f"关联正文循环：{url}")
        seen.add(url)
        page_html = self.raw_fetch(url, timeout, session)
        script_documents: list[tuple[str, str]] = []
        diagnostics: list[str] = []
        script_srcs = re.findall(
            r'<script[^>]+src=["\']([^"\']+)["\']',
            page_html,
            re.I,
        )
        for src in script_srcs:
            full_url = urljoin(url, src)
            if "/upload/script/" not in full_url:
                continue
            try:
                script_documents.append(
                    (full_url, self.raw_fetch(full_url, timeout, session))
                )
            except Exception as exc:
                diagnostics.append(
                    f"脚本 {full_url}：{type(exc).__name__}: {exc}"
                )

        resource_html = "\n".join(
            (page_html, *(item[1] for item in script_documents))
        )
        expanded_html = expand_encoded_html(resource_html)
        script_texts_by_url: dict[str, str] = {}
        for script_url, script_html in script_documents:
            script_text = "\n".join(
                text
                for chunk in decoded_html_chunks(script_html)
                if (text := html_fragment_to_text(chunk))
            )
            if script_text:
                script_texts_by_url[script_url] = script_text
        linked_mode = any(
            item.get("mode") == "linked_topic"
            and str(item.get("url_contains", "")) == url
            for item in self.rules
        )
        linked_text = ""
        try:
            linked_text = fetch_linked_topic_text(
                url,
                page_html,
                timeout,
                issue,
                self.rules,
                self.fetch_text,
                seen,
                session,
            )
        except Exception as exc:
            if linked_mode:
                raise RuntimeError(
                    f"关联正文抓取失败：{type(exc).__name__}: {exc}"
                ) from exc
            diagnostics.append(f"关联正文：{type(exc).__name__}: {exc}")

        try:
            extra_lines = special_image_issue_lines(
                url,
                expanded_html,
                timeout,
                issue,
                diagnostics,
                session,
                image_targets=self.image_targets,
                image_result_formats=self.image_result_formats,
                targets=self.targets,
                fetch_bytes=self.bytes_fetch,
                extract_zodiac=self.image_extract,
                extract_summary_zodiac=self.image_summary_extract,
            )
        except Exception as exc:
            diagnostics.append(f"图片资源：{type(exc).__name__}: {exc}")
            extra_lines = []

        try:
            dynamic_text = fetch_vue_hash_text(
                url,
                timeout,
                issue,
                session,
                targets=self.targets,
                rules=self.rules,
                fetch_raw=self.raw_fetch,
            )
        except Exception as exc:
            diagnostics.append(f"论坛接口：{type(exc).__name__}: {exc}")
            dynamic_text = ""

        external_script_rules = [
            rule
            for rule in self.rules
            if rule.get("source_strategy") == "external_script"
            and str(rule.get("url_contains", "")) == url
        ]
        documents: list[SourceDocument]
        if linked_mode:
            documents = deserialize_source_documents(linked_text)
        elif dynamic_text:
            documents = [
                make_source_document(
                    "dynamic-api-record",
                    url,
                    True,
                    dynamic_text,
                    document_id=_dynamic_document_id(dynamic_text),
                )
            ]
        elif (
            urlsplit(url).fragment
            and "zcphjs.ce83x-ms2rz-orwude.work" in urlsplit(url).netloc
        ):
            documents = []
        elif url in self.image_targets:
            documents = [
                make_source_document(
                    "image-resource",
                    url,
                    True,
                    "\n".join(extra_lines),
                )
            ]
        elif external_script_rules:
            documents = []
            for rule in external_script_rules:
                anchor = str(rule.get("source_document_anchor", "")).strip()
                keyword = str(rule.get("keyword", "")).strip()
                matches = [
                    (script_url, script_text)
                    for script_url, script_text in script_texts_by_url.items()
                    if anchor in script_text
                    and (not keyword or keyword in script_text)
                ]
                if len(matches) != 1:
                    diagnostics.append(
                        f"{rule.get('name', '')}：页面引用的目标外部脚本文档"
                        f"数量为{len(matches)}，必须唯一"
                    )
                    continue
                script_url, script_text = matches[0]
                documents.append(
                    make_source_document(
                        "external-script",
                        script_url,
                        True,
                        script_text,
                        document_id=str(rule.get("target_id", "")),
                    )
                )
        else:
            documents = [
                make_source_document(
                    "http-main",
                    url,
                    True,
                    html_fragment_to_text(page_html),
                )
            ]
            documents.extend(
                make_source_document(
                    f"page-decoded:{index}",
                    url,
                    False,
                    html_fragment_to_text(chunk),
                )
                for index, chunk in enumerate(decoded_html_chunks(page_html))
            )
            for script_url, script_text in script_texts_by_url.items():
                documents.append(
                    make_source_document(
                        "external-script",
                        script_url,
                        False,
                        script_text,
                    )
                )
            if extra_lines:
                documents.append(
                    make_source_document(
                        "image-resource",
                        url,
                        False,
                        "\n".join(extra_lines),
                    )
                )

        if diagnostics:
            documents.append(
                make_source_document(
                    "diagnostic",
                    url,
                    False,
                    "\n".join(
                        f"[[附属资源失败:{item}]]" for item in diagnostics
                    ),
                )
            )
        return serialize_source_documents(documents)
