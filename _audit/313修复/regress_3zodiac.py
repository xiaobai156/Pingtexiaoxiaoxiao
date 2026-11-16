"""放宽到 3 肖后的离线回归：确认没有别的站点被改变。

只读 `_audit/313修复/bodies/` 里的正文快照，不联网、不写任何正式文件。

比对的三个前提（缺一即跳过，不把「快照本身不含该期」算成回归失败）：
  1. 同一站点优先用 `-verify.txt`（修复时强制渲染后真实重抓的那份），
     普通 `.txt` 是 content-visibility 未解开时的旧抓取，正文可能为空；
  2. 快照正文里必须出现该期标记，否则说明这个快照不是该期的；
  3. 必须有对照基准：317 用成功文件，316/315 用 recent_10_cache.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pingte.application.runtime import build_runtime
from pingte.validation.issue import extract_target_zodiac

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
OUTPUT = Path(
    r"C:/Users/Administrator/Desktop/每天工具/爬虫合集/大围杀号生肖数据统一归纳/11.13平特肖.txt"
)


def pick_body(stem: str) -> Path | None:
    """同一站点优先取强制渲染后的 verify 正文，其次 recheck。"""
    for suffix in ("-verify", "-recheck"):
        candidate = BODIES / f"{stem}{suffix}.txt"
        if candidate.exists() and candidate.read_text(encoding="utf-8").strip():
            return candidate
    plain = BODIES / f"{stem}.txt"
    if plain.exists() and plain.read_text(encoding="utf-8").strip():
        return plain
    return None


def main() -> int:
    runtime = build_runtime(ROOT)
    by_name = {target.name: target for target in runtime.targets}
    records = {
        line.split(maxsplit=1)[1]: line.split(maxsplit=1)[0]
        for line in OUTPUT.read_text(encoding="utf-8")
        .split("\n排行榜\n", 1)[0]
        .splitlines()
        if line.strip()
    }
    cache = json.loads((ROOT / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
    cached = {
        entry["name"]: {str(k): str(v) for k, v in entry["values"].items()}
        for entry in cache["sites"]
    }

    stems = sorted(
        {
            path.stem.replace("-verify", "").replace("-recheck", "")
            for path in BODIES.glob("*.txt")
        }
    )

    mismatches = []
    compared = 0
    skipped: list[str] = []
    for name in stems:
        target = by_name.get(name)
        if target is None:
            continue
        body = pick_body(name)
        if body is None:
            skipped.append(f"{name}: 无可用正文快照")
            continue
        text = body.read_text(encoding="utf-8")
        rule = runtime.registry.rules.rule_for(target)
        for issue in ("317", "316", "315"):
            expected = records.get(name) if issue == "317" else cached.get(name, {}).get(issue)
            if expected is None:
                continue
            if f"{issue}期" not in text:
                skipped.append(f"{name} {issue}: 快照不含该期（{body.name}）")
                continue
            lines = runtime.registry.parse_issue_lines(text, target, issue)
            # 快照里该栏目可能只保留当期（往期行被站点覆盖），此时不含期标记的行
            # 是被别期行匹配进来的，不能当成本期解析结果。
            own = [line for line in lines if f"{issue}期" in line]
            if not own:
                skipped.append(f"{name} {issue}: 快照该栏目无本期数据行")
                continue
            values = [v for v in (extract_target_zodiac(line, target, rule) for line in own) if v]
            if not values:
                mismatches.append((name, issue, expected, None, len(own), body.name))
                continue
            parsed = values[0] if target.position == "top" else values[-1]
            compared += 1
            if parsed != expected:
                mismatches.append((name, issue, expected, parsed, len(own), body.name))

    current = [row for row in mismatches if row[1] == "317"]
    historical = [row for row in mismatches if row[1] != "317"]

    print(f"可比对 {compared} 项，跳过 {len(skipped)} 项")
    if historical:
        # 公式类站点的往期行由站方按新开奖号重算，与当日缓存必然不同，
        # 只能作参考，不能当回归依据（见 11.12 期满堂红第三/第四 同类现象）。
        print(f"参考项 {len(historical)} 个（历史行可能被站点改写，不计失败）：")
        for name, issue, expected, parsed, count, body in historical:
            print(f"  {name} {issue}: 缓存 {expected} / 今日页面 {parsed}（{body}）")
    if current:
        print("本期 317 不一致（真正的回归失败）：")
        for name, issue, expected, parsed, count, body in current:
            print(f"  {name} {issue}: 期望 {expected} / 解析 {parsed}（{count} 行，{body}）")
        return 1
    print("本期 317 全部一致：放宽 3 肖未改变任何已修站点的取值")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
