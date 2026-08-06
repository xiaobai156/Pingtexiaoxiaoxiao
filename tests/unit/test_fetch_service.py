from pingte.domain.models import TargetProfile
from pingte.fetch.documents import deserialize_source_documents
from pingte.fetch.service import FetchService


def test_fetch_service_keeps_current_and_decoded_documents_separate():
    encoded = "PGRpdj7ml6fmlofmoaM8L2Rpdj4="
    page = (
        "<div>当前正文</div>"
        f'<script>document.writeln(strdecode("{encoded}"));</script>'
    )
    service = FetchService(
        targets=(),
        rules=(),
        image_targets={},
        raw_fetch=lambda _url, _timeout, _session: page,
        bytes_fetch=lambda *_args: b"",
        image_extract=lambda *_args: None,
    )

    documents = deserialize_source_documents(
        service.fetch_text("https://example.test/topic/1.html", 1, "211")
    )

    assert [document.source for document in documents] == [
        "http-main",
        "page-decoded:0",
    ]
    assert documents[0].text == "当前正文"
    assert documents[1].text == "旧文档"


def test_fetch_service_rejects_recursive_linked_document_loop():
    target = TargetProfile(
        "https://example.test/topic/1.html",
        "top",
        "目录A",
        "三字平特",
        target_id="PT-0001",
    )
    service = FetchService(
        targets=(target,),
        rules=(
            {
                "target_id": "PT-0001",
                "url_contains": target.url,
                "name": target.name,
                "position": target.position,
                "keyword": target.keyword,
                "mode": "linked_topic",
            },
        ),
        image_targets={},
        raw_fetch=lambda *_args: (
            "<a href='/topic/1.html'>211期 目录A 三字平特</a>"
        ),
        bytes_fetch=lambda *_args: b"",
        image_extract=lambda *_args: None,
    )

    try:
        service.fetch_text(target.url, 1, "211")
    except RuntimeError as exc:
        assert "关联正文循环" in str(exc)
    else:
        raise AssertionError("循环关联正文必须失败")
