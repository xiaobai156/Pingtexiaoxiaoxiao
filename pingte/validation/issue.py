from __future__ import annotations

import re
from collections.abc import Mapping

from pingte.domain.models import TargetProfile
from pingte.domain.zodiac import ZODIAC_NUMBERS, ZODIACS


ANY_ISSUE_PATTERN = r"(?<!\d)\d{1,3}(?!\d)\s*期"


def issue_pattern(issue: str) -> str:
    return rf"(?<!\d){re.escape(str(int(issue)))}(?!\d)\s*期"


def zodiac_chars(text: str) -> str:
    return "".join(ch for ch in text if ch in ZODIACS)


def dedupe_zodiac(text: str) -> str:
    return "".join(dict.fromkeys(text))


def zodiac_from_open_numbers(line: str) -> str | None:
    if "开奖结果" in line or not re.search(r"(?:平特|一肖|成语|谜语|公式|推荐)", line):
        return None
    open_match = re.search(
        r"[开開]\s*[:：]?\s*([0-4]?\d(?:[.\s、,，/]+[0-4]?\d)*)",
        line,
    )
    if not open_match:
        return None
    if not re.search(
        r"(?:准|中|错|√|✓|×|x|X)",
        line[open_match.end() : open_match.end() + 6],
    ):
        return None
    result: list[str] = []
    for raw_number in re.findall(r"\d{1,2}", open_match.group(1)):
        number = int(raw_number)
        if not 1 <= number <= 49:
            continue
        for zodiac, numbers in ZODIAC_NUMBERS.items():
            if number in numbers and zodiac not in result:
                result.append(zodiac)
                break
    return "".join(result) or None


def _extract_zodiac(line: str, *, allow_open_number_zodiac: bool) -> str | None:
    clean_line = re.split(r"\s+(?:\.|function\b)", line, maxsplit=1)[0]
    rejected_context = (
        "目录标题", "帖子标题", "作者：", "作者:", "站长宣言", "站长提示", "本网站",
        "本站", "承诺", "拒绝", "严禁", "绝不", "免责声明", "温馨提示",
        "友情提示", "马后炮", "龙套数据", "虚假", "开后", "公告", "声明",
        "开奖结果", "非目标栏目",
    )
    if any(token in clean_line for token in rejected_context):
        return None
    if any(token in clean_line for token in ("→绝密数据", "→横扫庄家")):
        return None
    before_open = re.split(r"[开開]", clean_line, maxsplit=1)[0]
    bracket_parts = re.findall(r"[【『\[(（](.*?)[】』\])）]", before_open)
    for part in bracket_parts:
        found = zodiac_chars(part)
        if found:
            return dedupe_zodiac(found)

    equals_parts = re.findall(r"[=＝]\s*([^\s=＝]+)", line)
    if equals_parts:
        equals_zodiac = zodiac_chars(equals_parts[-1])
        if equals_zodiac:
            return dedupe_zodiac(equals_zodiac)

    before_bracket = re.split(r"[【『\[(（]", before_open, maxsplit=1)[0]
    before_found = zodiac_chars(before_bracket)
    if before_found and len(before_bracket) <= 40:
        return dedupe_zodiac(before_found)

    before_open_found = zodiac_chars(before_open)
    suspicious_context = any(
        token in before_open
        for token in ("站长宣言", "本网站", "马后炮", "资料", "封号", "公告", "声明")
    )
    if before_open_found and not suspicious_context and len(before_open) <= 25:
        return dedupe_zodiac(before_open_found)

    open_parts = re.split(r"[开開]", clean_line, maxsplit=1)
    if len(open_parts) > 1:
        after_found = zodiac_chars(open_parts[-1])
        if after_found:
            return dedupe_zodiac(after_found)
    if allow_open_number_zodiac:
        return zodiac_from_open_numbers(clean_line)
    return None


def extract_zodiac(line: str) -> str | None:
    """Legacy text helper; formal parsing uses strict_extract_zodiac."""
    return _extract_zodiac(line, allow_open_number_zodiac=True)


def strict_extract_zodiac(line: str) -> str | None:
    """Extract only zodiac characters explicitly present in the source line."""
    return _extract_zodiac(line, allow_open_number_zodiac=False)


def extract_target_zodiac(
    line: str,
    target: TargetProfile,
    rule: Mapping[str, object] | None = None,
) -> str | None:
    identities = {
        target.name,
        str((rule or {}).get("section_name", "")),
    }
    sanitized = line
    for identity in identities:
        if identity:
            sanitized = sanitized.replace(identity, "")
    return strict_extract_zodiac(sanitized)
