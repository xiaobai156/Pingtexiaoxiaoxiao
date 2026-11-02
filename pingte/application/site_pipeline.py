from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pingte.domain.models import Target
from pingte.fetch.documents import deserialize_source_documents
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.identity import (
    target_allows_browser_dom,
    target_cache_key,
    target_requires_browser_dom,
    unique_urls,
)
from pingte.validation.result import ValidationOutcome, validate_documents

FetchText = Callable[[str, int, str, object], str]
FetchBrowserTexts = Callable[
    [list[Target], int, str], tuple[dict[str, str], dict[str, str]]
]


@dataclass(frozen=True)
class PipelineTargetResult:
    target: Target
    text: str = ""
    outcome: ValidationOutcome | None = None
    error: str = ""
    used_browser: bool = False


class SitePipeline:
    """Fetch each source once, then run exactly one dedicated validation path."""

    def __init__(
        self,
        targets: Iterable[Target],
        registry: DedicatedParserRegistry,
        *,
        fetch_text: FetchText,
        fetch_browser_texts: FetchBrowserTexts,
        max_workers: int = 8,
    ) -> None:
        self.targets = tuple(targets)
        self.registry = registry
        self.fetch_text = fetch_text
        self.fetch_browser_texts = fetch_browser_texts
        self.max_workers = max(1, max_workers)

    def _fetch_http(
        self,
        urls: list[str],
        issue: str,
        timeout: int,
        session: object,
    ) -> tuple[dict[str, str], dict[str, str]]:
        texts: dict[str, str] = {}
        errors: dict[str, str] = {}
        if not urls:
            return texts, errors
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.fetch_text, url, timeout, issue, session): url
                for url in urls
            }
            for future in as_completed(futures):
                url = futures[future]
                try:
                    texts[url] = future.result()
                except Exception as exc:
                    errors[url] = f"{type(exc).__name__}: {exc}"
        return texts, errors

    def _preliminary_outcome(
        self,
        target: Target,
        issue: str,
        text: str,
    ) -> ValidationOutcome | None:
        if not text:
            return None
        return validate_documents(target, issue, text, self.registry)

    def run(
        self,
        issue: str,
        timeout: int,
        *,
        session: object = None,
    ) -> list[PipelineTargetResult]:
        rules = self.registry.rules
        browser_preferred = [
            target
            for target in self.targets
            if (
                rules.rule_for(target).get("source_strategy") == "browser_main"
                or (
                    rules.rule_for(target).get("source_strategy")
                    == "image_resource"
                    and rules.rule_for(target).get(
                        "image_transport",
                        "browser_dom",
                    )
                    == "browser_dom"
                )
            )
        ]
        browser_preferred_keys = {
            target_cache_key(target) for target in browser_preferred
        }
        http_targets = [
            target
            for target in self.targets
            if target_cache_key(target) not in browser_preferred_keys
        ]
        http_texts, http_errors = self._fetch_http(
            unique_urls(http_targets),
            issue,
            timeout,
            session,
        )

        browser_targets = list(browser_preferred)
        preliminary: dict[tuple[str, str, str, str], ValidationOutcome | None] = {}
        for target in http_targets:
            text = http_texts.get(target.url, "")
            outcome = self._preliminary_outcome(target, issue, text)
            preliminary[target_cache_key(target)] = outcome
            conflict_reason = outcome.failure.message if outcome and outcome.failure else None
            if not text:
                if target_allows_browser_dom(target, rules):
                    browser_targets.append(target)
                continue
            if target_requires_browser_dom(
                target,
                text,
                outcome.zodiac if outcome else None,
                conflict_reason,
                rules,
                deserialize_source_documents,
            ):
                browser_targets.append(target)

        browser_texts: dict[str, str] = {}
        browser_errors: dict[str, str] = {}
        if browser_targets:
            try:
                browser_texts, browser_errors = self.fetch_browser_texts(
                    browser_targets,
                    timeout,
                    issue,
                )
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                browser_errors = {
                    url: reason for url in unique_urls(browser_targets)
                }

        browser_keys = {
            target_cache_key(target) for target in browser_targets
        }
        results: list[PipelineTargetResult] = []
        for target in self.targets:
            key = target_cache_key(target)
            use_browser = key in browser_keys
            text = browser_texts.get(target.url, "") if use_browser else http_texts.get(target.url, "")
            if not text:
                error = (
                    browser_errors.get(target.url)
                    or http_errors.get(target.url)
                    or "没有返回正文"
                )
                results.append(
                    PipelineTargetResult(
                        target=target,
                        error=error,
                        used_browser=use_browser,
                    )
                )
                continue
            results.append(
                PipelineTargetResult(
                    target=target,
                    text=text,
                    outcome=validate_documents(target, issue, text, self.registry),
                    used_browser=use_browser,
                )
            )
        return results
