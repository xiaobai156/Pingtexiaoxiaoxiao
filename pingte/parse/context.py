from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pingte.domain.models import TargetProfile
from pingte.domain.zodiac import ZODIACS


ANY_ISSUE_PATTERN = r"(?<!\d)\d{1,3}(?!\d)\s*期"


def issue_pattern(issue: str) -> str:
    return rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)\s*期"


def issue_pattern_for_rule(issue: str, rule: Mapping[str, object]) -> str:
    number = rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)"
    if rule.get("issue_line_format") == "arabic_colon_exact":
        return number + r"\s*[:：]"
    return number + r"\s*期"


def issue_anchor_matches(line: str, template: str, issue: str) -> bool:
    """Match an issue-bearing section anchor without accepting a larger issue."""
    if not template:
        return False
    if "{issue}" not in template:
        return template in line
    before, after = template.split("{issue}", 1)
    issue_number = rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)"
    pattern = re.escape(before) + issue_number + re.escape(after)
    return bool(re.search(pattern, line))


_PERIOD_TOKEN_RE = re.compile(r"(?<!\d)(\d{1,3})(?:\s*[-－~]\s*(\d{1,3}))?(?!\d)\s*期")
_ZODIAC_CHARS = "鼠牛虎兔龙蛇马羊猴鸡狗猪"


def value_line_belongs_to_issue(line: str, issue: str) -> bool:
    """区块内的值行是否属于指定期。

    区块里可能混入邻期数据行（例如 298 期区块里出现一行 ``297期 平特一肖 马``），
    只按标签+生肖取值会把邻期的值当本期结果。判定方式是**值归属期**：
    取「第一个生肖出现位置之前、最后一个期号标记」作为该值的期号。

    这样两类借值都会被拒绝：
      * ``297期 … 蛇 … 下期298期预告`` —— 蛇属于 297，请求 298 时拒绝；
      * ``AAAAA级大公开298期 297期 平特一肖：鼠`` —— 鼠属于 297，请求 298 时拒绝。
    行内没有期号时放行（专属解析器已把期号绑在区块锚点上）。
    """
    tokens: list[tuple[int, int, int]] = []
    for match in _PERIOD_TOKEN_RE.finditer(line):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        tokens.append((min(start, end), max(start, end), match.end()))
    if not tokens:
        return True

    value_at = next(
        (index for index, ch in enumerate(line) if ch in _ZODIAC_CHARS),
        len(line),
    )
    owner: tuple[int, int] | None = None
    for start, end, token_end in tokens:
        if token_end <= value_at:
            owner = (start, end)
        else:
            break
    if owner is None:
        # 期号都在生肖之后（例如「…【鼠】开 298期准」），按第一个期号归属。
        owner = (tokens[0][0], tokens[0][1])
    target = int(issue)
    return owner[0] <= target <= owner[1]


_value_line_belongs_to_issue = value_line_belongs_to_issue


def clean_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]


@dataclass(frozen=True)
class ParserHooks:
    extract_zodiac: Callable[[str], str | None]
    extract_target_zodiac: Callable[..., str | None]
    zodiac_chars: Callable[[str], str]
    dedupe_zodiac: Callable[[str], str]


class RuleBook:
    def __init__(
        self,
        rules: Iterable[dict],
        followup_labels: Mapping[str, str],
        *,
        dedicated_names: Iterable[str] = ("赌神平特", "小白平特"),
        dedicated_url_parts: Iterable[str] = (
            "topic/385412.html",
            "topic/385408.html",
        ),
    ) -> None:
        self.rules = tuple(rules)
        self.followup_labels = dict(followup_labels)
        self.dedicated_names = frozenset(dedicated_names)
        self.dedicated_url_parts = tuple(dedicated_url_parts)

    @staticmethod
    def rule_matches(rule: dict, target: TargetProfile) -> bool:
        rule_target_id = str(rule.get("target_id", ""))
        if target.target_id and rule_target_id:
            return rule_target_id == target.target_id
        return (
            str(rule.get("url_contains", "")) == target.url
            and str(rule.get("name", "")) == target.name
            and str(rule.get("position", "")) == target.position
            and str(rule.get("keyword", "")) == target.keyword
        )

    def rule_for(self, target: TargetProfile) -> dict:
        matches = [
            rule for rule in self.rules if self.rule_matches(rule, target)
        ]
        return matches[0] if len(matches) == 1 else {}

    def mode_for(self, target: TargetProfile) -> str:
        return str(self.rule_for(target).get("mode", ""))

    def is_dedicated_bottom(self, target: TargetProfile) -> bool:
        return target.name in self.dedicated_names or any(
            part in target.url for part in self.dedicated_url_parts
        )

    def has_dedicated_parser(self, target: TargetProfile) -> bool:
        return bool(self.mode_for(target)) or self.is_dedicated_bottom(target)


