"""单期结果生肖个数上限回归测试（用户定口径：2026-11-13 由 2 放宽到 3，2026-11-15 由 3 放宽到 4）。

覆盖三条独立判定路径，避免只放宽其中一处导致「校验过了但写不进 TXT」：
  1. 统一校验器 `pingte/validation/result.py` 的 `_finish`；
  2. 成功 TXT 读写 `pingte/storage/output.py` 的 `_success_record`；
  3. 新增站点校验 `pingte/application/onboarding.py` 的 `normalize_values`。

5 肖及以上仍必须失败，不能把多肖栏目当成平特结果。
"""
from __future__ import annotations

import pytest

from pingte.application.onboarding import OnboardingError, normalize_values
from pingte.domain.zodiac import MAX_RESULT_ZODIACS
from pingte.storage.output import build_output, merge_success_output


def test_limit_constant_is_four():
    assert MAX_RESULT_ZODIACS == 4


@pytest.mark.parametrize("zodiac", ["蛇鼠", "羊牛虎", "兔虎猴鼠"])
def test_success_record_accepts_up_to_four(zodiac: str):
    merged = merge_success_output(build_output(["鼠 原有"]), [f"{zodiac} 新站"])
    assert f"{zodiac} 新站" in merged.split("\n排行榜\n")[0].splitlines()


def test_success_record_rejects_five():
    with pytest.raises(ValueError, match="成功TXT生肖无效"):
        merge_success_output(build_output(["鼠 原有"]), ["兔虎猴鼠牛 新站"])


def test_success_record_rejects_duplicate_chars():
    with pytest.raises(ValueError, match="成功TXT生肖无效"):
        merge_success_output(build_output(["鼠 原有"]), ["羊羊 新站"])


def test_onboarding_accepts_four():
    assert normalize_values({"319": "羊蛇猴猪"}) == {"319": "羊蛇猴猪"}


def test_onboarding_rejects_five():
    with pytest.raises(OnboardingError):
        normalize_values({"319": "羊蛇猴猪牛"})


def test_ranking_counts_each_zodiac_separately():
    text = build_output(["羊牛虎 三肖站", "羊 一肖站"])
    ranking = text.split("\n排行榜\n")[1].splitlines()
    assert "羊 2" in ranking
    assert "牛 1" in ranking
    assert "虎 1" in ranking


# ---------------------------------------------------------------- 统一校验器

from pingte.domain.models import Candidate, SourceDocument, TargetProfile
from pingte.validation.result import _finish


def _candidate(zodiac: str, rule_keyword: str = "平特玄机") -> Candidate:
    return Candidate(
        target_id="PT-9902",
        issue="319",
        zodiac=zodiac,
        raw_line=f"319期【{zodiac}出风头】开00.00准",
        source="browser-main",
        source_url="https://example.test/topic/1.html",
    )


def _finish_outcome(zodiac: str):
    target = TargetProfile(
        url="https://example.test/topic/1.html",
        position="top",
        name="上限测试站",
        keyword="平特玄机",
        target_id="PT-9902",
        rule_version=1,
    )
    document = SourceDocument(
        source="browser-main",
        source_url=target.url,
        primary=True,
        text=f"319期【{zodiac}出风头】开00.00准",
    )
    return _finish(target, document, [_candidate(zodiac)], "319")


def test_validator_accepts_four_zodiacs():
    outcome = _finish_outcome("羊蛇猴猪")
    assert outcome.ok is True
    assert outcome.zodiac == "羊蛇猴猪"


def test_validator_rejects_five_zodiacs():
    outcome = _finish_outcome("羊蛇猴猪牛")
    assert outcome.ok is False
    assert outcome.failure is not None
    assert "超过4个" in outcome.failure.message
