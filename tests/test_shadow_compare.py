from pingte.application.shadow import ShadowCase, compare_parsers


def test_shadow_compare_passes_the_same_document_to_both_parsers():
    document = "211期:平特一肖【虎】开00准"
    calls = []

    def legacy_parser(target, issue, text):
        calls.append(("legacy", target, issue, id(text)))
        return "虎", text, None

    def candidate_parser(target, issue, text):
        calls.append(("candidate", target, issue, id(text)))
        return "虎", text, None

    differences = compare_parsers(
        [ShadowCase("case-1", "target-A", "211", document)],
        legacy_parser,
        candidate_parser,
    )

    assert differences == []
    assert calls == [
        ("legacy", "target-A", "211", id(document)),
        ("candidate", "target-A", "211", id(document)),
    ]


def test_shadow_compare_reports_exact_old_and_new_results():
    case = ShadowCase("case-2", "target-B", "211", "same source document")

    differences = compare_parsers(
        [case],
        lambda *_args: ("虎", "old line", None),
        lambda *_args: ("牛", "new line", None),
    )

    assert len(differences) == 1
    assert differences[0].case_id == "case-2"
    assert differences[0].issue == "211"
    assert differences[0].legacy_result == ("虎", "old line", None)
    assert differences[0].candidate_result == ("牛", "new line", None)
