import hashlib
from datetime import datetime

from pingte.domain.models import SourceDocument
from pingte.fetch.documents import (
    deserialize_source_documents,
    make_source_document,
    serialize_source_documents,
)
from pingte.fetch.http_fetcher import FetchSession
from pingte.fetch.image_resource import target_image_urls
from pingte.domain.models import TargetProfile


def test_source_document_factory_records_hash_and_timestamp():
    document = make_source_document(
        source="http-main",
        source_url="https://example.test/topic/1.html",
        primary=True,
        text="211期平特一肖【牛】",
        fetched_at="2026-07-30T23:30:00+08:00",
    )

    assert document.sha256 == hashlib.sha256(
        document.text.encode("utf-8")
    ).hexdigest()
    assert datetime.fromisoformat(document.fetched_at).utcoffset() is not None


def test_document_serialization_preserves_provenance_fields():
    document = SourceDocument(
        source="browser-main",
        source_url="https://example.test/final",
        primary=True,
        text="211期成语平特【鸡飞狗跳】",
        sha256="abc123",
        fetched_at="2026-07-30T23:31:00+08:00",
    )

    restored = deserialize_source_documents(serialize_source_documents([document]))

    assert restored == [document]


def test_document_serialization_keeps_documents_independent_and_deduplicated():
    primary = make_source_document("http-main", "https://x", True, "当前正文")
    historical = make_source_document("page-decoded:0", "https://x", False, "旧文档")

    restored = deserialize_source_documents(
        serialize_source_documents([primary, historical, historical])
    )

    assert [item.source for item in restored] == ["http-main", "page-decoded:0"]
    assert [item.text for item in restored] == ["当前正文", "旧文档"]


def test_document_serialization_preserves_distinct_document_ids():
    first = make_source_document(
        "dynamic-api-record",
        "https://x",
        True,
        "同一正文",
        document_id="100",
    )
    second = make_source_document(
        "dynamic-api-record",
        "https://x",
        True,
        "同一正文",
        document_id="101",
    )

    restored = deserialize_source_documents(
        serialize_source_documents([first, second])
    )

    assert [item.document_id for item in restored] == ["100", "101"]


def test_image_source_rejects_duplicate_target_title_blocks():
    target = TargetProfile(
        "https://example.test/topic/1.html",
        "tail",
        "赌神平特",
        "赌神平特",
    )
    page = (
        '<div class="detail_info_forum2_item">'
        '<div class="forum-head">赌神平特</div>'
        '<div class="forum-body"><div class="content">'
        '<img src="a.png"></div></div></div>'
        '<div class="detail_info_forum2_item">'
        '<div class="forum-head">赌神平特</div>'
        '<div class="forum-body"><div class="content">'
        '<img src="b.png"></div></div></div>'
    )

    try:
        target_image_urls(page, target, "164")
    except RuntimeError as exc:
        assert "不唯一" in str(exc)
    else:
        raise AssertionError("重复目标图片区块必须失败")


def test_fetch_session_canonical_url_excludes_fragment_only():
    assert FetchSession.canonical_url("https://x/a?q=1#/users/2") == "https://x/a?q=1"
