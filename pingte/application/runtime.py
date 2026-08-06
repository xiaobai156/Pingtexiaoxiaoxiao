from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pingte.config.loader import load_compiled_config, load_targets
from pingte.domain.models import Target
from pingte.fetch import browser_fetcher, http_fetcher
from pingte.fetch.service import FetchService
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.custom.image_result import extract_issue_zodiac_from_label_image
from pingte.parse.registry import DedicatedParserRegistry
from pingte.storage.cache import CacheStore
from pingte.validation.issue import (
    dedupe_zodiac,
    extract_target_zodiac,
    strict_extract_zodiac,
    zodiac_chars,
)

from .single_issue import SingleIssueRunner
from .site_pipeline import SitePipeline


DEFAULT_OUTPUT_DIR = Path(
    r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\大围杀号生肖数据统一归纳"
)


@dataclass(frozen=True)
class Runtime:
    project_dir: Path
    targets: tuple[Target, ...]
    registry: DedicatedParserRegistry
    pipeline: SitePipeline
    cache_store: CacheStore
    output_dir: Path
    evidence_dir: Path

    def single_runner(self, *, log: Callable[[str], None] | None = None) -> SingleIssueRunner:
        return SingleIssueRunner(
            self.targets,
            self.pipeline,
            cache_store=self.cache_store,
            output_dir=self.output_dir,
            evidence_dir=self.evidence_dir,
            log=log,
        )


def _contains_map(config: dict, key: str, value_key: str) -> dict[str, str]:
    return {
        str(item["url_contains"]): str(item[value_key])
        for item in config.get(key, [])
        if isinstance(item, dict) and item.get("url_contains") and item.get(value_key)
    }


def _build_registry(config: dict, targets: list[Target]) -> tuple[DedicatedParserRegistry, dict[str, str]]:
    rules = config.get("special_parse_targets", [])
    followup_labels = _contains_map(config, "special_followup_labels", "label")
    rule_book = RuleBook(
        rules,
        followup_labels,
        dedicated_names={"赌神平特", "小白平特"},
        dedicated_url_parts={"topic/385412.html", "topic/385408.html"},
    )
    hooks = ParserHooks(
        extract_zodiac=strict_extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=zodiac_chars,
        dedupe_zodiac=dedupe_zodiac,
    )
    return DedicatedParserRegistry(rule_book, hooks), _contains_map(
        config,
        "special_image_targets",
        "name",
    )


def build_runtime(
    project_dir: Path,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    evidence_dir: Path | None = None,
    cache_path: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> Runtime:
    project_dir = Path(project_dir)
    config = load_compiled_config(project_dir / "targets.json")
    targets = load_targets(config)
    registry, image_targets = _build_registry(config, targets)

    def raw_fetch(url: str, timeout: int, session: object) -> str:
        return http_fetcher.fetch_raw(url, timeout, session)

    def bytes_fetch(url: str, timeout: int, session: object) -> bytes:
        return http_fetcher.fetch_bytes(url, timeout, session)

    fetch_service = FetchService(
        targets=targets,
        rules=config["special_parse_targets"],
        image_targets=image_targets,
        raw_fetch=raw_fetch,
        bytes_fetch=bytes_fetch,
        image_extract=extract_issue_zodiac_from_label_image,
    )

    def fetch_text(url: str, timeout: int, issue: str, session: object) -> str:
        return fetch_service.fetch_text(url, timeout, issue, session=session)

    def fetch_browser_texts(target_list, timeout: int, issue: str):
        return browser_fetcher.fetch_browser_texts(
            target_list,
            timeout,
            issue,
            registry.rules,
            image_targets,
            extract_issue_zodiac_from_label_image,
            progress=_browser_progress,
        )

    pipeline = SitePipeline(
        targets,
        registry,
        fetch_text=fetch_text,
        fetch_browser_texts=fetch_browser_texts,
        max_workers=8,
    )
    return Runtime(
        project_dir=project_dir,
        targets=tuple(targets),
        registry=registry,
        pipeline=pipeline,
        cache_store=CacheStore(cache_path or project_dir / "recent_10_cache.json"),
        output_dir=Path(output_dir),
        evidence_dir=Path(evidence_dir or project_dir / "evidence"),
    )


def _browser_progress(
    completed: int,
    total: int,
    succeeded: int,
    failed: int,
    started_at: float,
    url: str,
) -> None:
    import time

    elapsed = time.monotonic() - started_at
    print(
        f"[浏览器 {completed}/{total} 成功 {succeeded} 失败 {failed} "
        f"用时 {elapsed:.1f}s] 当前：{url}",
        flush=True,
    )
