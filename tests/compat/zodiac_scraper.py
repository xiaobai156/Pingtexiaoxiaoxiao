"""Compatibility facade for older callers.

Formal execution lives in ``run_single.py`` and ``run_multi.py``.  This module
only adapts the historical function names used by existing tests and scripts;
fetching, parsing, validation and storage are implemented in ``pingte``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError
from urllib.request import urlopen

from pingte.config.loader import load_compiled_config, load_targets
from pingte.config.schema import (
    ALLOWED_SOURCE_STRATEGIES,
    DATA_STRUCTURE_BY_MODE,
    SECTION_BOUNDARY_BY_MODE,
    validate_compiled_config,
)
from pingte.domain.failures import FailureCode, FailureDetail
from pingte.domain.models import SourceDocument, Target, TargetProfile, ValidatedResult
from pingte.domain.zodiac import ZODIACS
from pingte.fetch import browser_fetcher, dynamic_record, html as fetch_html
from pingte.fetch import http_fetcher, image_resource, linked_topic
from pingte.fetch.documents import deserialize_source_documents, serialize_source_documents
from pingte.fetch.http_fetcher import FetchSession
from pingte.fetch.service import FetchService
from pingte.parse import anchored_section as parsed_anchored
from pingte.parse import formula_section as parsed_formula
from pingte.parse import header_section as parsed_header
from pingte.parse import named_section as parsed_named
from pingte.parse.context import (
    ParserHooks,
    RuleBook,
    has_confirmed_result_structure,
    is_section_boundary,
    many_zodiac_category,
    selected_section_starts,
)
from pingte.parse.custom import image_result
from pingte.parse.registry import DedicatedParserRegistry
from pingte.storage.cache import CacheStore
from pingte.storage.output import (
    atomic_write_text,
    build_output,
    date_label,
    default_output_paths as _default_output_paths,
    progress_line,
)
from pingte.validation.boundary import (
    auxiliary_failure_reason,
    missing_target_issue_reason as _missing_target_issue_reason,
    pending_issue_reason as _pending_issue_reason,
    unavailable_reason,
)
from pingte.validation.identity import target_cache_key, unique_urls
from pingte.validation.issue import (
    ANY_ISSUE_PATTERN,
    dedupe_zodiac,
    extract_target_zodiac,
    extract_zodiac,
    issue_pattern,
    zodiac_chars,
    zodiac_from_open_numbers,
)
from pingte.validation.result import ValidationOutcome, validate_documents
from pingte.application.site_pipeline import PipelineTargetResult, SitePipeline

TextExtractor = fetch_html.TextExtractor
decode_bytes = http_fetcher.decode_bytes
html_fragment_to_text = fetch_html.html_fragment_to_text
decoded_html_chunks = fetch_html.decoded_html_chunks
html_to_text = fetch_html.html_to_text
expand_encoded_html = fetch_html.expand_encoded_html


FETCH_RETRIES = 3
MAX_WORKERS = 8
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "targets.json"
RECENT_10_CACHE_PATH = PROJECT_ROOT / "recent_10_cache.json"
RECENT_10_CACHE_WINDOW = 10
OUTPUT_DIR = Path(
    r"C:\Users\Administrator\Desktop\每天工具\数据系列\大围杀号生肖数据统一归纳"
)
IMAGE_TEMPLATE_CACHE = image_result.IMAGE_TEMPLATE_CACHE


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    return load_compiled_config(path)


validate_config = validate_compiled_config
CONFIG = validate_config(load_config())
TARGETS = load_targets(CONFIG)


def load_contains_map(config: dict, key: str, value_key: str) -> dict[str, str]:
    return {
        str(item["url_contains"]): str(item[value_key])
        for item in config.get(key, [])
        if isinstance(item, dict) and item.get("url_contains") and item.get(value_key)
    }


SPECIAL_IMAGE_TARGETS = load_contains_map(CONFIG, "special_image_targets", "name")
SPECIAL_FOLLOWUP_LABELS = load_contains_map(CONFIG, "special_followup_labels", "label")
SPECIAL_PARSE_TARGETS = CONFIG.get("special_parse_targets", [])
SPECIAL_PARSE_MODES = {
    str(item["url_contains"]): str(item["mode"])
    for item in SPECIAL_PARSE_TARGETS
    if isinstance(item, dict) and item.get("url_contains") and item.get("mode")
}
DEFAULT_SPECIAL_PARSE_MODES = SPECIAL_PARSE_MODES.copy()
DEDICATED_BOTTOM_ISSUE_ZODIAC_NAMES = {"赌神平特", "小白平特"}
DEDICATED_BOTTOM_ISSUE_ZODIAC_URL_PARTS = {"topic/385412.html", "topic/385408.html"}


def parser_hooks() -> ParserHooks:
    return ParserHooks(
        extract_zodiac=extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=zodiac_chars,
        dedupe_zodiac=dedupe_zodiac,
    )


def parser_rule_book() -> RuleBook:
    return RuleBook(
        SPECIAL_PARSE_TARGETS,
        SPECIAL_FOLLOWUP_LABELS,
        dedicated_names=DEDICATED_BOTTOM_ISSUE_ZODIAC_NAMES,
        dedicated_url_parts=DEDICATED_BOTTOM_ISSUE_ZODIAC_URL_PARTS,
    )


def parser_registry() -> DedicatedParserRegistry:
    return DedicatedParserRegistry(parser_rule_book(), parser_hooks())


def issue_lines(text: str, issue: str, keyword: str = "") -> list[str]:
    from pingte.parse.registry import issue_lines as parse_issue_lines

    return parse_issue_lines(text, issue, keyword, parser_hooks())


def matches_keyword(line: str, keyword: str) -> bool:
    return not keyword or keyword in line


def choose_line(lines: list[str], target: Target) -> str | None:
    from pingte.parse.registry import choose_line as parse_choose_line

    return parse_choose_line(lines, target, parser_hooks())


def candidate_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parser_registry().parse_issue_lines(text, target, issue)


def has_dedicated_parser(target: Target) -> bool:
    return parser_rule_book().has_dedicated_parser(target)


def special_parse_mode(target: Target) -> str:
    return parser_rule_book().mode_for(target)


def special_parse_rule(target: Target) -> dict:
    return parser_rule_book().rule_for(target)


def special_parse_rule_matches(item: dict, target: Target) -> bool:
    return RuleBook.rule_matches(item, target)


def special_parse_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parser_registry().parse_issue_lines(text, target, issue)


def special_issue_candidates(issue: str) -> list[str]:
    return [str(int(issue))]


def special_parse_issue_lines_for_issue(text: str, target: Target, issue: str, mode: str) -> list[str]:
    return parser_registry().parse_issue_lines(text, target, issue) if mode == special_parse_mode(target) else []


def dedicated_bottom_issue_zodiac_lines(text: str, target: Target, issue: str) -> list[str]:
    return parser_registry().dedicated_bottom_issue_zodiac_lines(text, target, issue)


def is_dedicated_bottom_issue_zodiac_target(target: Target) -> bool:
    return parser_rule_book().is_dedicated_bottom(target)


def anchored_section_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_anchored.anchored_section_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def author_section_result_structure(line: str, issue: str) -> bool:
    return parsed_anchored.author_section_result_structure(line, issue)


def compact_author_result_line(line: str, issue: str, rule: dict) -> bool:
    return parsed_anchored.compact_author_result_line(line, issue, rule)


def author_section_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_anchored.author_section_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def formula_section_zodiac(line: str, issue: str, allow_question_summary: bool = False) -> str | None:
    return parsed_formula.formula_section_zodiac(line, issue, allow_question_summary)


def anchored_formula_section_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_formula.anchored_formula_section_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def target_identity_header_indexes(lines: list[str], header_indexes: list[int], target: Target) -> list[int]:
    return parsed_header.target_identity_header_indexes(lines, header_indexes, target, parser_rule_book())


def special_header_section_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_header.special_header_section_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def special_next_line_zodiac_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_header.special_next_line_zodiac_issue_lines(text, target, issue, parser_hooks())


def special_ai_public_label_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_header.special_ai_public_label_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def special_nearest_keyword_line_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_header.special_nearest_keyword_line_issue_lines(text, target, issue, parser_hooks())


def keyword_header_indexes(lines: list[str], keyword: str) -> list[int]:
    return parsed_header.keyword_header_indexes(lines, keyword, parser_hooks())


def has_ambiguous_keyword_headers(text: str, keyword: str) -> bool:
    return parsed_header.has_ambiguous_keyword_headers(text, keyword, parser_hooks())


def keyword_header_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_header.keyword_header_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def named_section_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_named.named_section_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def special_followup_issue_lines(text: str, target: Target, issue: str) -> list[str]:
    return parsed_named.special_followup_issue_lines(text, target, issue, parser_rule_book(), parser_hooks())


def _fetch_raw_uncached(url: str, timeout: int) -> str:
    return http_fetcher.fetch_raw_uncached(url, timeout, opener=urlopen, sleeper=time.sleep)


def fetch_raw(url: str, timeout: int, session: FetchSession | None = None) -> str:
    return http_fetcher.fetch_raw(url, timeout, session, loader=_fetch_raw_uncached)


def _fetch_bytes_uncached(url: str, timeout: int) -> bytes:
    return http_fetcher.fetch_bytes_uncached(url, timeout, opener=urlopen, sleeper=time.sleep)


def fetch_bytes(url: str, timeout: int, session: FetchSession | None = None) -> bytes:
    return http_fetcher.fetch_bytes(url, timeout, session, loader=_fetch_bytes_uncached)


def fetch_text(
    url: str,
    timeout: int,
    issue: str | None = None,
    visited: set[str] | None = None,
    session: FetchSession | None = None,
) -> str:
    def compat_raw(request_url: str, request_timeout: int, request_session: object) -> str:
        if request_session is None:
            return fetch_raw(request_url, request_timeout)
        return fetch_raw(request_url, request_timeout, request_session)

    def compat_bytes(request_url: str, request_timeout: int, request_session: object) -> bytes:
        if request_session is None:
            return fetch_bytes(request_url, request_timeout)
        return fetch_bytes(request_url, request_timeout, request_session)

    service = FetchService(
        targets=TARGETS,
        rules=SPECIAL_PARSE_TARGETS,
        image_targets=SPECIAL_IMAGE_TARGETS,
        raw_fetch=compat_raw,
        bytes_fetch=compat_bytes,
        image_extract=image_result.extract_issue_zodiac_from_label_image,
    )
    return service.fetch_text(url, timeout, issue, visited, session)


def browser_url_matches(requested_url: str, final_url: str) -> bool:
    return browser_fetcher.browser_url_matches(requested_url, final_url)


def retryable_browser_navigation_error(exc: Exception) -> bool:
    return browser_fetcher.retryable_browser_navigation_error(exc)


async def navigate_browser_page_with_retry(page, url: str, timeout: int) -> None:
    await browser_fetcher.navigate_browser_page_with_retry(page, url, timeout, retries=FETCH_RETRIES)


async def fetch_browser_main_text_with_retry(page, url: str, timeout: int, required_anchors: Iterable[str] = ()) -> str:
    return await browser_fetcher.fetch_browser_main_text_with_retry(
        page, url, timeout, required_anchors, retries=FETCH_RETRIES
    )


async def browser_image_dom_sections(page):
    return await browser_fetcher.browser_image_dom_sections(page)


def fetch_browser_texts(targets: Iterable[Target], timeout: int, issue: str | None = None):
    return browser_fetcher.fetch_browser_texts(
        targets,
        timeout,
        str(issue or ""),
        parser_rule_book(),
        SPECIAL_IMAGE_TARGETS,
        image_result.extract_issue_zodiac_from_label_image,
    )


def fetch_browser_text(url: str, timeout: int, target: Target) -> str:
    texts, errors = fetch_browser_texts([target], timeout)
    if url in errors:
        raise RuntimeError(errors[url])
    if url not in texts:
        raise RuntimeError("浏览器没有返回目标URL正文")
    return texts[url]


def fetch_linked_topic_text(url: str, page_html: str, timeout: int, issue: str | None, visited=None, session=None) -> str:
    return linked_topic.fetch_linked_topic_text(
        url, page_html, timeout, issue, SPECIAL_PARSE_TARGETS, fetch_text, visited, session
    )


def _dynamic_id(value: object) -> str:
    return dynamic_record.dynamic_id(value)


def _dynamic_record_candidates(data: object):
    return dynamic_record.dynamic_record_candidates(data)


def _dynamic_target_config(url: str) -> Target:
    return dynamic_record.resolve_target(url, TARGETS, SPECIAL_PARSE_TARGETS)[0]


def _dynamic_record_fields(path: str, row: dict, target: Target):
    return dynamic_record.dynamic_record_fields(path, row, target, special_parse_rule(target))


def _dynamic_user_issue_record(data: object, target: Target, issue: str):
    return dynamic_record.dynamic_user_issue_record(data, target, special_parse_rule(target), issue)


def _dynamic_forum_issue_record(data: object, target: Target, forum_id: str, issue: str):
    return dynamic_record.dynamic_forum_issue_record(data, target, special_parse_rule(target), forum_id, issue)


def _dynamic_record_text(record: dict[str, str]) -> str:
    return dynamic_record.dynamic_record_text(record)


def fetch_vue_hash_text(url: str, timeout: int, issue: str | None = None, session: FetchSession | None = None) -> str:
    return dynamic_record.fetch_vue_hash_text(
        url, timeout, issue, session, targets=TARGETS, rules=SPECIAL_PARSE_TARGETS,
        fetch_raw=lambda request_url, request_timeout, request_session: fetch_raw(
            request_url, request_timeout, request_session
        ),
    )


def exact_issue_blocks(text: str, issue: str) -> list[str]:
    return dynamic_record.exact_issue_blocks(text, issue)


def target_image_urls(page_html: str, target: Target, issue: str) -> list[str]:
    return image_resource.target_image_urls(page_html, target, issue)


def decode_data_image_uri(value: str) -> bytes | None:
    return image_resource.decode_data_image_uri(value)


def browser_image_issue_lines_from_sections(sections, targets, issue):
    return image_resource.browser_image_issue_lines_from_sections(
        sections, targets, issue,
        extract_zodiac=image_result.extract_issue_zodiac_from_label_image,
    )


decode_label_image = image_result.decode_label_image
image_component_rows = image_result.image_component_rows
red_component_rows = image_result.red_component_rows
extract_red_issue_zodiac_from_encrypted_image = image_result.extract_red_issue_zodiac_from_encrypted_image
first_image_row_colon_end = image_result.first_image_row_colon_end
image_prefix_matches_issue = image_result.image_prefix_matches_issue
extract_historical_issue_zodiac_from_image = image_result.extract_historical_issue_zodiac_from_image
extract_issue_zodiac_from_label_image = image_result.extract_issue_zodiac_from_label_image
crop_mask = image_result.crop_mask
font_paths = image_result.font_paths
rendered_text_score = image_result.rendered_text_score
match_zodiac_crop = image_result.match_zodiac_crop
cached_render_template = image_result.cached_render_template
merge_close_boxes = image_result.merge_close_boxes
bottom_line_boxes = image_result.bottom_line_boxes
render_template = image_result.render_template


def scrape_target_diagnostic(target: Target, issue: str, text: str):
    outcome = validate_documents(target, issue, text, parser_registry())
    if outcome.ok and outcome.candidate:
        return outcome.zodiac, outcome.candidate.raw_line, None
    failure = outcome.failure
    if failure and failure.code == FailureCode.TOO_MANY_ZODIACS:
        return outcome.zodiac, failure.matched_line or None, None
    if failure and failure.code in {
        FailureCode.AMBIGUOUS_CANDIDATES,
        FailureCode.SOURCE_CONFLICT,
    }:
        message = failure.message
        if message.startswith("跨文档出现多个目标候选："):
            message = message.replace(
                "跨文档出现多个目标候选：",
                "跨文档出现多个目标候选，文档边界不明确：",
                1,
            )
        return None, None, message
    return None, None, None


def scrape_target(target: Target, issue: str, text: str):
    zodiac, line, _reason = scrape_target_diagnostic(target, issue, text)
    return zodiac, line


def pending_issue_reason(text: str, target: Target, issue: str) -> str | None:
    return _pending_issue_reason(text, target, issue, parser_rule_book(), parser_hooks())


def missing_target_issue_reason(text: str, target: Target, issue: str) -> str | None:
    return _missing_target_issue_reason(text, target, issue, parser_rule_book(), parser_hooks())


def default_output_paths(issue: str):
    return _default_output_paths(issue, output_dir=OUTPUT_DIR)


def progress_percent(done: int, total: int) -> int:
    return 100 if total <= 0 else int(done * 100 / total)


def _cache_store() -> CacheStore:
    return CacheStore(RECENT_10_CACHE_PATH, RECENT_10_CACHE_WINDOW)


def update_recent_10_cache(targets: list[Target], values: dict[tuple[str, str, str, str], str], issue: str) -> bool:
    return _cache_store().update_values(targets, values, issue).ok


def load_recent_10_cache() -> dict:
    return _cache_store().load()


def cached_target_value(cache: dict, target: Target, issue: str) -> str:
    key = target_cache_key(target)
    for entry in cache.get("sites", []):
        if isinstance(entry, dict) and (
            str(entry.get("url", "")),
            str(entry.get("name", "")),
            str(entry.get("position", "")),
            str(entry.get("keyword", "")),
        ) == key:
            values = entry.get("values", {})
            return str(values.get(str(int(issue)), "")) if isinstance(values, dict) else ""
    return ""


def recent_10_cache_issue_keys(cache: dict, limit: int | None = RECENT_10_CACHE_WINDOW) -> list[str]:
    values = sorted({int(item) for item in cache.get("issues", []) if str(item).isdigit()}, reverse=True)
    return [str(item) for item in values] if limit is None else [str(item) for item in values[:limit]]


def validate_candidate_cache_latest_two(candidate_values: dict[str, str], cache: dict | None = None):
    store = _cache_store()
    if cache is not None:
        old = store.load
        store.load = lambda: cache
        try:
            outcome = store.validate_candidate_latest_two(candidate_values)
        finally:
            store.load = old
    else:
        outcome = store.validate_candidate_latest_two(candidate_values)
    return outcome.ok, (None if outcome.ok else outcome.message)


def find_recent_10_cache_duplicates(candidate_values: dict[str, str], cache: dict | None = None):
    store = _cache_store()
    if cache is None:
        selected_cache = store.load()
    else:
        selected_cache = cache
    cache_issues = {
        str(item)
        for item in selected_cache.get("issues", [])
        if str(item).isdigit()
    }
    candidate_issues = {
        str(item)
        for item, value in candidate_values.items()
        if str(item).isdigit() and str(value).strip()
    }
    if not cache_issues.intersection(candidate_issues):
        return [], "候选站没有抓到缓存中的共同有效期数，不能完成重复检测"
    if cache is None:
        return store.find_duplicates(candidate_values), None
    old = store.load
    store.load = lambda: cache
    try:
        return store.find_duplicates(candidate_values), None
    finally:
        store.load = old


def _compat_failure(item: PipelineTargetResult, issue: str) -> FailureDetail:
    if item.error:
        prefix = "浏览器DOM抓取失败" if item.used_browser else "网页抓取失败"
        return FailureDetail(
            FailureCode.WEB_FETCH_FAILED,
            f"{prefix}：{item.error}",
            item.target.target_id,
            item.target.name,
            item.target.url,
            item.target.position,
            item.target.keyword,
            str(int(issue)),
        )
    if item.outcome and item.outcome.failure:
        return item.outcome.failure
    return FailureDetail(
        FailureCode.INTERNAL_ERROR,
        "流水线没有返回校验结果",
        item.target.target_id,
        item.target.name,
        item.target.url,
        item.target.position,
        item.target.keyword,
        str(int(issue)),
    )


def run(issue: str, output: Path | None, timeout: int, update_cache: bool = True, fetch_session: FetchSession | None = None, audit: bool = False) -> int:
    def fetch_for_pipeline(url: str, request_timeout: int, request_issue: str, session: object) -> str:
        return fetch_text(url, request_timeout, request_issue, session=session if isinstance(session, FetchSession) else fetch_session)

    def browser_for_pipeline(targets: list[Target], request_timeout: int, request_issue: str):
        return fetch_browser_texts(targets, request_timeout, request_issue)

    pipeline = SitePipeline(
        TARGETS,
        parser_registry(),
        fetch_text=fetch_for_pipeline,
        fetch_browser_texts=browser_for_pipeline,
        max_workers=MAX_WORKERS,
    )
    results = pipeline.run(issue, timeout, session=fetch_session or FetchSession())
    history = load_recent_10_cache()
    successes: list[ValidatedResult] = []
    failures: list[FailureDetail] = []
    cache_conflict = False
    for item in results:
        if item.outcome and item.outcome.ok and item.outcome.result:
            cached = cached_target_value(history, item.target, issue)
            if cached and cached != item.outcome.zodiac:
                failures.append(
                    FailureDetail(
                        FailureCode.SOURCE_CONFLICT,
                        f"历史缓存同一期数据冲突：缓存{cached}，当前{item.outcome.zodiac}；历史解析错误或源站内容变更待确认",
                        item.target.target_id,
                        item.target.name,
                        item.target.url,
                        item.target.position,
                        item.target.keyword,
                        str(int(issue)),
                        item.outcome.candidate.raw_line if item.outcome.candidate else "",
                    )
                )
                cache_conflict = True
            else:
                successes.append(item.outcome.result)
        else:
            failures.append(_compat_failure(item, issue))
    success_path, default_failure = default_output_paths(issue)
    success_path = Path(output) if output is not None else success_path
    failure_path = success_path.with_suffix(".errors.txt") if output is not None else default_failure
    if update_cache and not audit and not cache_conflict:
        values = {target_cache_key(item.target): item.candidate.zodiac for item in successes}
        if not update_recent_10_cache(TARGETS, values, issue):
            failures.append(
                FailureDetail(
                    FailureCode.CACHE_UPDATE_FAILED,
                    f"recent_10_cache.json 更新失败，原缓存已保留，路径：{RECENT_10_CACHE_PATH}",
                    "",
                    "全站缓存",
                    str(RECENT_10_CACHE_PATH),
                    "",
                    "",
                    str(int(issue)),
                )
            )
    if audit:
        for failure in failures:
            print("审计失败：" + failure.render())
        print(f"审计完成：成功 {len(successes)} 条，失败 {len(failures)} 条；未写缓存或TXT。")
        return 0 if successes else 1
    atomic_write_text(success_path, build_output(f"{item.candidate.zodiac} {item.target.name}" for item in successes))
    atomic_write_text(failure_path, "\n".join(item.render() for item in failures) + ("\n" if failures else ""))
    return 0 if successes else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="旧兼容入口；正式运行请使用 run_single.py")
    parser.add_argument("issue")
    parser.add_argument("-o", "--output")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--no-cache-update", action="store_true")
    parser.add_argument("--audit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issue = args.issue.strip()
    if not re.fullmatch(r"\d{1,3}", issue):
        print("期数必须是数字，例如：164", file=sys.stderr)
        return 2
    return run(issue, Path(args.output) if args.output else None, args.timeout, not args.no_cache_update, audit=args.audit)


if __name__ == "__main__":
    raise SystemExit(main())
