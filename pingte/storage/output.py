from __future__ import annotations

import os
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Iterable

from pingte.domain.failures import FailureCode, FailureDetail
from pingte.domain.zodiac import ZODIACS


_FAILURE_PRESENTATION: dict[FailureCode, tuple[str, str]] = {
    FailureCode.WEB_FETCH_FAILED: ("网页抓取", "网络失败"),
    FailureCode.EMPTY_DOCUMENT: ("正文校验", "正文为空"),
    FailureCode.TARGET_BOUNDARY_MISSING: ("区块边界校验", "边界缺失"),
    FailureCode.KEYWORD_MISSING: ("栏目校验", "关键字缺失"),
    FailureCode.ISSUE_MISSING: ("指定期数校验", "指定期缺失"),
    FailureCode.ISSUE_OUT_OF_DIRECTION_WINDOW: ("指定期数校验", "方向范围外"),
    FailureCode.ANCHOR_MISSING: ("栏目锚点校验", "锚点缺失"),
    FailureCode.BLOCK_AMBIGUOUS: ("区块校验", "区块冲突"),
    FailureCode.CONTENT_PENDING: ("内容校验", "内容未更新"),
    FailureCode.ZODIAC_MISSING: ("结果校验", "生肖缺失"),
    FailureCode.TOO_MANY_ZODIACS: ("数量校验", "数量超限"),
    FailureCode.AMBIGUOUS_CANDIDATES: ("同期校验", "同期候选冲突"),
    FailureCode.RECORD_ID_MISSING: ("文章身份校验", "文章ID缺失"),
    FailureCode.RECORD_ID_AMBIGUOUS: ("文章身份校验", "文章ID冲突"),
    FailureCode.RECORD_VALIDATION_FAILED: ("文章身份校验", "文章身份不一致"),
    FailureCode.SOURCE_CONFLICT: ("来源校验", "来源冲突"),
    FailureCode.CACHE_UPDATE_FAILED: ("缓存更新", "缓存更新失败"),
    FailureCode.RULE_MISSING: ("专属规则校验", "专属解析缺失"),
    FailureCode.INTERNAL_ERROR: ("程序校验", "内部错误"),
}


def _failure_stage_category(failure: FailureDetail) -> tuple[str, str]:
    return _FAILURE_PRESENTATION.get(
        failure.code,
        ("失败校验", failure.code.value),
    )


def _failure_reason(failure: FailureDetail) -> str:
    reason = failure.message
    if failure.matched_line:
        reason += f"；匹配行：{failure.matched_line}"
    if failure.visible_issues:
        visible = "、".join(f"{issue}期" for issue in failure.visible_issues)
        reason += f"；当前可见期数：{visible}"
    return reason


def _render_failure_txt(failure: FailureDetail) -> str:
    stage, _category = _failure_stage_category(failure)
    position = "bottom" if failure.position == "tail" else failure.position
    return (
        f"失败 {failure.name} {failure.url} 方向: {position} 期数: {failure.issue}\n"
        f"阶段: {stage} 原因: {_failure_reason(failure)}"
    )


def build_failure_output(failures: Iterable[FailureDetail]) -> str:
    items = list(failures)
    if not items:
        return ""

    categories: dict[str, int] = {}
    for failure in items:
        _stage, category = _failure_stage_category(failure)
        categories[category] = categories.get(category, 0) + 1

    blocks = [_render_failure_txt(failure) for failure in items]
    summary = ["失败分类统计"]
    summary.extend(
        f"{category} {count}条" for category, count in categories.items()
    )
    return "\n\n".join((*blocks, "\n".join(summary))) + "\n"


def build_output(results: Iterable[str]) -> str:
    lines = list(results)
    counts = {zodiac: 0 for zodiac in ZODIACS}
    for result in lines:
        zodiac_text = result.split(maxsplit=1)[0]
        for zodiac in zodiac_text:
            if zodiac in counts:
                counts[zodiac] += 1
    ranking = [(zodiac, counts[zodiac]) for zodiac in ZODIACS if counts[zodiac] > 0]
    ranking.sort(key=lambda item: (-item[1], ZODIACS.index(item[0])))
    if ranking:
        lines.extend(("", "排行榜"))
        lines.extend(f"{zodiac} {count}" for zodiac, count in ranking)
    return "\n".join(lines) + ("\n" if lines else "")


def date_label(today: date | None = None) -> str:
    current = today or date.today()
    return f"{current.month}.{current.day}"


def progress_line(
    label: str,
    done: int,
    total: int,
    success: int,
    failed: int,
    started_at: float,
    current: str,
) -> str:
    elapsed = time.monotonic() - started_at
    percent = 100 if total <= 0 else int(done * 100 / total)
    return (
        f"[{label} {done}/{total} {percent}% 成功 {success} 失败 {failed} "
        f"用时 {elapsed:.1f}s] 当前：{current}"
    )


def default_output_paths(
    issue: str,
    *,
    output_dir: Path,
    today: date | None = None,
) -> tuple[Path, Path]:
    del issue
    label = date_label(today)
    return (
        Path(output_dir) / f"{label}平特肖.txt",
        Path(output_dir) / f"{label}平特肖-失败.txt",
    )


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        raise
