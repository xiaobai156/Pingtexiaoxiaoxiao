from __future__ import annotations

from pingte.application.site_pipeline import SitePipeline
from pingte.domain.models import SourceDocument, Target
from pingte.fetch.documents import serialize_source_documents
from pingte.parse.context import ParserHooks, RuleBook
from pingte.parse.registry import DedicatedParserRegistry
from pingte.validation.issue import extract_target_zodiac, extract_zodiac


def make_target(name: str, url: str = "https://example.test/topic/1.html") -> Target:
    return Target(url, "top", name, "成语平特", f"PT-{name}", 1)


def make_pipeline(targets: list[Target], browser_targets: set[str] | None = None):
    browser_targets = browser_targets or set()
    rules = [
        {
            "target_id": target.target_id,
            "url_contains": target.url,
            "position": target.position,
            "name": target.name,
            "keyword": target.keyword,
            "mode": "nearest_keyword_line",
            "source_strategy": "browser_main" if target.name in browser_targets else "http_main",
        }
        for target in targets
    ]
    hooks = ParserHooks(
        extract_zodiac=extract_zodiac,
        extract_target_zodiac=extract_target_zodiac,
        zodiac_chars=lambda value: value,
        dedupe_zodiac=lambda value: value,
    )
    registry = DedicatedParserRegistry(
        RuleBook(rules, {}, dedicated_names=(), dedicated_url_parts=()),
        hooks,
    )
    return registry


def document(target: Target, zodiac: str) -> str:
    return serialize_source_documents(
        [
            SourceDocument(
                "http-main",
                target.url,
                True,
                f"{target.name}\n成语平特\n164期成语平特【{zodiac}】开00准",
            )
        ]
    )


def test_pipeline_fetches_each_http_url_once_and_validates_each_target():
    targets = [make_target("目录A"), make_target("目录B")]
    calls: list[tuple[str, str]] = []

    def fetch_text(url, timeout, issue, session):
        calls.append(("http", url))
        return document(targets[0 if url.endswith("1.html") else 1], "鼠")

    def fetch_browser(_targets, _timeout, _issue):
        raise AssertionError("http success should not need browser")

    pipeline = SitePipeline(
        targets,
        make_pipeline(targets),
        fetch_text=fetch_text,
        fetch_browser_texts=fetch_browser,
        max_workers=2,
    )

    results = pipeline.run("164", 5)

    assert len(calls) == 1
    assert all(result.outcome.ok for result in results)
    assert {result.outcome.zodiac for result in results} == {"鼠"}


def test_pipeline_uses_browser_for_browser_only_target():
    target = make_target("浏览器目录")
    calls: list[str] = []

    def fetch_text(*_args):
        calls.append("http")
        raise AssertionError("browser-only target must not use HTTP")

    def fetch_browser(targets, _timeout, _issue):
        calls.append("browser")
        return {target.url: document(target, "牛")}, {}

    pipeline = SitePipeline(
        [target],
        make_pipeline([target], {target.name}),
        fetch_text=fetch_text,
        fetch_browser_texts=fetch_browser,
    )

    results = pipeline.run("164", 5)

    assert calls == ["browser"]
    assert results[0].outcome.ok
    assert results[0].outcome.zodiac == "牛"


def test_pipeline_keeps_fetch_error_separate_from_parser_failure():
    target = make_target("失败目录")

    def fetch_text(*_args):
        raise ConnectionError("closed")

    pipeline = SitePipeline(
        [target],
        make_pipeline([target]),
        fetch_text=fetch_text,
        fetch_browser_texts=lambda *_args: ({}, {}),
    )

    result = pipeline.run("164", 5)[0]

    assert result.text == ""
    assert result.error.startswith("ConnectionError: closed")
    assert result.outcome is None
