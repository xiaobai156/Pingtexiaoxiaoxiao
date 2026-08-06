import asyncio
import base64
import json
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from datetime import date
from urllib.error import HTTPError

import pytest
from tests.compat import zodiac_multi, zodiac_scraper
from tests.compat.zodiac_scraper import (
    Target,
    build_output,
    extract_zodiac,
    html_to_text,
    issue_lines,
    scrape_target,
    scrape_target_diagnostic,
    unavailable_reason,
)


def strict_special_rule(target: Target, mode: str) -> dict[str, str]:
    data_structures = {
        "header_section": "confirmed_result_line",
        "followup_label": "label_followup_result",
        "next_line_zodiac": "issue_following_result",
        "nearest_keyword_line": "exact_keyword_result_line",
        "linked_topic": "linked_topic_result",
        "named_section": "confirmed_result_line",
        "ai_public_label": "public_label_followup_result",
        "anchored_section": "confirmed_result_line",
        "anchored_formula_section": "terminal_formula_result",
        "author_section": "confirmed_result_line",
    }
    boundaries = {
        "header_section": "target_header_section",
        "followup_label": "issue_followup_block",
        "next_line_zodiac": "issue_followup_block",
        "nearest_keyword_line": "single_exact_line",
        "linked_topic": "linked_record",
        "named_section": "target_name_section",
        "ai_public_label": "public_label_block",
        "anchored_section": "explicit_anchors",
        "anchored_formula_section": "explicit_anchors",
        "author_section": "explicit_anchors",
    }
    return {
        "url_contains": target.url,
        "name": target.name,
        "position": target.position,
        "keyword": target.keyword,
        "mode": mode,
        "issue_format": "arabic_issue_exact",
        "data_structure": data_structures[mode],
        "section_boundary": boundaries[mode],
        "source_strategy": "http_main",
    }


def test_main_forwards_manual_issue_and_runtime_flags(monkeypatch, tmp_path):
    output = tmp_path / "result.txt"
    calls = []

    def fake_run(issue, output_path, timeout, update_cache, audit):
        calls.append((issue, output_path, timeout, update_cache, audit))
        return 0

    monkeypatch.setattr(zodiac_scraper, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "zodiac_scraper.py",
            "211",
            "--timeout",
            "9",
            "--no-cache-update",
            "--audit",
            "--output",
            str(output),
        ],
    )

    assert zodiac_scraper.main() == 0
    assert calls == [("211", output, 9, False, True)]


def test_main_rejects_non_numeric_manual_issue(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["zodiac_scraper.py", "21x"])

    assert zodiac_scraper.main() == 2
    assert "期数必须是数字" in capsys.readouterr().err


def test_date_label_uses_month_dot_day_without_year():
    assert zodiac_scraper.date_label(date(2026, 6, 15)) == "6.15"


def test_extracts_zodiac_from_brackets_before_open_result():
    line = "163期:成语平特【蛇形走位】开马37错"

    assert extract_zodiac(line) == "蛇"


def test_extracts_multiple_zodiacs_from_idiom():
    line = "164期四字平特『当牛做马』开？00准 牛马"

    assert extract_zodiac(line) == "牛马"


def test_extracts_tail_equals_style():
    line = "163期39-08-10-33-07-41T37+01=牛√"

    assert extract_zodiac(line) == "牛"


def test_extracts_all_zodiacs_after_equals_with_status_marks():
    line = "200期43-46-05-32-35-29T39 +02.03=羊×猪√"

    assert extract_zodiac(line) == "羊猪"


def test_extracts_zodiac_from_open_number_when_no_zodiac_text():
    line = "165期:平特一肖开:02准"

    assert extract_zodiac(line) == "蛇"


def test_extracts_zodiac_without_repeated_animals():
    line = "164期 平特一肖【马马虎虎】开000准"

    assert extract_zodiac(line) == "马虎"


def test_does_not_extract_from_long_description_text():
    line = "164期【AI平特肖】 站长宣言：本网站绝不参假，如遇马后炮资料直接封号。"

    assert extract_zodiac(line) is None


def test_does_not_extract_zodiac_from_disclaimer_with_open_word():
    line = "164期【AI平特肖】站长宣言：本网站绝不参假如遇马后炮资料直接封号开000中"

    assert extract_zodiac(line) is None


