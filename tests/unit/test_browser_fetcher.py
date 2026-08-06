from pingte.fetch.browser_fetcher import (
    BrowserCapture,
    BrowserFetchSpec,
    browser_url_matches,
)


def test_browser_spec_keeps_readiness_and_image_boundaries_immutable():
    spec = BrowserFetchSpec(
        url="https://example.test/topic/1.html",
        required_anchors=("目标栏目",),
        image_headers=(("目录A", "平特一肖"),),
    )

    assert spec.capture_images is True
    assert spec.required_anchors == ("目标栏目",)


def test_browser_capture_keeps_main_text_and_image_sections_separate():
    capture = BrowserCapture(
        requested_url="https://example.test/topic/1.html",
        final_url="https://example.test/topic/1.html",
        body="正文",
        image_sections=(("目录A 平特", ("data:image/png;base64,AA==",)),),
    )

    assert capture.body == "正文"
    assert capture.image_sections[0][0] == "目录A 平特"


def test_browser_url_match_requires_exact_origin_path_query_and_fragment():
    url = "https://example.test/topic/1.html?a=1#/users/2"

    assert browser_url_matches(url, url)
    assert not browser_url_matches(url, "https://example.test/topic/2.html?a=1#/users/2")
    assert not browser_url_matches(url, "https://other.test/topic/1.html?a=1#/users/2")