def matches_keyword(line: str, keyword: str) -> bool:
    return not keyword or keyword in line


def many_zodiac_category(line: str) -> bool:
    return bool(
        re.search(
            r"[二三四五六七八九十②③④⑤⑥⑦⑧⑨⑩]\s*肖|"
            r"[2-9]\s*肖|1[0-9]\s*肖",
            line,
        )
    )


def selected_section_starts(
    starts: list[int],
    target: TargetProfile,
    rule: dict,
    *,
    all_sections: bool = False,
) -> list[int]:
    if all_sections:
        return list(starts)
    if not starts:
        return []
    # target.position is the only direction authority. A legacy override is
    # rejected during config validation and ignored here for fail-closed use
    # by tests or callers that construct rules directly.
    return [starts[0] if target.position == "top" else starts[-1]]


def has_confirmed_result_structure(
    line: str,
    issue: str | None = None,
    *,
    issue_marker: str | None = None,
    allow_short_pingte: bool = False,
    allow_bare_pingte: bool = False,
) -> bool:
    if issue and not re.search(issue_marker or issue_pattern(issue), line):
        return False
    if any(
        token in line
        for token in (
            "→绝密数据",
            "→横扫庄家",
            "独家高手",
            "免费公開",
            "免费公开",
        )
    ):
        return False
    if re.search(rf"=[{ZODIACS}]+\s*[√✓×xX]", line):
        return True
    if re.search(
        r"[开開](?:\s*[:：]?\s*[开開])?[\s\S]{0,18}"
        r"(?:准|中|错|赢|输|对|對|赚|賺|√|✓|×|x|X)",
        line,
    ):
        return True
    if re.search(rf"平[特一]{{1,3}}[\s:：]*[{ZODIACS}]+肖?[？?]?\s*$", line):
        return True
    if re.search(rf"平特[^期]{{0,10}}[{ZODIACS}]{{2,}}\s*$", line):
        return True
    # Site-specific abbreviation proven on the live page, e.g. "261期 平鸡肖".
    # Only sites whose own DOM shows that spelling may enable it.
    if allow_short_pingte and re.search(
        rf"平\s*[{ZODIACS}]{{1,2}}\s*肖\s*$",
        line,
    ):
        return True
    # 本期未开奖的简写，例如「299期 平牛兔」：「平」是「平特」简写，后面直接
    # 跟 1–2 个生肖、不带「肖」字。只有开启 allow_bare_pingte_result 的站点可用。
    if allow_bare_pingte and re.search(
        rf"期\s*平\s*[{ZODIACS}]{{1,2}}\s*$",
        line,
    ):
        return True
    return bool(
        re.search(rf"[{ZODIACS}]+肖[？?]?\s*$", line)
        and "平特" in line
    )


def is_section_boundary(
    line: str,
    target: TargetProfile,
    header: str = "",
) -> bool:
    if line == header:
        return False
    if line.startswith((".", "function ")) or any(
        token in line for token in ("上一篇", "下一篇")
    ):
        return True
    if re.search(r"^(?:广告|广告推荐|赞助|推广)(?:$|[:：])", line):
        return True
    return any(token in line for token in ("发表于", "作者：", "作者:")) and (
        target.name not in line
    )