def test_filters_by_keyword_for_same_page_modules():
    text = "\n".join(
        [
            "164期:平特一肖【狗狗狗】开000中",
            "164期:成语平特【牛鬼蛇神】开000准",
            "164期谜语平特-红娘过桥狗鸡随-开? 00准",
        ]
    )

    target = Target("x", "top", "智能成语", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "nearest_keyword_line")]
    try:
        zodiac, _line = scrape_target(target, "164", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "牛蛇"


def test_rejects_zodiac_line_without_exact_keyword():
    text = "\n".join(
        [
            "164期:成语平特 等待更新",
            "164期:平特一肖【狗狗狗】开000中",
        ]
    )

    zodiac, line = scrape_target(Target("x", "top", "智能成语", "成语平特"), "164", text)

    assert zodiac is None
    assert line is None


def test_tail_rejects_different_same_issue_keyword_candidates():
    text = "\n".join(
        [
            "164期:成语平特【牛牛牛】开000准",
            "164期:平特一肖【狗狗狗】开000中",
            "164期:成语平特【蛇蛇蛇】开000准",
        ]
    )

    target = Target("x", "tail", "测试目录", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        zodiac, line = scrape_target(target, "164", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_tail_rejects_different_same_issue_candidates_without_keyword():
    text = "\n".join(
        [
            "164期:平特一肖【狗狗狗】开000中",
            "164期36-43-25-32-37-18T05+01=鼠√",
        ]
    )

    target = Target("x", "tail", "熊出没", "")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        zodiac, _line = scrape_target(target, "164", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None


def test_skips_title_line_without_zodiac():
    text = "\n".join(
        [
            "平特帖164期:【成语平特】 作者:突然发大",
            "164期成语平特【鸡飞狗跳】开000准",
        ]
    )

    target = Target("x", "top", "突然发大", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        zodiac, _line = scrape_target(target, "164", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "鸡狗"


def test_ai_followup_label_extracts_next_line_for_special_url():
    text = "\n".join(
        [
            "164期【AI推荐平特】开？00中",
            "平特一肖：鸡鸡鸡",
            "平特1尾：000尾",
            "163期【AI推荐平特】开鼠07龙39中",
            "平特一肖：鼠鼠鼠",
        ]
    )

    target = Target("https://x/topic/654833.html", "top", "AI平特肖", "AI推荐平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    old_labels = zodiac_scraper.SPECIAL_FOLLOWUP_LABELS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "followup_label")]
    zodiac_scraper.SPECIAL_FOLLOWUP_LABELS = {target.url: "平特一肖"}
    try:
        zodiac, _line = scrape_target(target, "164", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old
        zodiac_scraper.SPECIAL_FOLLOWUP_LABELS = old_labels

    assert zodiac == "鸡"


def test_one_zodiac_keyword_is_not_rejected_as_many_zodiac_noise():
    target = Target("https://x", "top", "平特一肖", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "nearest_keyword_line")]
    try:
        text = "183期：(平特一肖)牛牛牛"
        zodiac, line = scrape_target(target, "183", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "牛"
    assert line == "183期：(平特一肖)牛牛牛"


def test_ai_public_label_binds_to_public_block_not_direct_keyword_line():
    old_targets = zodiac_scraper.SPECIAL_PARSE_TARGETS
    target = Target("https://x", "top", "智能平特", "平特一肖")
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        strict_special_rule(target, "ai_public_label")
    ]
    try:
        text = "\n".join(
            [
                "183期:平特一肖【狗狗狗】开000中",
                "AAAAA级大公开183期",
                "站长宣言：如遇马后炮资料直接封号",
                "平特一肖 ：猪猪猪",
                "AAAAA级大公开182期",
                "平特一肖 ：鸡鸡鸡",
            ]
        )
        zodiac, line = scrape_target(target, "183", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_targets

    assert zodiac == "猪"
    assert line == "AAAAA级大公开183期 平特一肖 ：猪猪猪"


def test_named_section_prefers_keyword_line_over_other_issue_lines():
    text = "\n".join(
        [
            "水果奶奶【一肖一码】",
            "165期:必中⑥肖：【鸡鼠猴蛇龙猪】",
            "水果奶奶【平特一肖】",
            "165期 平特一肖：【鸡鸡鸡】开 ?? 准",
        ]
    )

    target = Target("https://aa.828797a.com:1888/", "top", "水果奶奶", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        zodiac, line = scrape_target(target, "165", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "鸡"
    assert "平特一肖" in line


def test_named_section_rejects_issue_line_when_only_header_has_keyword():
    text = "\n".join(
        [
            "167期:墨言笙歌【平特一肖】独家公式",
            "167期：20-15-01-04-21-28T06+0=兔√",
            "166期：20-15-01-04-21-28T06+0=兔√",
        ]
    )

    zodiac, line = scrape_target(Target("x", "tail", "墨言笙歌", "平特一肖"), "166", text)

    assert zodiac is None
    assert line is None


def test_direct_keyword_matches_honor_tail_position():
    text = "\n".join(
        [
            "尾部样例【平特一尾】",
            "166期 平特一尾 20-15-01-04-21-28 T06 +1=蛇√",
            "尾部样例【平特一尾】",
            "166期 平特一尾 20-15-01-04-21-28 T06 +5=马√",
        ]
    )

    target = Target("x", "tail", "尾部样例", "平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        zodiac, line = scrape_target(target, "166", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_keyword_header_section_rejects_lines_without_precise_keyword():
    text = "\n".join(
        [
            "168期【公式平特】规律",
            "166期 20-15-01-04-21-28 T06 +5=猪×",
            "167期 23-03-40-39-07-11 T19 +5=兔√",
            "168期 平特猪猪猪肖？",
        ]
    )

    zodiac, line = scrape_target(Target("x", "tail", "熊出没公平", "公式平特"), "167", text)

    assert zodiac is None
    assert line is None


def test_keyword_header_section_does_not_use_other_issue():
    text = "\n".join(
        [
            "168期【公式平特】规律",
            "168期 平特猪猪猪肖？",
        ]
    )

    zodiac, line = scrape_target(Target("x", "tail", "熊出没公平", "公式平特"), "167", text)

    assert zodiac is None
    assert line is None


def test_named_section_does_not_cross_to_previous_section():
    text = "\n".join(
        [
            "六合彩宝典【四字平特】",
            "165期:四字平特【蛇形走位】开马37错",
            "164期:四字平特【当牛做马】开00准",
            "163期:四字平特【龙飞凤舞】开00准",
            "鬼使神差【四字平特】",
            "165期:四字平特【鸡飞狗跳】开00准",
            "164期:四字平特【虎头蛇尾】开00准",
        ]
    )

    target = Target("x", "top", "鬼使神差", "四字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        zodiac, line = scrape_target(target, "163", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_keyword_header_section_uses_matching_named_block_only():
    text = "\n".join(
        [
            "六合彩宝典【四字平特】",
            "165期:四字平特【蛇形走位】开马37错",
            "164期:四字平特【当牛做马】开00准",
            "163期:四字平特【龙飞凤舞】开00准",
            "鬼使神差【四字平特】",
            "165期:四字平特【鸡飞狗跳】开00准",
            "164期:四字平特【虎头蛇尾】开00准",
        ]
    )

    target = Target("x", "top", "鬼使神差", "四字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        zodiac, line = scrape_target(target, "164", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "虎蛇"
    assert line.endswith("【虎头蛇尾】开00准")


def test_named_section_rejects_non_keyword_many_zodiac_issue_line():
    text = "\n".join(
        [
            "爱莫能助【成语平特】",
            "169期⑨肖【虎猴羊狗鸡龙蛇兔马】√",
            "169期：成语平特《蛇鼠一窝》开00准",
        ]
    )

    target = Target("x", "tail", "爱莫能助", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        zodiac, line = scrape_target(target, "169", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "蛇鼠"
    assert "成语平特" in line


def test_same_url_anchored_columns_use_independent_boundaries_and_directions():
    text = "\n".join(
        [
            "『成语平特』",
            "201期成語爆平特【马马虎虎】開？00准",
            "『原创七尾』",
            "『规律二肖』",
            "200期03-37-24-10-41-19T39 +09.03=鼠√猪√",
            "201期平特一肖 虎牛肖",
            "『百马禁一肖』",
            "『谜语平特』",
            "201期(谜语平特)(龙蛇飞动)开：0000准",
            "『家野主三肖』",
            "『成语平特』",
            "201期成語爆平特【牛羊成群】開羊12准",
            "『原创七尾』",
            "『规律二肖』",
            "200期43-46-05-32-35-29T39 +09.07=虎√牛√",
            "201期平特一肖 猴鸡肖",
            "『百马禁一肖』",
            "『谜语平特』",
            "201期(谜语平特)(羊入虎口)开：羊24准",
            "『家野主三肖』",
        ]
    )
    targets = [
        Target("https://same.example/", "top", "平特一肖成语平特", "成语平特"),
        Target("https://same.example/", "tail", "平特一肖规律二肖", "规律二肖"),
        Target("https://same.example/", "top", "平特一肖谜语平特", "谜语平特"),
    ]
    rules = [
        {
            "url_contains": "https://same.example/",
            "name": targets[0].name,
            "position": targets[0].position,
            "keyword": targets[0].keyword,
            "mode": "anchored_section",
            "section_anchor": "『成语平特』",
            "section_end": "『原创七尾』",
            "line_keyword": "成語爆平特",
        },
        {
            "url_contains": "https://same.example/",
            "name": targets[1].name,
            "position": targets[1].position,
            "keyword": targets[1].keyword,
            "mode": "anchored_formula_section",
            "section_anchor": "『规律二肖』",
            "section_end": "『百马禁一肖』",
        },
        {
            "url_contains": "https://same.example/",
            "name": targets[2].name,
            "position": targets[2].position,
            "keyword": targets[2].keyword,
            "mode": "anchored_section",
            "section_anchor": "『谜语平特』",
            "section_end": "『家野主三肖』",
        },
    ]
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = rules
    try:
        assert scrape_target(targets[0], "201", text) == (None, None)
        assert scrape_target(targets[1], "200", text) == (None, None)
        assert scrape_target(targets[2], "201", text) == (None, None)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_anchored_formula_section_rejects_other_section_and_missing_issue():
    target = Target("https://same.example/", "tail", "平特一肖规律二肖", "规律二肖")
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        {
            "url_contains": "https://same.example/",
            "name": target.name,
            "position": target.position,
            "keyword": target.keyword,
            "mode": "anchored_formula_section",
            "section_anchor": "『规律二肖』",
            "section_end": "『百马禁一肖』",
        }
    ]
    text = "\n".join(
        [
            "『规律一肖』",
            "202期公式=鼠√猪√",
            "『单双中特』",
            "『规律二肖』",
            "200期43-46-05-32-35-29T39 +09.07=虎√牛√",
            "『百马禁一肖』",
        ]
    )
    try:
        assert scrape_target(target, "200", text)[0] == "虎牛"
        assert scrape_target(target, "199", text) == (None, None)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_anchored_formula_section_rejects_pending_question_summary():
    target = Target("https://formula.example/topic/1.html", "tail", "公式目录", "公式平特")
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        {
            "url_contains": target.url,
            "name": target.name,
            "position": target.position,
            "keyword": target.keyword,
            "mode": "anchored_formula_section",
            "section_anchor": "【公式平特】",
            "section_end": "站长宣言",
        }
    ]
    text = "\n".join(
        [
            "201期:【公式平特】",
            "200期 43-46-05-32-35-29 T39=虎√",
            "201期 平特一肖虎肖？",
            "站长宣言",
        ]
    )
    try:
        assert scrape_target(target, "200", text)[0] == "虎"
        assert scrape_target(target, "201", text) == (None, None)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_anchored_formula_section_allows_question_summary_only_when_explicitly_enabled():
    target = Target("https://formula.example/topic/question.html", "tail", "公式目录", "公式平特")
    text = "\n".join(
        [
            "203期【公式平特】规律",
            "203期 平特兔兔兔肖？",
            "站长宣言",
        ]
    )
    base_rule = {
        "url_contains": target.url,
        "name": target.name,
        "position": target.position,
        "keyword": target.keyword,
        "mode": "anchored_formula_section",
        "section_anchor": "【公式平特】",
        "section_end": "站长宣言",
    }
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    try:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = [base_rule]
        assert scrape_target(target, "203", text) == (None, None)

        zodiac_scraper.SPECIAL_PARSE_TARGETS = [
            {**base_rule, "allow_question_summary": True}
        ]
        assert scrape_target(target, "203", text) == ("兔", "203期 平特兔兔兔肖？")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_anchored_section_uses_requested_issue_as_exact_end_boundary():
    target = Target("https://example.test/topic/203.html", "tail", "五彩缤纷", "一肖平特")
    rule = {
        **strict_special_rule(target, "anchored_section"),
        "section_anchor": "作者:五彩缤纷",
        "section_end": "{issue}期",
        "section_anchor_exact": True,
        "section_end_exact": True,
        "line_keyword": "一肖平特",
    }
    text = "\n".join(
        [
            "高手帖 203期〖平特一肖〗",
            "作者:五彩缤纷",
            "202期一肖平特《狗狗狗》开45准",
            "203期一肖平特《猪猪猪》开00准",
            "203期",
            "旧文档 203期一肖平特《马马马》开00准",
        ]
    )
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        assert scrape_target_diagnostic(target, "203", text) == (
            "猪",
            "203期一肖平特《猪猪猪》开00准",
            None,
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_anchored_formula_section_can_bind_first_header_for_tail_data_direction():
    target = Target("https://example.test/topic/repeated.html", "tail", "锦离鸢墨", "平特一肖")
    rule = {
        **strict_special_rule(target, "anchored_formula_section"),
        "section_anchor": "锦离鸢墨【平特一肖】独家公式",
        "section_end": "★★ 博彩必备★★",
        "section_anchor_position": "first",
    }
    text = "\n".join(
        [
            "203期:锦离鸢墨【平特一肖】独家公式",
            "203期 平特马肖",
            "★★ 博彩必备★★",
            "203期:锦离鸢墨【平特一肖】独家公式",
            "203期 平特猪肖",
            "★★ 博彩必备★★",
        ]
    )
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        assert scrape_target_diagnostic(target, "203", text) == (
            None,
            None,
            "同一目标文档出现不同生肖候选：马、猪",
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_anchored_section_exposes_explicit_many_zodiac_candidate_for_rejection():
    target = Target("https://example.test/topic/five.html", "top", "锦绣前程", "平特一肖")
    rule = {
        **strict_special_rule(target, "anchored_section"),
        "section_anchor": "锦绣前程【平特五肖】已公开",
        "section_end": "站长宣言:",
        "line_keyword": "平特五肖",
        "allow_many_zodiac_candidate": True,
    }
    text = "\n".join(
        [
            "203期：锦绣前程【平特五肖】已公开",
            "203期【平特五肖】【兔猪狗羊马】开00准",
            "站长宣言:本网站绝不带一丝参假料",
        ]
    )
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        assert scrape_target_diagnostic(target, "203", text) == (
            "兔猪狗羊马",
            "203期【平特五肖】【兔猪狗羊马】开00准",
            None,
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


@pytest.mark.parametrize(
    ("name", "expected", "text"),
    [
        (
            "千秋万代",
            ("龙马", "203期♥四字平特☄《龙马精神》开：37.25.03中"),
            "\n".join(
                [
                    "千秋万代 发表于 07月23日 00:00:06",
                    "202期♥四字平特☄《马到成功》开：25.13中",
                    "203期♥四字平特☄《龙马精神》开：37.25.03中",
                    "鸿蒙娱乐城",
                    "203期♥四字平特☄《猪狗不如》开：00中",
                ]
            ),
        ),
        (
            "光辉岁月",
            ("猪猴", "203期平特二肖：（猪猴）开:11.44准↑"),
            "\n".join(
                [
                    "光辉岁月 发表于 07月23日 00:00:06",
                    "203期平特二肖：（猪猴）开:11.44准↑",
                    "202期平特二肖：（鸡马）开:25.13准↑",
                    "鸿蒙娱乐城",
                    "203期平特二肖：（牛狗）开:00准↑",
                ]
            ),
        ),
    ],
)
def test_new_candidates_use_site_specific_author_boundaries(name, expected, text):
    target = next(item for item in zodiac_scraper.TARGETS if item.name == name)

    assert scrape_target(target, "203", text) == expected


@pytest.mark.parametrize(
    ("target", "issue", "expected", "text", "anchor", "end"),
    [
        (
            Target("https://example.test/topic/feng.html", "tail", "碎风漫卷", "平特一肖"),
            "203",
            ("牛", "203期 12-11-31-03-44-37 T25+05=牛√"),
            "\n".join(
                [
                    "204期【平特一肖】已公开",
                    "碎风漫卷 发表于 07月23日 15:09:24",
                    "202期 21-15-25-47-13-45 T40+05=蛇×",
                    "203期 12-11-31-03-44-37 T25+05=牛√",
                    "204期平特牛肖√",
                    "鸿蒙娱乐城",
                    "204期【平特一肖】猪猪猪",
                ]
            ),
            "碎风漫卷 发表于",
            "鸿蒙娱乐城",
        ),
        (
            Target("https://example.test/topic/love.html", "tail", "爱奇朵拉", "平特一肖"),
            "204",
            ("牛", "204期平特牛肖√"),
            "\n".join(
                [
                    "204期【爱奇朵拉】【平特一肖】已公开",
                    "爱奇朵拉 发表于 07月23日 15:08:47",
                    "203期 12-15-31-03-44-37 T25+05=牛√",
                    "204期平特牛肖√",
                    "上一篇：",
                    "204期【爱恋娃娃】【24码中特】已公开",
                ]
            ),
            "爱奇朵拉 发表于",
            "上一篇：",
        ),
        (
            Target("https://example.test/topic/hong.html", "tail", "哄堂大笑", "平特一肖"),
            "204",
            ("鼠", "204期：平特一肖【鼠鼠鼠】‖开00准"),
            "\n".join(
                [
                    "平特帖204期:【平特一肖】",
                    "作者:哄堂大笑",
                    "203期：平特一肖【猪猪猪】‖开44准",
                    "204期：平特一肖【鼠鼠鼠】‖开00准",
                    "鸿蒙娱乐城",
                    "204期:〖平特一肖〗猪猪猪",
                ]
            ),
            "作者:哄堂大笑",
            "鸿蒙娱乐城",
        ),
    ],
)
def test_author_section_parser_handles_mixed_result_rows_and_stops_at_boundary(
    target, issue, expected, text, anchor, end
):
    rule = strict_special_rule(target, "author_section")
    rule.update({"section_anchor": anchor, "section_end": end, "section_end_exact": True})
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        assert scrape_target(target, issue, text) == expected
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_new_onboarding_targets_have_unique_bounded_site_rules():
    expected = {
        "水中着盐": ("tail", "平特２肖", "author_section"),
        "高才卓识": ("tail", "平特二肖", "author_section"),
        "阳春三月": ("tail", "平特二肖", "author_section"),
        "条分缕析": ("tail", "平特二肖", "author_section"),
        "春风风人": ("top", "成语平特", "anchored_section"),
        "万家灯火": ("top", "成语平特", "anchored_section"),
        "以后还好": ("top", "成语平特", "author_section"),
        "辞穷理尽": ("top", "平特二肖", "author_section"),
        "说东道西": ("top", "成语平特", "author_section"),
        "影遁之影": ("top", "平特二肖", "author_section"),
        "湮灭红尘": ("top", "成语平特", "author_section"),
        "掌舵一人": ("tail", "成语平特", "author_section"),
        "不揪不采": ("tail", "成语平特", "author_section"),
        "上官盐翼": ("top", "成语平特", "author_section"),
        "用智铺谋": ("top", "平特二肖", "author_section"),
        "一一对应": ("top", "平特二肖", "author_section"),
        "寿比南山": ("tail", "平特二肖", "author_section"),
        "实话实说": ("tail", "成语平特", "author_section"),
        "两面三刀": ("tail", "平特二肖", "author_section"),
    }
    targets = {target.name: target for target in zodiac_scraper.TARGETS}
    assert set(expected) <= set(targets)

    for name, (position, keyword, mode) in expected.items():
        target = targets[name]
        rules = [
            rule
            for rule in zodiac_scraper.SPECIAL_PARSE_TARGETS
            if zodiac_scraper.special_parse_rule_matches(rule, target)
        ]
        assert len(rules) == 1
        rule = rules[0]
        assert rule["url_contains"] == target.url
        assert rule["name"] == name
        assert rule["position"] == position == target.position
        assert rule["keyword"] == keyword == target.keyword
        assert rule["mode"] == mode
        assert rule["issue_format"] == "arabic_issue_exact"
        assert rule["data_structure"] == "confirmed_result_line"
        assert rule["section_boundary"] == "explicit_anchors"
        assert rule["section_anchor"]
        assert rule["section_end"]
        assert rule["source_strategy"] == "browser_main"


@pytest.mark.parametrize(
    ("name", "expected", "text"),
    [
        (
            "红袖添香",
            "龙",
            "\n".join(
                [
                    "203期:平特一肖[祝您期期大中]",
                    "作者：红袖添香",
                    "203期： 红袖添香★平特一肖★ 【龙】 开 ?? 准",
                    "Copyright ©水果奶奶 Reserved",
                    "203期：其他目录★平特一肖★【马】开00准",
                ]
            ),
        ),
        (
            "一盏琉璃",
            "马",
            "\n".join(
                [
                    "203期:平特一肖[祝您期期大中]",
                    "作者： 一盏琉璃",
                    "203期： 一盏琉璃★平特一肖★ 【马】 开 ?? 准",
                    "Copyright ©水果奶奶 Reserved",
                    "203期：其他目录★平特一肖★【龙】开00准",
                ]
            ),
        ),
        (
            "锦离鸢墨",
            "马",
            "\n".join(
                [
                    "203期:锦离鸢墨【平特一肖】独家公式",
                    "202期21-15-25-47-13-45T40 +00=马✓",
                    "203期 平特马肖",
                    "★★ 博彩必备★★",
                    "203期 平特猪肖",
                ]
            ),
        ),
        (
            "独家发表",
            "虎",
            "\n".join(
                [
                    "第203期:独家发表【④字平特】已公开√",
                    "203期④字平特〖虎虎生威〗开00准",
                    "上一篇：",
                    "第203期:独家发表【三肖平特】已公开√",
                    "203期④字平特〖猪狗不如〗开00准",
                ]
            ),
        ),
        (
            "空中飞翔",
            "龙",
            "\n".join(
                [
                    "203期:空中飞翔【平特①肖】已公开",
                    "作者:空中飞翔",
                    "203期平特①肖《天龙》开00准",
                    "★★ 博彩必备★★",
                    "203期:〖平特一肖〗猪猪猪",
                ]
            ),
        ),
        (
            "责备求全",
            "虎蛇",
            "\n".join(
                [
                    "203期:责备求全【成语平特】已公开！",
                    "责备求全 发表于 07月22日 12:20:15",
                    "203期：成语平特〖虎头蛇尾〗开：00准",
                    "★★ 博彩必备★★",
                    "203期:责备求全【成语平特】已公开！",
                    "203期：成语平特〖猪狗不如〗开：00准",
                ]
            ),
        ),
        (
            "潜水中月",
            "鸡猴",
            "\n".join(
                [
                    "203期:潜水中月「四字平特」独家提供",
                    "作者:轻虑浅谋",
                    "203期：四字平特（杀鸡儆猴）开：00准",
                    "★★ 博彩必备★★",
                    "203期:潜水中月「四字平特」独家提供",
                    "203期：四字平特（猪狗不如）开：00准",
                ]
            ),
        ),
    ],
)
def test_203_failed_sites_use_isolated_site_boundaries(name, expected, text):
    target = next(item for item in zodiac_scraper.TARGETS if item.name == name)

    zodiac, _line, reason = scrape_target_diagnostic(target, "203", text)

    assert (zodiac, reason) == (expected, None)


def test_anchored_formula_section_rejects_all_zero_placeholder_formula():
    target = Target("https://formula.example/topic/2.html", "tail", "公式目录", "平特一肖")
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        {
            "url_contains": target.url,
            "name": target.name,
            "position": target.position,
            "keyword": target.keyword,
            "mode": "anchored_formula_section",
            "section_anchor": "公式目录【平特一肖】独家公式",
            "section_end": "★★ 博彩必备★★",
        }
    ]
    text = "\n".join(
        [
            "201期:公式目录【平特一肖】独家公式",
            "第200期：43-46-05-32-35-29T39+0=猴√",
            "第201期：00-00-00-00-00-00T00+0=猴√",
            "★★ 博彩必备★★",
        ]
    )
    try:
        assert scrape_target(target, "200", text)[0] == "猴"
        assert scrape_target(target, "201", text) == (None, None)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_anchored_formula_section_rejects_other_column_formula_line():
    target = Target("https://formula.example/topic/4.html", "top", "公式目录", "公式平特")
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        {
            "url_contains": target.url,
            "name": target.name,
            "position": target.position,
            "keyword": target.keyword,
            "mode": "anchored_formula_section",
            "section_anchor": "【公式平特】",
            "section_end": "结束",
        }
    ]
    text = "\n".join(
        [
            "【公式平特】",
            "201期其他栏目 43-12-08=猴√",
            "结束",
        ]
    )
    try:
        assert zodiac_scraper.scrape_target(target, "201", text) == (None, None)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_pending_reason_for_anchored_formula_placeholder():
    target = Target("https://formula.example/topic/3.html", "tail", "公式目录", "公式平特")
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        {
            "url_contains": target.url,
            "name": target.name,
            "position": target.position,
            "keyword": target.keyword,
            "mode": "anchored_formula_section",
            "section_anchor": "【公式平特】",
            "section_end": "站长宣言",
        }
    ]
    text = "\n".join(
        [
            "201期:【公式平特】",
            "201期 平特一肖虎肖？",
            "站长宣言",
        ]
    )
    try:
        assert zodiac_scraper.pending_issue_reason(text, target, "201") == (
            "指定期数页面已出现，但该期生肖内容尚未更新"
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_formula_placeholder_sites_use_explicit_formula_boundaries():
    expected = {
        "熊出没公平": ("【公式平特】", "鸿蒙娱乐城"),
        "满堂红第四": ("【公式平特】", "站长宣言"),
        "墨言笙歌": ("墨言笙歌【平特一肖】独家公式", "★★ 博彩必备★★"),
    }
    rules = {item["name"]: item for item in zodiac_scraper.CONFIG["special_parse_targets"]}
    for name, (anchor, end) in expected.items():
        rule = rules[name]
        assert rule["mode"] == "anchored_formula_section"
        assert rule["section_anchor"] == anchor
        assert rule["section_end"] == end
        assert rule["data_structure"] == "terminal_formula_result"
        assert rule["section_boundary"] == "explicit_anchors"


def test_pending_new_site_candidates_have_unique_named_section_rules():
    expected = {
        "偶像风韵": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/248569.html", "top", "成语平特"),
        "闻所未闻": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/665091.html", "tail", "平特二肖"),
        "撩你妹妹": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/248593.html", "top", "成语平特"),
        "冰雪聪明": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/455007.html", "top", "成语平特"),
        "大器晚成": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/459152.html", "top", "平特一肖"),
        "锦绣未央": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/248603.html", "top", "成语平特"),
        "耳聪目明": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/454997.html", "top", "成语平特"),
        "大巧若拙": ("https://dahnqumi.i504e-bi3xk-bqxlqv.xyz:16677/topic/455000.html", "top", "成语平特"),
        "皮咔加油": ("https://wwtkvupm.1jpxm-0dmxs-hzimql.xyz:16677/topic/305386.html", "top", "平特一肖"),
        "光明正大": ("https://wwtkvupm.1jpxm-0dmxs-hzimql.xyz:16677/topic/305409.html", "top", "平特一肖"),
        "心平气舒": ("https://ewnhbquq.8udr7-6win8-yfikpo.xyz:16677/topic/469702.html", "tail", "三字平特"),
        "菲食薄衣": ("https://ewnhbquq.8udr7-6win8-yfikpo.xyz:16677/topic/454685.html", "tail", "平特二肖"),
        "整军饬武": ("https://ewnhbquq.8udr7-6win8-yfikpo.xyz:16677/topic/457598.html", "tail", "平特二肖"),
        "廖哥袭平": ("https://ewnhbquq.8udr7-6win8-yfikpo.xyz:16677/topic/250775.html", "tail", "成语平特"),
        "外滩画报": ("https://ewnhbquq.8udr7-6win8-yfikpo.xyz:16677/topic/457599.html", "tail", "平特二肖"),
    }
    targets = {target.name: target for target in zodiac_scraper.TARGETS}
    rules = {rule["name"]: rule for rule in zodiac_scraper.SPECIAL_PARSE_TARGETS}
    for name, (url, position, keyword) in expected.items():
        assert name in targets
        assert (targets[name].url, targets[name].position, targets[name].keyword) == (url, position, keyword)
        assert rules[name]["url_contains"] == url
        assert rules[name]["mode"] == "named_section"
def test_keyword_target_does_not_use_header_or_section_fallback():
    text = "\n".join(
        [
            "167期:墨言笙歌【平特一肖】独家公式",
            "166期：20-15-01-04-21-28T06+0=兔√",
        ]
    )

    zodiac, line = scrape_target(Target("x", "tail", "墨言笙歌", "平特一肖"), "166", text)

    assert zodiac is None
    assert line is None


def test_keyword_target_does_not_use_followup_fallback():
    text = "\n".join(
        [
            "164期【AI推荐平特】开？00中",
            "平特一肖：鸡鸡鸡",
        ]
    )

    zodiac, line = scrape_target(Target("https://x/not-special.html", "top", "AI平特肖", "AI推荐平特"), "164", text)

    assert zodiac is None
    assert line is None


def test_special_header_section_extracts_named_url_only():
    target = Target("https://x/topic/654109.html", "tail", "碎风漫卷", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "\n".join(
            [
                "169期【平特一肖】已公开",
                "碎风漫卷 发表于 06月17日 23:00:05",
                "168期 27-11-24-05-40-33 T15+7=牛√",
                "169期 平特牛肖",
            ]
        )

        zodiac, line = scrape_target(target, "169", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "牛"
    assert line == "169期 平特牛肖"


def test_special_next_line_zodiac_extracts_only_configured_url():
    target = Target("https://x/art_art/8126.html", "top", "山涧晴岚", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "next_line_zodiac")]
    try:
        text = "\n".join(["169期:平特一肖开:00准", "【蛇】"])
        zodiac, line = scrape_target(target, "169", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "蛇"
    assert "【蛇】" in line


def test_special_header_section_does_not_use_previous_issue_when_requested_missing():
    target = Target("https://x/art_gsb/9875.html", "top", "一盏琉璃", "一盏琉璃★平特一肖★")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "next_line_zodiac")]
    try:
        text = "\n".join(
            [
                "170期：",
                "一盏琉璃★平特一肖★",
                "【虎】",
                "开 ?? 准",
                "168期: 一盏琉璃★平特一肖★ 【羊】 开 24 准",
            ]
        )
        zodiac, line = scrape_target(target, "169", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_special_header_section_does_not_use_next_issue_when_requested_missing():
    target = Target("https://x/art_gsb/9875.html", "top", "一盏琉璃", "一盏琉璃★平特一肖★")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "next_line_zodiac")]
    try:
        text = "\n".join(
            [
                "170期：",
                "一盏琉璃★平特一肖★",
                "【虎】",
                "开 ?? 准",
            ]
        )
        zodiac, line = scrape_target(target, "169", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_special_nearest_keyword_line_does_not_use_previous_issue():
    target = Target("https://x/topic/267381.html", "top", "无敌金刚", "两字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "nearest_keyword_line")]
    try:
        text = "\n".join(
            [
                "169期: 无敌金刚《两字平特》奔向富豪",
                "168期《两字平特》《老虎》开00准",
            ]
        )
        zodiac, line = scrape_target(target, "169", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_special_named_section_extracts_issue_line_without_full_keyword():
    target = Target("https://x/topic/741286.html", "tail", "气冲牛斗", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        text = "\n".join(
            [
                "平特贴 178期:【平特一肖】买码必看",
                "气冲牛斗 发表于 08月02日 20:04:44",
                "177期平特 鼠肖",
            ]
        )
        zodiac, line = scrape_target(target, "177", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "鼠"
    assert line == "177期平特 鼠肖"



def test_special_mode_does_not_fall_back_to_generic_keyword_line():
    target = Target("https://x/topic/455715.html", "top", "鬼使神差", "四字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        text = "164期:四字平特【虎头蛇尾】开00准"
        zodiac, line = scrape_target(target, "164", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_linked_topic_appends_matching_issue_detail(monkeypatch):
    target = Target("https://x/topic/257907.html", "top", "逆天飞翔", "三字平特")
    old_targets = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "linked_topic")]
    fetched: list[str] = []

    def fake_fetch_raw(url: str, timeout: int) -> str:
        fetched.append(url)
        if url.endswith("257907.html"):
            return """
            <a href="/topic/1039398.html"><p>190期：【成王败寇】☆肉菜草肖☆实力见证！</p></a>
            <a href="/topic/1039399.html"><p>190期：【逆天飞翔】☆三字平特☆实力见证！</p></a>
            <a href="/topic/1039397.html"><p>189期：【逆天飞翔】☆三字平特☆实力见证！</p></a>
            """
        return "190期：【逆天飞翔】☆三字平特☆实力见证！\n190期:三字平特『喜羊羊』开00准"

    monkeypatch.setattr(zodiac_scraper, "fetch_raw", fake_fetch_raw)
    try:
        text = zodiac_scraper.fetch_text(target.url, 1, "190")
        zodiac, line = scrape_target(target, "190", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_targets

    assert fetched == ["https://x/topic/257907.html", "https://x/topic/1039399.html"]
    assert zodiac == "羊"
    assert line == "190期:三字平特『喜羊羊』开00准"


def test_god_gambler_dedicated_bottom_issue_zodiac():
    text = "\n".join(
        [
            "热177期【赌神平特】规律",
            "176期：马√",
            "177期：羊",
        ]
    )

    zodiac, line = scrape_target(
        Target("https://sadoleu.rznla-fgwyr-nzqalp.xyz:16677/topic/385412.html", "tail", "赌神平特", "赌神平特"),
        "177",
        text,
    )

    assert zodiac == "羊"
    assert line == "177期：羊"


def test_xiaobai_dedicated_bottom_issue_zodiac():
    text = "\n".join(
        [
            "热177期【小白平特】规律",
            "176期：猪√",
            "177期：狗",
        ]
    )

    zodiac, line = scrape_target(
        Target("https://sadoleu.rznla-fgwyr-nzqalp.xyz:16677/topic/385408.html", "tail", "小白平特", "小白平特"),
        "177",
        text,
    )

    assert zodiac == "狗"
    assert line == "177期：狗"


def test_bottom_issue_zodiac_is_limited_to_dedicated_targets():
    text = "\n".join(["热177期【其它目录】规律", "177期：羊"])

    zodiac, line = scrape_target(Target("https://x/topic/other.html", "tail", "其它目录", "其它目录"), "177", text)

    assert zodiac is None
    assert line is None


def test_issue_lines_keeps_wrapped_block_until_next_issue():
    text = "标题\n164期:谜语平特-红娘过桥狗鸡随-\n开? 00准\n163期:谜语平特-兔羊-\n"

    assert issue_lines(text, "164") == ["164期:谜语平特-红娘过桥狗鸡随- 开? 00准"]


def test_html_to_text_expands_strdecode_base64_chunks():
    page = 'document.writeln(utf8to16(strdecode("MTY05pyf44CQ54uX54uX54uX44CR5byA")));'

    assert "164期【狗狗狗】开" in html_to_text(page)


def test_build_output_appends_zodiac_ranking():
    output = build_output(["牛马 无字之思", "蛇鼠 重见天日", "狗 责备求全", "猪狗 狂迷情侣"])

    assert output.endswith("排行榜\n狗 2\n鼠 1\n牛 1\n蛇 1\n马 1\n猪 1\n")


def test_run_rejects_more_than_two_zodiacs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(zodiac_scraper, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", tmp_path / "recent_10_cache.json")
    target = Target("https://x", "top", "测试目录", "成语平特")
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_text",
        lambda url, timeout, issue, **_kwargs: (
            "164期:测试目录【成语平特】\n164期成语平特【鼠牛虎】开00准"
        ),
    )

    assert zodiac_scraper.run("164", None, 1) == 1
    label = zodiac_scraper.date_label()
    assert Path(f"{label}平特肖.txt").read_text(encoding="utf-8") == ""
    failure_text = Path(f"{label}平特肖-失败.txt").read_text(encoding="utf-8")
    assert "抓到的生肖超过2个，按规则丢失败，生肖：鼠牛虎" in failure_text
    assert "目录：测试目录" in failure_text


def test_update_recent_10_cache_keeps_latest_ten_issues(tmp_path, monkeypatch):
    cache_path = tmp_path / "recent_10_cache.json"
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    target = Target("https://x", "top", "测试目录", "平特一肖")
    cache_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "window_size": 10,
                "issues": [172, 171],
                "sites": [
                    {
                        "name": "测试目录",
                        "url": "https://x",
                        "position": "top",
                        "keyword": "平特一肖",
                        "values": {"172": "鼠", "171": "牛"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    assert zodiac_scraper.update_recent_10_cache([target], {zodiac_scraper.target_cache_key(target): "虎"}, "183")

    data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    assert data["issues"] == [183, 172, 171]
    assert data["sites"][0]["values"] == {"183": "虎", "172": "鼠", "171": "牛"}
    assert data["sites"][0]["position"] == "top"
    assert data["sites"][0]["keyword"] == "平特一肖"


def test_recent_10_cache_separates_same_url_different_directories(tmp_path, monkeypatch):
    cache_path = tmp_path / "recent_10_cache.json"
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    targets = [
        Target("https://same", "top", "智能平特", "平特一肖"),
        Target("https://same", "top", "智能成语", "成语平特"),
    ]

    assert zodiac_scraper.update_recent_10_cache(
        targets,
        {zodiac_scraper.target_cache_key(targets[0]): "猪", zodiac_scraper.target_cache_key(targets[1]): "牛马"},
        "183",
    )

    data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    assert [(item["name"], item["values"]) for item in data["sites"]] == [
        ("智能平特", {"183": "猪"}),
        ("智能成语", {"183": "牛马"}),
    ]


def test_recent_10_cache_preserves_target_order_when_old_cache_order_differs(tmp_path, monkeypatch):
    cache_path = tmp_path / "recent_10_cache.json"
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    targets = [
        Target("https://a", "top", "目录A", "平特一肖"),
        Target("https://b", "tail", "目录B", "成语平特"),
    ]
    cache_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "issues": [182],
                "sites": [
                    {
                        "name": "目录B",
                        "url": "https://b",
                        "position": "tail",
                        "keyword": "成语平特",
                        "values": {"182": "牛"},
                    },
                    {
                        "name": "目录A",
                        "url": "https://a",
                        "position": "top",
                        "keyword": "平特一肖",
                        "values": {"182": "鼠"},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    zodiac_scraper.update_recent_10_cache(
        targets,
        {zodiac_scraper.target_cache_key(targets[0]): "虎", zodiac_scraper.target_cache_key(targets[1]): "兔"},
        "183",
    )

    data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    assert [item["name"] for item in data["sites"]] == ["目录A", "目录B"]
    assert data["sites"][0]["values"] == {"183": "虎", "182": "鼠"}
    assert data["sites"][1]["values"] == {"183": "兔", "182": "牛"}


def test_recent_10_cache_uses_full_target_identity_not_name_only(tmp_path, monkeypatch):
    cache_path = tmp_path / "recent_10_cache.json"
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    targets = [
        Target("https://a", "top", "同名目录", "平特一肖"),
        Target("https://b", "tail", "同名目录", "成语平特"),
    ]

    zodiac_scraper.update_recent_10_cache(
        targets,
        {zodiac_scraper.target_cache_key(targets[0]): "虎", zodiac_scraper.target_cache_key(targets[1]): "兔"},
        "183",
    )

    data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    assert [item["values"] for item in data["sites"]] == [{"183": "虎"}, {"183": "兔"}]


def test_run_updates_recent_10_cache_for_successes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(zodiac_scraper, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", tmp_path / "recent_10_cache.json")
    target = Target("https://x", "top", "测试目录", "成语平特")
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_text",
        lambda url, timeout, issue, **_kwargs: (
            "183期:测试目录【成语平特】\n183期成语平特【牛气冲天】开00准"
        ),
    )

    assert zodiac_scraper.run("183", None, 1) == 0

    data = json.loads((tmp_path / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
    assert data["issues"] == [183]
    assert data["sites"][0]["values"] == {"183": "牛"}


def test_run_can_skip_recent_10_cache_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(zodiac_scraper, "OUTPUT_DIR", tmp_path)
    cache_path = tmp_path / "recent_10_cache.json"
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    target = Target("https://x", "top", "测试目录", "成语平特")
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_text",
        lambda url, timeout, issue, **_kwargs: (
            "183期:测试目录【成语平特】\n183期成语平特【牛气冲天】开00准"
        ),
    )

    assert zodiac_scraper.run("183", None, 1, update_cache=False) == 0

    assert not cache_path.exists()


def test_multi_failure_summary_lists_only_all_failed_directories(tmp_path):
    issue_results = {
        "187": {
            "success": tmp_path / "187.txt",
            "failure": tmp_path / "187.errors.txt",
        },
        "188": {
            "success": tmp_path / "188.txt",
            "failure": tmp_path / "188.errors.txt",
        },
    }
    issue_results["187"]["success"].write_text("鼠 目录A\n", encoding="utf-8")
    issue_results["188"]["success"].write_text("牛 目录B\n", encoding="utf-8")
    issue_results["187"]["failure"].write_text(
        "原因187，目录：目录B，网址：https://b\n原因187，目录：目录C，网址：https://c\n",
        encoding="utf-8",
    )
    issue_results["188"]["failure"].write_text(
        "原因188，目录：目录A，网址：https://a\n原因188，目录：目录C，网址：https://c\n",
        encoding="utf-8",
    )
    targets = [
        Target("https://a", "top", "目录A", "平特一肖"),
        Target("https://b", "top", "目录B", "平特一肖"),
        Target("https://c", "top", "目录C", "平特一肖"),
    ]

    text = zodiac_multi.build_multi_failure_summary(["187", "188"], targets, issue_results)

    assert "全部失败目录数：1" in text
    assert "目录C" in text
    assert "187期：原因187，目录：目录C，网址：https://c" in text
    assert "188期：原因188，目录：目录C，网址：https://c" in text
    assert "目录A" not in text
    assert "目录B" not in text


def test_find_recent_10_cache_duplicates_uses_candidate_common_issue_values():
    cache = {
        "issues": [183, 182, 181],
        "sites": [
            {
                "name": "旧目录",
                "url": "https://old",
                "position": "top",
                "keyword": "平特一肖",
                "values": {"183": "猪", "182": "鸡", "181": "牛"},
            }
        ],
    }

    matches, reason = zodiac_scraper.find_recent_10_cache_duplicates({"183": "猪", "182": "鸡"}, cache)

    assert reason is None
    assert [item["name"] for item in matches] == ["旧目录"]


def test_find_recent_10_cache_duplicates_rejects_candidate_without_common_issue():
    cache = {"issues": [183, 182, 181], "sites": []}

    matches, reason = zodiac_scraper.find_recent_10_cache_duplicates({"180": "猪"}, cache)

    assert matches == []
    assert reason == "候选站没有抓到缓存中的共同有效期数，不能完成重复检测"


def test_find_recent_10_cache_duplicates_matches_same_issue_values():
    cache = {
        "issues": [183, 182, 181],
        "sites": [
            {
                "name": "旧目录",
                "url": "https://old",
                "position": "top",
                "keyword": "平特一肖",
                "values": {"183": "猪", "182": "鸡", "181": "牛"},
            },
            {
                "name": "不同目录",
                "url": "https://other",
                "position": "tail",
                "keyword": "成语平特",
                "values": {"183": "牛", "182": "鸡", "181": "猪"},
            },
        ],
    }

    matches, reason = zodiac_scraper.find_recent_10_cache_duplicates(
        {"183": "猪", "182": "鸡", "181": "牛"},
        cache,
    )

    assert reason is None
    assert [item["name"] for item in matches] == ["旧目录"]


def test_validate_candidate_cache_latest_two_accepts_latest_or_previous_issue():
    cache = {"issues": [186, 185, 184], "sites": []}

    ok, reason = zodiac_scraper.validate_candidate_cache_latest_two({"185": "牛"}, cache)

    assert ok is True
    assert reason is None


def test_validate_candidate_cache_latest_two_rejects_outside_latest_two():
    cache = {"issues": [186, 185, 184], "sites": []}

    ok, reason = zodiac_scraper.validate_candidate_cache_latest_two({"184": "虎"}, cache)

    assert ok is False
    assert reason == "候选站没有抓到缓存最新近2期（186期、185期）中的任意一期，不能视为有效"


def test_validate_candidate_cache_latest_two_rejects_empty_cache():
    ok, reason = zodiac_scraper.validate_candidate_cache_latest_two({"186": "虎"}, {"issues": [], "sites": []})

    assert ok is False
    assert reason == "recent_10_cache.json 没有基准期数，不能验证新增站点"


def test_named_section_extracts_wrapped_current_issue_block():
    text = "\n".join(
        [
            "184期:山涧晴岚【平特一肖】[祝您期期大中]",
            "作者：山涧晴岚",
            "184期:",
            "平特一肖",
            "【虎】",
            "开 ?? 准",
            "183期: 平特一肖 【猴】 开 23 准",
        ]
    )
    target = Target("https://x/art_art/8126.html", "top", "山涧晴岚", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        zodiac, line = scrape_target(target, "184", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "虎"
    assert line == "184期: 平特一肖 【虎】 开 ?? 准"


def test_pending_issue_reason_when_issue_header_exists_without_zodiac():
    text = "\n".join(
        [
            "184期:山涧晴岚【平特一肖】[祝您期期大中]",
            "作者：山涧晴岚",
            "184期:",
            "平特一肖",
            "183期: 平特一肖 【猴】 开 23 准",
        ]
    )
    target = Target("https://x/art_art/8126.html", "top", "山涧晴岚", "平特一肖")

    zodiac, line = scrape_target(target, "184", text)

    assert zodiac is None
    assert line is None
    assert zodiac_scraper.pending_issue_reason(text, target, "184") == "指定期数页面已出现，但该期生肖内容尚未更新"


def test_unavailable_reason_detects_removed_topic():
    assert unavailable_reason("正文 此帖子ID已被下架 其他") == "帖子ID已被下架，页面没有可解析数据"


def test_progress_line_matches_terminal_format(monkeypatch):
    monkeypatch.setattr(zodiac_scraper.time, "monotonic", lambda: 117.1)

    line = zodiac_scraper.progress_line("进度", 2, 120, 2, 0, 100.0, "亡魂丧魄")

    assert line == "[进度 2/120 1% 成功 2 失败 0 用时 17.1s] 当前：亡魂丧魄"


def test_progress_percent_handles_empty_total():
    assert zodiac_scraper.progress_percent(0, 0) == 100


@pytest.mark.parametrize("wrong_issue", ["1191", "0191", "2026191"])
def test_issue_matching_requires_complete_digit_boundaries(wrong_issue):
    target = Target("https://x", "top", "测试目录", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    rule = strict_special_rule(target, "header_section")
    rule["source_strategy"] = "dynamic_record"
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        zodiac, line = scrape_target(target, "191", f"{wrong_issue}期:平特一肖【虎】开00准")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None


def test_header_section_stops_at_advertisement_and_next_author():
    target = Target("https://x", "top", "目标作者", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "\n".join(
            [
                "191期【平特一肖】目标作者",
                "广告推荐",
                "191期:平特一肖【虎】开00准",
                "下一作者 发表于 10:00",
                "191期:平特一肖【牛】开00准",
            ]
        )
        zodiac, line, reason = zodiac_scraper.scrape_target_diagnostic(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None
    assert reason is None


def test_same_issue_different_zodiac_candidates_fail_as_conflict():
    target = Target("https://x", "top", "目标作者", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "\n".join(
            [
                "191期【平特一肖】目标作者",
                "191期:平特一肖【虎】开00准",
                "191期:平特一肖【牛】开00准",
            ]
        )
        zodiac, line, reason = zodiac_scraper.scrape_target_diagnostic(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None
    assert reason == "同一目标文档出现不同生肖候选：虎、牛"


@pytest.mark.parametrize(
    "line",
    [
        "191期目录标题【马到成功平特一肖】作者：测试",
        "191期声明：开后马后炮资料直接封号，平特一肖【虎】",
        "191期非目标栏目开奖结果 开:02准",
    ],
)
def test_extract_zodiac_rejects_titles_disclaimers_and_unbound_open_results(line):
    assert extract_zodiac(line) is None


def test_extract_zodiac_rejects_station提示_declaration_line():
    assert extract_zodiac("201期平特一肖【虎】站长提示开000中") is None


def test_extract_zodiac_keeps_confirmed_target_open_number_conversion():
    assert extract_zodiac("191期:平特一肖 开:02准") == "蛇"


def test_vue_user_fetch_keeps_only_matching_forum(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562"
    target = Target(url, "top", "年轻画作", "平特心水一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    rule = strict_special_rule(target, "header_section")
    rule["source_strategy"] = "dynamic_record"
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    payload = [
        {
            "id": 1,
            "user_id": 1562,
            "draw": 190,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "title": "191期其它栏目",
            "content": "191期:平特一肖【牛】开00准",
        },
        {
            "id": 2,
            "user_id": 1562,
            "draw": 191,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "title": "191期平特心水一肖",
            "content": "191期:平特心水一肖【虎】开00准",
        },
    ]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        text = zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert "【虎】" in text
    assert "【牛】" not in text
    assert "[[FORUM:2]]" in text


def test_dynamic_rule_requires_record_topic():
    target = Target(
        "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562",
        "top",
        "年轻画作",
        "平特心水一肖",
    )
    rule = strict_special_rule(target, "header_section")
    rule["source_strategy"] = "dynamic_record"
    config = {"targets": [
        {
            "url": target.url,
            "position": target.position,
            "name": target.name,
            "keyword": target.keyword,
        }
    ], "special_parse_targets": [rule]}

    with pytest.raises(ValueError, match="record_topic"):
        zodiac_scraper.validate_config(config)


def test_anchored_rule_requires_explicit_section_bounds():
    target = Target("https://x/topic/1.html", "top", "目录", "成语平特")
    rule = strict_special_rule(target, "anchored_section")
    config = {
        "targets": [{
            "url": target.url,
            "position": target.position,
            "name": target.name,
            "keyword": target.keyword,
        }],
        "special_parse_targets": [rule],
    }

    with pytest.raises(ValueError, match="section_anchor"):
        zodiac_scraper.validate_config(config)


def test_dynamic_record_rejects_wrong_column_even_when_content_matches():
    target = Target(
        "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562",
        "top",
        "年轻画作",
        "平特心水一肖",
    )
    rule = strict_special_rule(target, "header_section")
    rule["source_strategy"] = "dynamic_record"
    rule["record_topic"] = "平特一肖"
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    row = {
        "id": 191,
        "user_id": 1562,
        "draw": 191,
        "status": "published",
        "topic": "其它栏目",
        "user": {"id": 1562, "nickname": "年轻画作"},
        "content": "191期:平特心水一肖【虎】开00准",
    }
    try:
        with pytest.raises(RuntimeError, match="栏目校验失败"):
            zodiac_scraper._dynamic_record_fields("$[0]", row, target)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_vue_user_fetch_uses_draw_record_boundary_before_parsing_content(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562"
    target = Target(url, "top", "年轻画作", "平特心水一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    rule = strict_special_rule(target, "header_section")
    rule["source_strategy"] = "dynamic_record"
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    payload = [
        {
            "id": 191,
            "user_id": 1562,
            "draw": 191,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "title": "",
            "content": "191期:平特心水一肖【虎】开00准",
        },
        {
            "id": 190,
            "user_id": 1562,
            "draw": 190,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "title": "",
            "content": "191期:平特心水一肖【牛】开00准",
        },
    ]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        text = zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
        zodiac, line = scrape_target(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "虎"
    assert "【牛】" not in text
    assert "[[FORUM:191]]" in text


def test_vue_user_fetch_rejects_multiple_records_for_same_draw(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562"
    target = Target(url, "top", "年轻画作", "平特心水一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    payload = [
        {
            "id": 191,
            "user_id": 1562,
            "draw": 191,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "content": "191期:平特心水一肖【虎】开00准",
        },
        {
            "id": 192,
            "user_id": 1562,
            "draw": 191,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "content": "191期:平特心水一肖【牛】开00准",
        },
    ]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        with pytest.raises(RuntimeError, match="多条文章记录"):
            zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_vue_user_fetch_rejects_period_fallback_when_draw_is_different(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562"
    target = Target(url, "top", "年轻画作", "平特心水一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    payload = [{
        "id": 190,
        "user_id": 1562,
        "draw": 190,
        "status": "published",
        "user": {"id": 1562, "nickname": "年轻画作"},
        "content": "191期:平特心水一肖【牛】开00准",
    }]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        with pytest.raises(RuntimeError, match="没有唯一文章记录"):
            zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_vue_user_fetch_walks_structured_nested_response(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562"
    target = Target(url, "top", "年轻画作", "平特心水一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    payload = {
        "data": {
            "items": [{
                "id": 191,
                "user_id": 1562,
                "draw": 191,
                "status": "published",
                "user": {"id": 1562, "nickname": "年轻画作"},
                "content": "191期:平特心水一肖【虎】开00准",
            }]
        }
    }
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        text = zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert "[[FORUM:191]]" in text
    assert "【虎】" in text


def test_vue_user_fetch_rejects_mismatched_author_identity(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562"
    target = Target(url, "top", "年轻画作", "平特心水一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    payload = [{
        "id": 191,
        "user_id": 1562,
        "draw": 191,
        "status": "published",
        "user": {"id": 1491, "nickname": "免费门"},
        "content": "191期:平特心水一肖【牛】开00准",
    }]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        with pytest.raises(RuntimeError, match="作者校验失败"):
            zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_vue_user_fetch_rejects_duplicate_article_id(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1562"
    target = Target(url, "top", "年轻画作", "平特心水一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    payload = [
        {
            "id": 191,
            "user_id": 1562,
            "draw": 191,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "content": "191期:平特心水一肖【虎】开00准",
        },
        {
            "id": 191,
            "user_id": 1562,
            "draw": 190,
            "status": "published",
            "user": {"id": 1562, "nickname": "年轻画作"},
            "content": "190期:平特心水一肖【牛】开00准",
        },
    ]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        with pytest.raises(RuntimeError, match="重复文章ID"):
            zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_linked_topic_uses_detail_body_not_parent_candidate(monkeypatch):
    target = Target("https://x/topic/parent.html", "top", "逆天飞翔", "三字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "linked_topic")]

    def fake_fetch_raw(url, _timeout):
        if url.endswith("parent.html"):
            return """<div>191期:三字平特【牛】开00准</div><a href='/topic/1039399.html'>191期 逆天飞翔 三字平特</a>"""
        return "191期:三字平特【虎】开00准<a href='/topic/parent.html'>返回</a>"

    monkeypatch.setattr(zodiac_scraper, "fetch_raw", fake_fetch_raw)
    try:
        text = zodiac_scraper.fetch_text(target.url, 1, "191")
        zodiac, line = scrape_target(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "虎"
    assert "【牛】" not in text
    assert "detail.html" not in text
    assert "【虎】" in line


def test_linked_topic_rejects_cross_origin_or_non_detail_link(monkeypatch):
    target = Target("https://x.example/topic/parent.html", "top", "逆天飞翔", "三字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "linked_topic")]
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_raw",
        lambda *_args: '<a href="https://evil.example/anything">191期 逆天飞翔 三字平特</a>',
    )
    try:
        with pytest.raises(RuntimeError, match="同源|详情"):
            zodiac_scraper.fetch_text(target.url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_target_image_urls_excludes_unrelated_page_images():
    target = Target("https://x/topic/1", "top", "目标作者", "平特一肖")
    page = """
    <img data-original='/ads/wrong.bin'>
    <section><h2>191期 目标作者 平特一肖</h2><img data-original='/target/right.bin'></section>
    <section><h2>191期 其他作者 平特一肖</h2><img data-original='/other/wrong.bin'></section>
    """

    assert zodiac_scraper.target_image_urls(page, target, "191") == ["/target/right.bin"]


def test_corrupt_cache_is_fail_closed_and_not_overwritten(tmp_path, monkeypatch):
    cache_path = tmp_path / "recent_10_cache.json"
    cache_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    target = Target("https://x", "top", "测试目录", "平特一肖")

    assert zodiac_scraper.update_recent_10_cache(
        [target], {zodiac_scraper.target_cache_key(target): "虎"}, "191"
    ) is False
    assert cache_path.read_text(encoding="utf-8") == "{broken"


def test_cache_updates_are_serialized_and_preserve_both_issues(tmp_path, monkeypatch):
    cache_path = tmp_path / "recent_10_cache.json"
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    target = Target("https://x", "top", "测试目录", "平特一肖")
    barrier = threading.Barrier(2)

    def update(issue, zodiac):
        barrier.wait()
        assert zodiac_scraper.update_recent_10_cache(
            [target], {zodiac_scraper.target_cache_key(target): zodiac}, issue
        )

    threads = [threading.Thread(target=update, args=("191", "虎")), threading.Thread(target=update, args=("192", "牛"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    assert data["issues"] == [192, 191]
    assert data["sites"][0]["values"] == {"192": "牛", "191": "虎"}


def test_fetch_raw_reports_urllib_and_requests_failure_chain(monkeypatch):
    monkeypatch.setattr(zodiac_scraper, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("urllib down")))
    monkeypatch.setattr(zodiac_scraper.time, "sleep", lambda _seconds: None)
    fake_requests = types.ModuleType("requests")
    fake_requests.packages = types.SimpleNamespace(
        urllib3=types.SimpleNamespace(
            exceptions=types.SimpleNamespace(InsecureRequestWarning=Warning),
            disable_warnings=lambda *_args: None,
        )
    )
    fake_requests.get = lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("requests down"))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "requests.packages", fake_requests.packages)
    monkeypatch.setitem(sys.modules, "requests.packages.urllib3", fake_requests.packages.urllib3)
    monkeypatch.setitem(sys.modules, "requests.packages.urllib3.exceptions", fake_requests.packages.urllib3.exceptions)

    with pytest.raises(RuntimeError, match="urllib down.*requests down"):
        zodiac_scraper.fetch_raw("https://x", 1)


def test_validate_config_rejects_invalid_position_and_missing_dedicated_rule():
    config = {
        "targets": [{"url": "https://x", "position": "middle", "name": "目录", "keyword": "平特一肖"}],
        "special_parse_targets": [],
    }

    with pytest.raises(ValueError, match="position.*专属解析"):
        zodiac_scraper.validate_config(config)


def test_fetch_text_keeps_auxiliary_script_failure_diagnostic(monkeypatch):
    def fake_fetch_raw(url, _timeout):
        if url == "https://x/topic/1.html":
            return "<div>正文</div><script src='/upload/script/data.js'></script>"
        raise OSError("script down")

    monkeypatch.setattr(zodiac_scraper, "fetch_raw", fake_fetch_raw)

    text = zodiac_scraper.fetch_text("https://x/topic/1.html", 1, "191")

    assert "正文" in text
    assert "附属资源失败:脚本 https://x/upload/script/data.js：OSError: script down" in text


def test_linked_topic_self_loop_is_fail_closed_with_diagnostic(monkeypatch):
    target = Target("https://x/topic/257907.html", "top", "逆天飞翔", "三字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "linked_topic")]
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_raw",
        lambda *_args: "<a href='/topic/257907.html'>191期 逆天飞翔 三字平特</a><div>191期:三字平特【牛】开00准</div>",
    )
    try:
        with pytest.raises(RuntimeError, match="关联正文循环"):
            zodiac_scraper.fetch_text(target.url, 1, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_fetch_session_reuses_fragmentless_page_shell(monkeypatch):
    calls = []

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"same shell"

    def fake_urlopen(request, **_kwargs):
        calls.append(request.full_url)
        return Response()

    monkeypatch.setattr(zodiac_scraper, "urlopen", fake_urlopen)
    session = zodiac_scraper.FetchSession()

    first = zodiac_scraper.fetch_raw("https://x/#/users/1", 5, session=session)
    second = zodiac_scraper.fetch_raw("https://x/#/users/2", 5, session=session)

    assert first == second == "same shell"
    assert calls == ["https://x/"]


def test_fetch_session_limits_concurrent_requests_per_host(monkeypatch):
    active = 0
    maximum = 0
    counter_lock = threading.Lock()

    class Response:
        headers = {}

        def __enter__(self):
            nonlocal active, maximum
            with counter_lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            return self

        def __exit__(self, *_args):
            nonlocal active
            with counter_lock:
                active -= 1
            return False

        def read(self):
            return b"ok"

    monkeypatch.setattr(zodiac_scraper, "urlopen", lambda *_args, **_kwargs: Response())
    session = zodiac_scraper.FetchSession(max_per_host=2)

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(lambda index: zodiac_scraper.fetch_raw(f"https://x/{index}", 5, session=session), range(6)))

    assert maximum == 2


def test_validate_config_rejects_multiple_dedicated_rules():
    target = {"url": "https://x/topic/1", "position": "top", "name": "目录", "keyword": "平特一肖"}
    rule = {"url_contains": "https://x/", "position": "top", "name": "目录", "keyword": "平特一肖", "mode": "header_section"}
    config = {"targets": [target], "special_parse_targets": [rule, {**rule, "url_contains": "topic/1"}]}

    with pytest.raises(ValueError, match="必须且只能匹配1条"):
        zodiac_scraper.validate_config(config)


def test_validate_config_rejects_partial_url_dedicated_rule():
    target = Target("https://x/topic/1", "top", "目录", "平特一肖")
    rule = strict_special_rule(target, "header_section")
    rule["url_contains"] = "https://x/"

    with pytest.raises(ValueError, match="完整URL"):
        zodiac_scraper.validate_config(
            {
                "targets": [
                    {
                        "url": target.url,
                        "position": target.position,
                        "name": target.name,
                        "keyword": target.keyword,
                    }
                ],
                "special_parse_targets": [rule],
            }
        )


def test_fetch_raw_does_not_retry_permanent_not_found(monkeypatch):
    calls = []

    def fail(request, **_kwargs):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 404, "missing", {}, None)

    monkeypatch.setattr(zodiac_scraper, "urlopen", fail)

    with pytest.raises(HTTPError):
        zodiac_scraper.fetch_raw("https://x/missing", 5)

    assert calls == ["https://x/missing"]


def test_anchored_section_uses_only_configured_column_block():
    target = Target("https://x", "top", "首页目录", "四字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        {
            **strict_special_rule(target, "anchored_section"),
            "section_anchor": "首页固定四字栏目",
            "section_end": "首页下一栏目",
        }
    ]
    text = "\n".join(
        [
            "首页固定四字栏目",
            "191期四字平特【猪朋狗友】开00准",
            "首页下一栏目",
            "191期四字平特【龙马精神】开00准",
        ]
    )
    try:
        zodiac, line = scrape_target(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "猪狗"
    assert line == "191期四字平特【猪朋狗友】开00准"


def test_atomic_write_text_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "result.txt"
    path.write_text("old", encoding="utf-8")
    monkeypatch.setattr(zodiac_scraper.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("disk")))

    with pytest.raises(OSError, match="disk"):
        zodiac_scraper.atomic_write_text(path, "new")

    assert path.read_text(encoding="utf-8") == "old"


def test_run_writes_cache_update_failure_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(zodiac_scraper, "OUTPUT_DIR", tmp_path)
    target = Target("https://x", "top", "测试目录", "成语平特")
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_text",
        lambda *_args, **_kwargs: (
            "191期:测试目录【成语平特】\n191期成语平特【牛气冲天】开00准"
        ),
    )
    monkeypatch.setattr(zodiac_scraper, "update_recent_10_cache", lambda *_args: False)

    assert zodiac_scraper.run("191", None, 1) == 0
    failure = tmp_path / f"{zodiac_scraper.date_label()}平特肖-失败.txt"
    assert "recent_10_cache.json 更新失败" in failure.read_text(encoding="utf-8")


def test_header_section_without_header_does_not_report_candidate_conflict():
    target = Target("https://x", "top", "目标", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        zodiac, line, reason = zodiac_scraper.scrape_target_diagnostic(
            target,
            "191",
            "191期平特一肖【虎】开00准\n191期平特一肖【牛】开00准",
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None
    assert reason is None


def test_missing_target_issue_reason_reports_available_issue():
    target = Target("https://x", "top", "水果奶奶", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [
        {
            **strict_special_rule(target, "anchored_section"),
            "section_anchor": "水果奶奶【平特一肖】",
            "section_end": "水果奶奶【绝杀一合】",
        }
    ]
    text = "\n".join(
        [
            "水果奶奶【平特一肖】",
            "192期 平特一肖【龙】开00准",
            "水果奶奶【绝杀一合】",
            "191期 平特一肖【虎】开00准",
        ]
    )

    try:
        reason = zodiac_scraper.missing_target_issue_reason(text, target, "191")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert reason == "目标目录/栏目存在，但页面没有指定的191期；当前可见期数：192期"


def test_real_config_invariants_remain_locked():
    assert len(zodiac_scraper.TARGETS) == 236
    assert len(zodiac_scraper.SPECIAL_PARSE_TARGETS) == 236
    assert all("bbs02.836280.cyou/bbs/topic.php?id=18055" not in target.url for target in zodiac_scraper.TARGETS)
    assert all(target.name != "嘻嘻哈哈" for target in zodiac_scraper.TARGETS)
    assert all(target.name != "福州高手" for target in zodiac_scraper.TARGETS)
    assert len({target.name for target in zodiac_scraper.TARGETS}) == 236
    assert all(
        sum(zodiac_scraper.special_parse_rule_matches(rule, target) for rule in zodiac_scraper.SPECIAL_PARSE_TARGETS) == 1
        for target in zodiac_scraper.TARGETS
    )
    for target in zodiac_scraper.TARGETS:
        rule = next(
            item for item in zodiac_scraper.SPECIAL_PARSE_TARGETS
            if zodiac_scraper.special_parse_rule_matches(item, target)
        )
        assert rule["url_contains"] == target.url
        assert rule["issue_format"] == "arabic_issue_exact"
        assert rule["data_structure"] == zodiac_scraper.DATA_STRUCTURE_BY_MODE[rule["mode"]]
        assert rule["section_boundary"] == zodiac_scraper.SECTION_BOUNDARY_BY_MODE[rule["mode"]]
        assert rule["source_strategy"] in zodiac_scraper.ALLOWED_SOURCE_STRATEGIES
        if rule["source_strategy"] == "browser_main":
            assert rule["frame_scope"] == "main"
            assert rule["browser_selector"] == "body"


def test_archived_site_is_removed_from_active_targets_rules_and_cache():
    archive_path = Path(__file__).with_name("archived_targets.json")
    archive = json.loads(archive_path.read_text(encoding="utf-8-sig"))
    archived = next(item for item in archive["sites"] if item["name"] == "锦绣前程")

    assert archived["url"] == "https://znnpwd.p42g1-zqmsb-jjrsfg.xyz:16677/topic/572223.html"
    assert archived["position"] == "top"
    assert archived["keyword"] == "平特一肖"
    assert archived["evidence"]["issue"] == "207"
    assert archived["evidence"]["zodiacs"] == "猴猪蛇龙羊"
    assert archived["evidence"]["matched_line"] == "207期【平特五肖】【猴猪蛇龙羊】开00准"

    assert all(target.name != "锦绣前程" for target in zodiac_scraper.TARGETS)
    assert all(
        rule.get("name") != "锦绣前程"
        and rule.get("url_contains") != archived["url"]
        for rule in zodiac_scraper.SPECIAL_PARSE_TARGETS
    )

    cache = json.loads(Path(__file__).with_name("recent_10_cache.json").read_text(encoding="utf-8-sig"))
    assert all(site["name"] != "锦绣前程" for site in cache["sites"])


def test_dream_snow_uses_dedicated_top_section_parser():
    target = next(item for item in zodiac_scraper.TARGETS if item.name == "梦幻之雪")
    assert target == Target(
        "https://rmrcjqk.6ln2t-46k8t-kuthoe.xyz:16677/topic/267365.html",
        "top",
        "梦幻之雪",
        "平特壹肖",
    )
    assert zodiac_scraper.special_parse_mode(target) == "anchored_section"
    text = "\n".join(
        [
            "193期: 梦幻之雪《平特壹肖》奇迹发生",
            "193期《平特壹肖》《虎》开00准",
            "192期《平特壹肖》《狗》开45准",
            "191期《平特壹肖》《猴》开29错",
            "193期: 海枯石烂《发财四肖》免费公开",
            "192期《平特壹肖》《马》开00准",
        ]
    )

    zodiac, line, reason = zodiac_scraper.scrape_target_diagnostic(target, "192", text)

    assert (zodiac, line, reason) == ("狗", "192期《平特壹肖》《狗》开45准", None)


def test_vue_forum_html_is_split_and_reduced_to_exact_issue(monkeypatch):
    url = "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/1491"
    target = Target(url, "top", "免费门", "平特①肖")
    payload = [{
        "id": 9,
        "user_id": 1491,
        "draw": 191,
        "status": "published",
        "user": {"id": 1491, "nickname": "免费门"},
        "title": "平特一肖",
        "content": (
            "<p><span>191期</span><span>平特①肖</span><span>〖鸡鸡鸡〗开00准</span></p>"
            "<p><span>190期</span><span>平特①肖</span><span>〖虎虎虎〗开29准</span></p>"
        ),
    }]
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    rule = strict_special_rule(target, "header_section")
    rule["source_strategy"] = "dynamic_record"
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args: json.dumps(payload, ensure_ascii=False))
    try:
        text = zodiac_scraper.fetch_vue_hash_text(url, 1, "191")
        zodiac, line = scrape_target(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert "191期平特①肖〖鸡鸡鸡〗开00准" in text
    assert "190期" not in text
    assert zodiac == "鸡"
    assert line == "191期平特①肖〖鸡鸡鸡〗开00准"


def test_header_section_uses_latest_title_as_boundary_for_historical_issue():
    target = Target("https://x/topic/654109.html", "tail", "碎风漫卷", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "\n".join([
            "192期【平特一肖】已公开",
            "碎风漫卷 发表于 07月10日 22:49:55",
            "190期 46-14-19-37-48-29 T16+09=狗×",
            "191期 19-43-39-24-16-26 T29+09=猴√",
            "192期 平特猴",
            ".down9898{padding:3px}",
            "191期:龙聚天下【绝杀半波】",
        ])
        zodiac, line = scrape_target(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "猴"
    assert line.endswith("=猴√")


def test_header_section_rejects_cross_directory_promotion_title():
    target = Target("https://x/topic/453057.html", "top", "东山再起", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "\n".join([
            "192期:东山再起【成语平特】独家提供",
            "作者:东山再起",
            "191期：成语平特【猪朋狗友】开29错",
            ".advert img{vertical-align:bottom}",
            "191期:龙聚天下【绝杀半波】",
        ])
        zodiac, line = scrape_target(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "猪狗"
    assert "绝杀半波" not in line


def test_promotional_directory_line_is_not_a_result_candidate():
    assert extract_zodiac("191期: 牛头马面【平特一肖】→绝密数据") is None


def test_header_section_keeps_bare_equal_zodiac_result():
    target = Target("https://x", "tail", "无字之思", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "\n".join([
            "192期【平特走势】【平特一肖】已公开",
            "无字之思 发表于 04月29日 16:55:28",
            "191期 19-43-39-24-16-26T29 +00=羊✓",
            ".context_switch {font-size:15px}",
            "191期: 牛头马面【平特一肖】→绝密数据",
        ])
        zodiac, line = scrape_target(target, "191", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac == "羊"
    assert line.endswith("=羊✓")


def test_header_section_stops_at_dedicated_end_text_before_other_document():
    target = Target("https://x/topic/238135.html", "tail", "轻虑浅谋", "四字平特")
    rule = strict_special_rule(target, "header_section")
    rule["section_end_text"] = "博彩必备"
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        text = "\n".join([
            "平特帖201期:【四字平特】",
            "作者:轻虑浅谋",
            "201期：四字平特（鼠肚鸡肠）开：00准",
            "★★ 博彩必备★★",
            "201期：一肖 猪 开：猪32中",
            "201期：平肖 蛇 开：蛇38中",
        ])
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("鼠鸡", "201期：四字平特（鼠肚鸡肠）开：00准", None)


def test_exact_anchored_section_ignores_earlier_keyword_reference():
    target = Target("https://x/", "top", "智能成语", "成语平特")
    rule = strict_special_rule(target, "anchored_section")
    rule.update(
        {
            "section_anchor": "成语平特",
            "section_end": "谜语平特",
            "line_keyword": "成语平特",
            "section_anchor_exact": True,
            "section_end_exact": True,
        }
    )
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        text = "\n".join(
            [
                "202期【成语平特】推荐",
                "200期:平特一肖【虎虎虎】开:虎05准",
                "成语平特",
                "200期:成语平特【蛇鼠一窝】开:鼠43准",
                "谜语平特",
                "201期谜语平特-地痞猪狗让三分-开猪32准",
            ]
        )
        result = zodiac_scraper.scrape_target_diagnostic(target, "200", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("蛇鼠", "200期:成语平特【蛇鼠一窝】开:鼠43准", None)


def test_exact_anchored_section_does_not_borrow_missing_issue_from_previous_section():
    target = Target("https://x/", "top", "智能谜语", "谜语平特")
    rule = strict_special_rule(target, "anchored_section")
    rule.update(
        {
            "section_anchor": "谜语平特",
            "section_end": "平特组合三连尾",
            "line_keyword": "谜语平特",
            "section_anchor_exact": True,
            "section_end_exact": True,
        }
    )
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        text = "\n".join(
            [
                "成语平特",
                "200期:成语平特【蛇鼠一窝】开:鼠43准",
                "谜语平特",
                "201期谜语平特-地痞猪狗让三分-开猪32准",
                "199期谜语平特-大地草原牛马欢-开牛42准",
                "平特组合三连尾",
            ]
        )
        result = zodiac_scraper.scrape_target_diagnostic(target, "200", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, None)


def test_target_image_urls_uses_target_forum_content_image_without_issue_text():
    target = Target("https://x/topic/385412.html", "tail", "赌神平特", "赌神平特")
    page = """
    <div class="detail_info_forum2_item">
      <div class="forum-head">192期【赌神平特】规律</div>
      <div class="forum-body"><img data-original="/avatar.png">
        <div class="content"><p><img data-original="/result.png"></p></div>
      </div>
    </div>
    <div class="advert"><img data-original="/ad.png"></div>
    """

    assert zodiac_scraper.target_image_urls(page, target, "191") == ["/result.png"]


def test_red_image_parser_locks_to_requested_issue_row_above_red_advertisement():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (560, 560), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 32)
    draw.text((180, 300), "201期：牛", font=font, fill=(255, 0, 0))
    draw.rectangle((360, 500, 559, 559), fill=(255, 0, 0))
    draw.text((430, 512), "广告", font=font, fill="white")
    output = BytesIO()
    image.save(output, format="PNG")

    assert zodiac_scraper.extract_red_issue_zodiac_from_encrypted_image(output.getvalue(), "201") == "牛"


def test_label_image_parser_reads_exact_black_history_row_and_ignores_red_numbers():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (560, 260), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24)
    draw.text((0, 40), "199期: 17 49 42 45 05 38+36 公式:+1 下期:龙√", font=font, fill="black")
    draw.text((0, 90), "200期: 43 46 05 32 35", font=font, fill="black")
    draw.text((238, 90), "29", font=font, fill=(255, 0, 0))
    draw.text((266, 90), "+39 公式:+1 下期:牛√", font=font, fill="black")
    output = BytesIO()
    image.save(output, format="PNG")

    assert zodiac_scraper.extract_issue_zodiac_from_label_image(output.getvalue(), "200") == "牛"
    assert zodiac_scraper.extract_issue_zodiac_from_label_image(output.getvalue(), "198") is None


def test_decode_data_image_uri_accepts_only_base64_images():
    raw = b"\x89PNG\r\n\x1a\nimage"
    uri = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")

    assert zodiac_scraper.decode_data_image_uri(uri) == raw
    assert zodiac_scraper.decode_data_image_uri("data:text/plain;base64,SGVsbG8=") is None
    assert zodiac_scraper.decode_data_image_uri("https://example.test/result.png") is None


def test_ai_public_label_reports_same_issue_candidate_conflict():
    target = Target("https://x/", "top", "智能平特", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "ai_public_label")]
    try:
        text = "\n".join(
            [
                "AAAAA级大公开201期",
                "平特一肖：猪猪猪",
                "平特一肖：蛇蛇蛇",
                "AAAAA级大公开200期",
                "平特一肖：牛牛牛",
            ]
        )
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, "同一目标文档出现不同生肖候选：猪、蛇")


def test_followup_label_reports_same_issue_candidate_conflict():
    target = Target("https://x/topic/1.html", "top", "AI平特一肖", "AI推荐平特")
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    old_labels = zodiac_scraper.SPECIAL_FOLLOWUP_LABELS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "followup_label")]
    zodiac_scraper.SPECIAL_FOLLOWUP_LABELS = {target.url: "平特一肖"}
    try:
        text = "\n".join(
            [
                "201期【AI推荐平特】开000中",
                "平特一肖：鼠鼠鼠",
                "平特一肖：牛牛牛",
                "200期【AI推荐平特】开000中",
            ]
        )
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules
        zodiac_scraper.SPECIAL_FOLLOWUP_LABELS = old_labels

    assert result == (None, None, "同一目标文档出现不同生肖候选：鼠、牛")


def test_next_line_parser_reports_same_issue_candidate_conflict():
    target = Target("https://x/topic/1.html", "top", "山涧晴岚", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "next_line_zodiac")]
    try:
        text = "\n".join(
            [
                "201期:山涧晴岚【平特一肖】",
                "201期: 平特一肖 【虎】 开 00 准",
                "201期:山涧晴岚【平特一肖】",
                "201期: 平特一肖 【牛】 开 00 准",
            ]
        )
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, "同一目标文档出现不同生肖候选：虎、牛")


def test_header_section_rejects_multiple_keyword_headers_without_target_identity():
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "\n".join(
            [
                "201期:其他作者【成语平特】",
                "201期成语平特【虎虎生威】开00准",
                "201期:另一作者【成语平特】",
                "201期成语平特【牛气冲天】开00准",
            ]
        )
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, None)


def test_header_section_without_header_never_scans_whole_document():
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        unrelated = "201期成语平特【虎虎生威】开00准"
        owned = "\n".join(["目标目录", "201期成语平特【牛气冲天】开00准"])
        direct_result = zodiac_scraper.scrape_target_diagnostic(target, "201", unrelated)
        owned_result = zodiac_scraper.scrape_target_diagnostic(target, "201", owned)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert direct_result == (None, None, None)
    assert owned_result == (None, None, None)


def test_target_name_zodiac_is_not_used_as_result_data():
    target = Target("https://x/topic/1.html", "top", "龙骧虎步", "四字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    try:
        text = "201期:龙骧虎步【四字平特】开000准"
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, None)


def test_extract_zodiac_rejects_site_promise_with_zodiac_wordplay():
    line = "201期【AI平特一肖】本站承诺拒绝龙套数据开000中"

    assert extract_zodiac(line) is None


def test_linked_topic_rejects_multiple_matching_detail_links(monkeypatch):
    target = Target("https://x/topic/parent.html", "top", "逆天飞翔", "三字平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "linked_topic")]
    monkeypatch.setattr(zodiac_scraper, "fetch_text", lambda *_args, **_kwargs: "detail")
    page = "\n".join(
        [
            '<a href="/topic/1.html">201期 逆天飞翔 三字平特</a>',
            '<a href="/topic/2.html">201期 逆天飞翔 三字平特</a>',
        ]
    )
    try:
        with pytest.raises(RuntimeError, match="关联正文匹配不唯一"):
            zodiac_scraper.fetch_linked_topic_text(target.url, page, 1, "201")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old


def test_browser_image_parser_uses_only_exact_target_section():
    from PIL import Image, ImageDraw, ImageFont

    def image_uri(zodiac: str) -> str:
        image = Image.new("RGB", (560, 400), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 32)
        draw.text((180, 280), f"201期：{zodiac}", font=font, fill=(255, 0, 0))
        output = BytesIO()
        image.save(output, format="PNG")
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")

    target = Target("https://x/topic/385412.html", "tail", "赌神平特", "赌神平特")
    lines, diagnostics = zodiac_scraper.browser_image_issue_lines_from_sections(
        [
            ("202期【赌神平特】规律", [image_uri("牛")]),
            ("202期【其他资料】规律", [image_uri("鸡")]),
        ],
        [target],
        "201",
    )

    assert lines == ["赌神平特 201期：牛"]
    assert diagnostics == []


def test_browser_image_parser_rejects_same_section_conflict():
    from PIL import Image, ImageDraw, ImageFont

    def image_uri(zodiac: str) -> str:
        image = Image.new("RGB", (560, 400), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 32)
        draw.text((180, 280), f"201期：{zodiac}", font=font, fill=(255, 0, 0))
        output = BytesIO()
        image.save(output, format="PNG")
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")

    target = Target("https://x/topic/385412.html", "tail", "赌神平特", "赌神平特")
    lines, diagnostics = zodiac_scraper.browser_image_issue_lines_from_sections(
        [("202期【赌神平特】规律", [image_uri("牛"), image_uri("鸡")])],
        [target],
        "201",
    )

    assert lines == []
    assert diagnostics == ["赌神平特：目标正文图片内同一期出现不同生肖：牛、鸡"]


def test_primary_document_ignores_conflicting_legacy_embedded_document():
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    text = zodiac_scraper.serialize_source_documents(
        [
            zodiac_scraper.SourceDocument(
                source="http-main",
                source_url=target.url,
                primary=True,
                text="201期:目标目录【成语平特】\n201期成语平特【虎虎生威】开00准",
            ),
            zodiac_scraper.SourceDocument(
                source="embedded-old",
                source_url="https://x/old.html",
                primary=False,
                text="201期:目标目录【成语平特】\n201期成语平特【牛气冲天】开00准",
            ),
        ]
    )
    try:
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("虎", "201期成语平特【虎虎生威】开00准", None)


def test_multiple_embedded_target_documents_are_ambiguous_without_primary_match():
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    text = zodiac_scraper.serialize_source_documents(
        [
            zodiac_scraper.SourceDocument("http-shell", target.url, True, "正在加载"),
            zodiac_scraper.SourceDocument(
                "script-current", target.url, False,
                "201期:目标目录【成语平特】\n201期成语平特【虎虎生威】开00准",
            ),
            zodiac_scraper.SourceDocument(
                "script-old", target.url, False,
                "201期:目标目录【成语平特】\n201期成语平特【牛气冲天】开00准",
            ),
        ]
    )
    try:
        zodiac, line, reason = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None
    assert reason == "跨文档出现多个目标候选，文档边界不明确：虎、牛"


def test_selected_primary_document_same_issue_conflict_still_fails():
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    text = zodiac_scraper.serialize_source_documents(
        [
            zodiac_scraper.SourceDocument(
                "browser-main", target.url, True,
                "\n".join([
                    "201期:目标目录【成语平特】",
                    "201期成语平特【虎虎生威】开00准",
                    "201期成语平特【牛气冲天】开00准",
                ]),
            )
        ]
    )
    try:
        zodiac, line, reason = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert zodiac is None
    assert line is None
    assert reason == "同一目标文档出现不同生肖候选：虎、牛"


def test_fetch_text_does_not_merge_visible_current_document_with_old_encoded_document(monkeypatch):
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    old_html = "<div>201期:目标目录【成语平特】</div><div>201期成语平特【牛气冲天】开00准</div>"
    encoded = base64.b64encode(old_html.encode()).decode()
    page = (
        "<div>201期:目标目录【成语平特】</div>"
        "<div>201期成语平特【虎虎生威】开00准</div>"
        f'<script>document.writeln(strdecode("{encoded}"));</script>'
    )
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "nearest_keyword_line")]
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args, **_kwargs: page)
    try:
        text = zodiac_scraper.fetch_text(target.url, 1, "201")
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("虎", "201期成语平特【虎虎生威】开00准", None)


def test_run_uses_browser_dom_for_http_shell_and_same_dedicated_parser(tmp_path, monkeypatch):
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    output = tmp_path / "result.txt"
    browser_calls = []
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(zodiac_scraper, "fetch_raw", lambda *_args, **_kwargs: "<html><body>正在加载</body></html>")

    def browser_fetch(targets, timeout, issue=None):
        browser_calls.append((list(targets), timeout, issue))
        return {
            target.url: "201期:目标目录【成语平特】\n201期成语平特【虎虎生威】开00准"
        }, {}

    monkeypatch.setattr(zodiac_scraper, "fetch_browser_texts", browser_fetch)

    assert zodiac_scraper.run("201", output, 1, update_cache=False) == 0
    assert browser_calls == [([target], 1, "201")]
    assert output.read_text(encoding="utf-8") == "虎 目标目录\n\n排行榜\n虎 1\n"
    assert output.with_suffix(".errors.txt").read_text(encoding="utf-8") == ""


def test_run_does_not_use_browser_to_override_same_document_conflict(tmp_path, monkeypatch):
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    output = tmp_path / "result.txt"
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_raw",
        lambda *_args, **_kwargs: (
            "<div>201期:目标目录【成语平特】</div>"
            "<div>201期成语平特【虎虎生威】开00准</div>"
            "<div>201期成语平特【牛气冲天】开00准</div>"
        ),
    )
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_browser_texts",
        lambda *_args, **_kwargs: pytest.fail("同一文档冲突不能用浏览器覆盖"),
    )

    assert zodiac_scraper.run("201", output, 1, update_cache=False) == 1
    assert "同一目标文档出现不同生肖候选：虎、牛" in output.with_suffix(".errors.txt").read_text(encoding="utf-8")


def test_audit_mode_never_writes_cache_or_txt(tmp_path, monkeypatch):
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    output = tmp_path / "audit" / "result.txt"
    cache_path = tmp_path / "recent_10_cache.json"
    cache_path.write_text("cache-sentinel", encoding="utf-8")
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_raw",
        lambda *_args, **_kwargs: (
            "<div>201期:目标目录【成语平特】</div>"
            "<div>201期成语平特【虎虎生威】开00准</div>"
        ),
    )

    assert zodiac_scraper.run("201", output, 1, audit=True) == 0
    assert cache_path.read_text(encoding="utf-8") == "cache-sentinel"
    assert not output.parent.exists()


@pytest.mark.parametrize(
    ("position", "text"),
    [
        (
            "top",
            "\n".join([
                "目标目录", "202期成语平特【虎虎生威】开00准",
                "目标目录", "201期成语平特【牛气冲天】开00准",
            ]),
        ),
        (
            "tail",
            "\n".join([
                "目标目录", "201期成语平特【牛气冲天】开00准",
                "目标目录", "202期成语平特【虎虎生威】开00准",
            ]),
        ),
    ],
)
def test_named_section_position_is_a_hard_boundary(position, text):
    target = Target("https://x/topic/1.html", position, "目标目录", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "named_section")]
    try:
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("牛", "201期成语平特【牛气冲天】开00准", None)


def test_run_rejects_same_issue_cache_conflict_without_overwriting_history(tmp_path, monkeypatch):
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    output = tmp_path / "result.txt"
    cache_path = tmp_path / "recent_10_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "window_size": 10,
                "issues": [201],
                "sites": [
                    {
                        "name": target.name,
                        "url": target.url,
                        "position": target.position,
                        "keyword": target.keyword,
                        "values": {"201": "猪"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(zodiac_scraper, "TARGETS", [target])
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)
    monkeypatch.setattr(zodiac_scraper, "SPECIAL_PARSE_TARGETS", [strict_special_rule(target, "header_section")])
    monkeypatch.setattr(
        zodiac_scraper,
        "fetch_raw",
        lambda *_args, **_kwargs: (
            "<div>201期:目标目录【成语平特】</div>"
            "<div>201期成语平特【虎虎生威】开00准</div>"
        ),
    )

    assert zodiac_scraper.run("201", output, 1) == 1
    assert output.read_text(encoding="utf-8") == ""
    failure = output.with_suffix(".errors.txt").read_text(encoding="utf-8")
    assert "历史缓存同一期数据冲突：缓存猪，当前虎" in failure
    assert "历史解析错误或源站内容变更待确认" in failure
    cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    assert cache["sites"][0]["values"]["201"] == "猪"


def test_cache_update_refuses_late_same_issue_conflict(tmp_path, monkeypatch):
    target = Target("https://x/topic/1.html", "top", "目标目录", "成语平特")
    cache_path = tmp_path / "recent_10_cache.json"
    cache_path.write_text(
        json.dumps({"schema": 1, "issues": [], "sites": []}, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(zodiac_scraper, "RECENT_10_CACHE_PATH", cache_path)

    assert zodiac_scraper.update_recent_10_cache(
        [target], {zodiac_scraper.target_cache_key(target): "虎"}, "201"
    )
    assert not zodiac_scraper.update_recent_10_cache(
        [target], {zodiac_scraper.target_cache_key(target): "牛"}, "201"
    )

    cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    assert cache["sites"][0]["values"]["201"] == "虎"


def test_real_wide_scan_targets_are_bound_to_verified_sections():
    expected = {
        "无敌金刚": ("anchored_section", "无敌金刚《两字平特》奔向富豪", "特码专区"),
        "满堂红第一": ("anchored_section", "澳门满堂红【平特一肖】", "澳门满堂红【三肖中特】"),
        "满堂红第二": ("anchored_section", "澳门满堂红【平特一肖】经典推出", "站长宣言"),
        "满堂红第三": ("anchored_formula_section", "期:【平特一肖】", "站长宣言"),
        "红袖添香": ("anchored_section", "作者：红袖添香", "Copyright ©水果奶奶 Reserved"),
        "一盏琉璃": ("anchored_section", "作者： 一盏琉璃", "Copyright ©水果奶奶 Reserved"),
        "锦离鸢墨": ("anchored_formula_section", "锦离鸢墨【平特一肖】独家公式", "★★ 博彩必备★★"),
        "独家发表": ("anchored_section", "独家发表【④字平特】", "上一篇："),
        "空中飞翔": ("anchored_section", "作者:空中飞翔", "★★ 博彩必备★★"),
        "一点红": ("anchored_section", "澳门一点红【平特一肖】准准", "点击投注港澳六合彩鸿蒙娱乐城"),
        "东方红": ("anchored_section", "平特一肖", "四尾八码"),
        "状元红": ("anchored_section", "狀元紅⊙『平特一肖』", "永久域名:"),
        "彩民书籍": ("anchored_section", "澳门彩民书籍『平特一肖』", "澳门彩民书籍『18码中特』"),
    }
    rules = {item["name"]: item for item in zodiac_scraper.CONFIG["special_parse_targets"]}

    for name, (mode, anchor, end) in expected.items():
        rule = rules[name]
        assert rule["mode"] == mode
        assert rule["section_anchor"] == anchor
        assert rule["section_end"] == end

    for name in ("山涧晴岚",):
        assert rules[name]["mode"] == "named_section"


def test_current_failure_sites_have_site_specific_boundaries_and_formats():
    rules = {item["name"]: item for item in zodiac_scraper.CONFIG["special_parse_targets"]}

    assert rules["心之所向"]["mode"] == "anchored_section"
    assert rules["心之所向"]["section_anchor"] == "作者：心之所向"
    assert rules["心之所向"]["section_end"] == "Copyright ©水果奶奶 Reserved"

    assert rules["雄霸六合"]["mode"] == "anchored_section"
    assert rules["雄霸六合"]["section_anchor"] == "雄霸六合「平特二肖」独家提供"
    assert rules["雄霸六合"]["section_end"] == "★★ 博彩必备★★"

    assert rules["阳春三月"]["result_line_format"] == "compact_zodiac_suffix"
    assert rules["阳春三月"]["result_marker_required"] is True
    assert rules["条分缕析"]["result_line_format"] == "compact_zodiac_suffix"
    assert rules["条分缕析"]["result_prefix"] == "平"
    assert rules["条分缕析"]["result_marker_required"] is False


@pytest.mark.parametrize(
    ("name", "line", "expected"),
    [
        ("阳春三月", "207期猴龙肖√", "猴龙"),
        ("条分缕析", "207期 平虎牛肖", "虎牛"),
    ],
)
def test_compact_author_result_lines_are_parsed_inside_their_boundaries(name, line, expected):
    target = next(item for item in zodiac_scraper.TARGETS if item.name == name)
    rule = {
        **zodiac_scraper.special_parse_rule(target),
        "result_line_format": "compact_zodiac_suffix",
        "result_suffix": "肖",
        "result_marker_required": name == "阳春三月",
        "result_prefix": "平" if name == "条分缕析" else "",
    }
    text = "\n".join(
        [
            "207期: 平特✨走势【平特二肖】13中12",
            f"{name} 发表于 04月27日 15:23:09",
            "206期 09-49-37-03-40-35T47 +2.2=猴√龙√",
            line,
            "上一篇：",
            "207期: 平特✨走势【平特二肖】99中99",
            "旧文档不应进入目标区块",
        ]
    )
    old_rules = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        assert zodiac_scraper.scrape_target_diagnostic(target, "207", text) == (
            expected,
            line,
            None,
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old_rules


def test_current_anchored_sections_select_the_exact_207_result():
    cases = [
        (
            "心之所向",
            "作者：心之所向\n207期： 心之所向★平特一肖★ 【狗】 开 ?? 准\n206期： 心之所向★平特一肖★ 【狗】 开 09 准\nCopyright ©水果奶奶 Reserved",
            "狗",
            "207期： 心之所向★平特一肖★ 【狗】 开 ?? 准",
        ),
        (
            "雄霸六合",
            "207期:雄霸六合「平特二肖」独家提供\n206期平特二肖 〈牛狗〉开09准\n207期平特二肖 〈鼠龙〉开00准\n★★ 博彩必备★★",
            "鼠龙",
            "207期平特二肖 〈鼠龙〉开00准",
        ),
    ]
    for name, text, expected, expected_line in cases:
        target = next(item for item in zodiac_scraper.TARGETS if item.name == name)
        assert zodiac_scraper.scrape_target_diagnostic(target, "207", text) == (
            expected,
            expected_line,
            None,
        )


def test_forest_song_uses_its_exact_author_block_for_209():
    target = next(item for item in zodiac_scraper.TARGETS if item.name == "森林牧歌")
    text = "\n".join(
        [
            "209期:平特一肖[祝您期期大中]",
            "作者：森林牧歌",
            "209期： 森林牧歌★平特一肖★ 【兔】 开 ?? 准",
            "208期： 森林牧歌★平特一肖★ 【鼠】 开 07.19 准",
            "Copyright ©水果奶奶 Reserved",
        ]
    )

    assert zodiac_scraper.scrape_target_diagnostic(target, "209", text) == (
        "兔",
        "209期： 森林牧歌★平特一肖★ 【兔】 开 ?? 准",
        None,
    )
    assert zodiac_scraper.pending_issue_reason(text, target, "209") is None


def test_xiongba_uses_first_complete_anchor_when_footer_repeats_title():
    target = next(item for item in zodiac_scraper.TARGETS if item.name == "雄霸六合")
    text = "\n".join(
        [
            "209期:雄霸六合「平特二肖」独家提供",
            "作者:照萤映雪",
            "208期平特二肖 〈蛇马〉开19错",
            "209期平特二肖 〈狗鼠〉开00准",
            "★★ 博彩必备★★",
            "209期:雄霸六合「平特二肖」独家提供",
            "页面下方导航重复标题，没有目标正文",
        ]
    )

    assert zodiac_scraper.scrape_target_diagnostic(target, "209", text) == (
        "狗鼠",
        "209期平特二肖 〈狗鼠〉开00准",
        None,
    )
    assert zodiac_scraper.scrape_target_diagnostic(target, "208", text) == (
        "蛇马",
        "208期平特二肖 〈蛇马〉开19错",
        None,
    )
    assert zodiac_scraper.pending_issue_reason(text, target, "209") is None


def test_anchored_pending_reason_does_not_cross_into_another_section():
    target = next(item for item in zodiac_scraper.TARGETS if item.name == "彩民书籍")
    text = "\n".join(
        [
            "澳门彩民书籍『平特一肖』",
            "208期平特一肖:[马马马] 开[00]准",
            "207期平特一肖:[龙龙龙] 开[31]错",
            "澳门彩民书籍『18码中特』",
            "209期： 彩民书籍 【平特一肖】 已公开",
        ]
    )

    assert zodiac_scraper.pending_issue_reason(text, target, "209") is None
    assert zodiac_scraper.missing_target_issue_reason(text, target, "209") == (
        "目标目录/栏目存在，但页面没有指定的209期；当前可见期数：208期、207期"
    )


def test_closed_browser_connection_is_retryable_without_changing_source():
    assert zodiac_scraper.retryable_browser_navigation_error(
        RuntimeError("Page.goto: net::ERR_CONNECTION_CLOSED")
    )
    assert not zodiac_scraper.retryable_browser_navigation_error(
        RuntimeError("浏览器最终URL不匹配")
    )


def test_browser_navigation_retries_the_same_url_after_connection_closed():
    class FakePage:
        def __init__(self):
            self.urls = []
            self.waits = []

        async def goto(self, url, **_kwargs):
            self.urls.append(url)
            if len(self.urls) == 1:
                raise RuntimeError("Page.goto: net::ERR_CONNECTION_CLOSED")

        async def wait_for_timeout(self, milliseconds):
            self.waits.append(milliseconds)

    page = FakePage()
    asyncio.run(
        zodiac_scraper.navigate_browser_page_with_retry(
            page,
            "https://fbgbfg.www27521c.com:8443/gsb/am47.html",
            20,
        )
    )

    assert page.urls == [
        "https://fbgbfg.www27521c.com:8443/gsb/am47.html",
        "https://fbgbfg.www27521c.com:8443/gsb/am47.html",
    ]
    assert page.waits == [250]


def test_browser_main_dom_retries_the_same_url_after_empty_document():
    url = "https://yqjfwqsc.1dayz-aetgp-kbjidr.xyz:16677/topic/682000.html"

    class FakeLocator:
        def __init__(self, page):
            self.page = page

        async def inner_text(self, **_kwargs):
            self.page.body_reads += 1
            return "" if self.page.body_reads == 1 else "210期 平特龙肖"

    class FakePage:
        def __init__(self):
            self.url = ""
            self.urls = []
            self.waits = []
            self.body_reads = 0

        async def goto(self, value, **_kwargs):
            self.url = value
            self.urls.append(value)

        async def wait_for_timeout(self, milliseconds):
            self.waits.append(milliseconds)

        def locator(self, _selector):
            return FakeLocator(self)

    page = FakePage()
    body = asyncio.run(zodiac_scraper.fetch_browser_main_text_with_retry(page, url, 20))

    assert body == "210期 平特龙肖"
    assert page.urls == [url, url]
    assert page.body_reads == 2
    assert 250 in page.waits


def test_browser_main_dom_waits_for_site_required_anchor():
    url = "https://dwfoxsuz.ik1v5-stbjb-dsttyy.xyz:16677/"
    anchor = "澳门一点红【平特一肖】准准"
    target = next(item for item in zodiac_scraper.TARGETS if item.name == "一点红")

    assert zodiac_scraper.special_parse_rule(target)["browser_required_anchor"] == anchor

    class FakeLocator:
        def __init__(self, page):
            self.page = page

        async def inner_text(self, **_kwargs):
            self.page.body_reads += 1
            return "页面已加载" if self.page.body_reads == 1 else f"页面已加载\n{anchor}\n210期:〖平特一肖〗【鸡鸡鸡】开00中"

    class FakePage:
        def __init__(self):
            self.url = ""
            self.urls = []
            self.waits = []
            self.body_reads = 0

        async def goto(self, value, **_kwargs):
            self.url = value
            self.urls.append(value)

        async def wait_for_timeout(self, milliseconds):
            self.waits.append(milliseconds)

        def locator(self, _selector):
            return FakeLocator(self)

    page = FakePage()
    body = asyncio.run(
        zodiac_scraper.fetch_browser_main_text_with_retry(
            page,
            url,
            20,
            required_anchors=(anchor,),
        )
    )

    assert anchor in body
    assert page.urls == [url]
    assert page.body_reads == 2
    assert 250 in page.waits


def test_real_ai_blocks_have_explicit_issue_boundaries():
    rules = {item["name"]: item for item in zodiac_scraper.CONFIG["special_parse_targets"]}

    assert rules["智能平特"]["section_anchor"] == "AAAAA级大公开{issue}期"
    assert rules["智能平特"]["section_end"] == "AI智能网:"
    assert rules["AI平特肖"]["section_anchor"] == "{issue}期【AI推荐平特】"
    assert rules["AI平特肖"]["section_end"] == "推荐平码"
    assert rules["AI平特肖"]["followup_label"] == "平特一肖"


def test_previous_direct_scan_sites_use_identity_boundaries():
    rules = {item["name"]: item for item in zodiac_scraper.CONFIG["special_parse_targets"]}
    named = {
        "转眼之间", "博闻茄子", "花仙子", "金聋彩", "无与伦比",
        "一叶报秋", "桃花潭水", "承前启后",
    }
    assert all(rules[name]["mode"] == "named_section" for name in named)
    assert rules["金聋彩"]["section_name"] == "金龙彩"
    assert rules["五彩缤纷"]["mode"] == "anchored_section"
    assert rules["五彩缤纷"]["section_anchor"] == "作者:五彩缤纷"
    assert rules["五彩缤纷"]["section_end"] == "{issue}期"
    assert rules["五彩缤纷"]["section_end_exact"] is True


def test_real_special_identity_and_homepage_boundaries_are_explicit():
    rules = {item["name"]: item for item in zodiac_scraper.CONFIG["special_parse_targets"]}

    assert rules["凤毛聋甲"]["section_name"] == "凤毛龙甲"
    assert rules["平特一肖"]["mode"] == "anchored_section"
    assert rules["平特一肖"]["section_anchor"] == "澳门平特一肖网 『妙解平特一肖』"
    assert rules["平特一肖"]["section_end"] == "澳门平特一肖网 『规律一尾』"
    assert rules["赢两千万"]["mode"] == "anchored_section"
    assert rules["赢两千万"]["section_anchor"] == "作者:永永无穷"
    assert rules["赢两千万"]["section_end"] == "★★ 博彩必备★★"


def test_named_section_uses_configured_identity_alias_without_zodiac_pollution():
    target = Target("https://x/topic/1.html", "top", "金聋彩", "平特一肖")
    rule = strict_special_rule(target, "named_section")
    rule["section_name"] = "金龙彩"
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        result = zodiac_scraper.scrape_target_diagnostic(
            target,
            "201",
            "201期:金龙彩★平特一肖≦(马马马)≧开:00准\n"
            "200期:金龙彩★平特一肖≦(羊羊羊)≧开:39错",
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("马", "201期:金龙彩★平特一肖≦(马马马)≧开:00准", None)


def test_header_section_uses_configured_identity_alias_to_select_one_header():
    target = Target("https://x/topic/1.html", "top", "凤毛聋甲", "成语平特")
    rule = strict_special_rule(target, "header_section")
    rule["section_name"] = "凤毛龙甲"
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    text = "\n".join(
        [
            "202期:其他作者【成语平特】",
            "201期成语平特【牛气冲天】开00准",
            "202期:凤毛龙甲【成语平特】",
            "作者:凤毛龙甲",
            "201期成语平特【龙争虎斗】开32错",
        ]
    )
    try:
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("龙虎", "201期成语平特【龙争虎斗】开32错", None)


def test_anchored_homepage_section_does_not_use_other_same_keyword_modules():
    target = Target("https://x/", "top", "平特一肖", "平特一肖")
    rule = strict_special_rule(target, "anchored_section")
    rule.update(
        {
            "section_anchor": "澳门平特一肖网 『妙解平特一肖』",
            "section_end": "澳门平特一肖网 『规律一尾』",
        }
    )
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    text = "\n".join(
        [
            "201期:其他栏目【平特一肖】开虎00准",
            "澳门平特一肖网 『妙解平特一肖』",
            "201期：(平特一肖)蛇蛇蛇",
            "澳门平特一肖网 『规律一尾』",
            "201期:另一栏目【平特一肖】开牛00准",
        ]
    )
    try:
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("蛇", "201期：(平特一肖)蛇蛇蛇", None)


def test_missing_target_issue_reason_uses_named_section_alias_and_boundary():
    target = Target("https://x/topic/1.html", "top", "金聋彩", "平特一肖")
    rule = strict_special_rule(target, "named_section")
    rule["section_name"] = "金龙彩"
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    text = "\n".join(
        [
            "金龙彩 平特一肖",
            "200期:金龙彩★平特一肖≦(羊羊羊)≧开:39错",
            "作者:其他栏目",
            "201期:其他栏目★平特一肖≦(虎虎虎)≧开:00准",
        ]
    )
    try:
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
        reason = zodiac_scraper.missing_target_issue_reason(text, target, "201")
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, None)
    assert reason == "目标目录/栏目存在，但页面没有指定的201期；当前可见期数：200期"


def test_header_section_stops_at_new_author_after_any_visible_issue():
    target = Target("https://x/topic/1.html", "top", "目标", "平特一肖")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    text = "\n".join(
        [
            "目标【平特一肖】",
            "200期 平特一肖【羊】开39错",
            "作者:其他栏目",
            "201期 平特一肖【虎】开00准",
        ]
    )
    try:
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, None)


def test_header_section_allows_metadata_after_issue_bearing_header():
    target = Target("https://x/topic/1.html", "top", "目标", "成语平特")
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [strict_special_rule(target, "header_section")]
    text = "\n".join(
        [
            "202期:目标【成语平特】",
            "发表于 07月20日 23:53:55",
            "202期成语平特【牛气冲天】开00准",
            "201期成语平特【虎虎生威】开00准",
        ]
    )
    try:
        result = zodiac_scraper.scrape_target_diagnostic(target, "201", text)
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == ("虎", "201期成语平特【虎虎生威】开00准", None)


def test_ai_public_label_requires_configured_end_boundary():
    target = Target("https://x/", "top", "智能平特", "平特一肖")
    rule = strict_special_rule(target, "ai_public_label")
    rule.update({
        "section_anchor": "AAAAA级大公开{issue}期",
        "section_end": "AI智能网:",
    })
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        result = zodiac_scraper.scrape_target_diagnostic(
            target,
            "201",
            "AAAAA级大公开201期\n平特一肖：虎虎虎\n下一栏目",
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert result == (None, None, None)


def test_followup_label_requires_exact_configured_issue_block():
    target = Target("https://x/topic/1.html", "top", "AI平特一肖", "AI推荐平特")
    rule = strict_special_rule(target, "followup_label")
    rule.update({
        "section_anchor": "{issue}期【AI推荐平特】",
        "section_end": "推荐平码",
        "followup_label": "平特一肖",
    })
    old = zodiac_scraper.SPECIAL_PARSE_TARGETS
    zodiac_scraper.SPECIAL_PARSE_TARGETS = [rule]
    try:
        good = zodiac_scraper.scrape_target_diagnostic(
            target,
            "201",
            "201期【AI推荐平特】开00中\n平特一肖：鼠鼠鼠\n推荐平码【07.19.31.43】",
        )
        missing_end = zodiac_scraper.scrape_target_diagnostic(
            target,
            "201",
            "201期【AI推荐平特】开00中\n平特一肖：牛牛牛\n下一栏目",
        )
    finally:
        zodiac_scraper.SPECIAL_PARSE_TARGETS = old

    assert good == ("鼠", "平特一肖：鼠鼠鼠", None)
    assert missing_end == (None, None, None)



