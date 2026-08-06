from __future__ import annotations

from pingte.domain.models import Target
from pingte.fetch import browser_fetcher
from pingte.fetch.documents import deserialize_source_documents
from pingte.parse.context import RuleBook


def test_browser_texts_keeps_main_document_independent(monkeypatch):
    target = Target("https://example.test/topic/1.html", "top", "目录A", "成语平特", "PT-A", 1)

    monkeypatch.setattr(
        browser_fetcher,
        "fetch_browser_captures",
        lambda *_args, **_kwargs: (
            {
                target.url: browser_fetcher.BrowserCapture(
                    target.url,
                    target.url,
                    "164期成语平特【鼠】开00准",
                )
            },
            {},
        ),
    )

    texts, errors = browser_fetcher.fetch_browser_texts(
        [target],
        5,
        "164",
        RuleBook(
            [
                {
                    "target_id": "PT-A",
                    "url_contains": target.url,
                    "name": target.name,
                    "position": target.position,
                    "keyword": target.keyword,
                    "source_strategy": "browser_main",
                }
            ],
            {},
            dedicated_names=(),
            dedicated_url_parts=(),
        ),
        {},
        lambda *_args: None,
    )

    assert not errors
    documents = deserialize_source_documents(texts[target.url])
    assert len(documents) == 1
    assert documents[0].source == "browser-main"
    assert documents[0].primary
