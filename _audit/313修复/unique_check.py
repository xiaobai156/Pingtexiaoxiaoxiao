"""机检：每个站点锚点区块内，317 期结果行是否唯一，且符合方向（top 取首、tail 取末）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.application.runtime import build_runtime  # noqa: E402
from pingte.parse.context import clean_lines, has_confirmed_result_structure  # noqa: E402
from pingte.validation.issue import extract_target_zodiac  # noqa: E402

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
ISSUE = "317"

runtime = build_runtime(ROOT)
by_name = {t.name: t for t in runtime.targets}
verify = {
    row["name"]: row
    for row in json.loads((HERE / f"verify-{ISSUE}.json").read_text(encoding="utf-8"))
}
text = (HERE / "failure.txt").read_text(encoding="utf-8")
names: list[str] = []
for entry in re.findall(r"失败 (\S+) (\S+) 方向", text):
    if entry[0] not in names:
        names.append(entry[0])

results = []
for name in names:
    target = by_name[name]
    rule = runtime.registry.rules.rule_for(target)
    path = BODIES / f"{name}-verify.txt"
    if not path.exists():
        results.append({"name": name, "status": "无快照"})
        continue
    lines = clean_lines(path.read_text(encoding="utf-8"))
    mode = str(rule.get("mode", ""))
    # 圈定站点自己的区块
    if mode in {"anchored_section", "anchored_formula_section"}:
        anchor = str(rule.get("section_anchor", "")).replace("{issue}", ISSUE)
        end = str(rule.get("section_end", "")).replace("{issue}", ISSUE)
        exact = bool(rule.get("section_anchor_exact"))
        end_exact = bool(rule.get("section_end_exact"))
        starts = [i for i, l in enumerate(lines) if (l == anchor if exact else anchor in l)]
        if not starts:
            results.append({"name": name, "status": "锚点缺失"})
            continue
        start = starts[0]
        stop = next(
            (i for i in range(start + 1, len(lines))
             if (lines[i] == end if end_exact else end in lines[i])),
            None,
        )
        scope = lines[start + 1: stop if stop is not None else len(lines)]
    elif mode == "author_section":
        anchor = str(rule.get("section_anchor", ""))
        starts = [i for i, l in enumerate(lines) if anchor in l]
        if not starts:
            results.append({"name": name, "status": "作者锚点缺失"})
            continue
        start = starts[0]
        stop = next(
            (i for i in range(start + 1, len(lines))
             if lines[i] == str(rule.get("section_end", ""))),
            None,
        )
        scope = lines[start + 1: stop if stop is not None else start + 40]
    else:
        scope = lines

    # 栏目关键词可能用繁体/缩写（如 成語爆平特），优先用规则里的 line_keyword；
    # 公式栏目（规律二肖）本期行本就不含关键栏目名，只按期数+结构筛。
    line_keyword = str(rule.get("line_keyword") or target.keyword)
    require_keyword = mode != "anchored_formula_section"
    issue_rows = [
        line for line in scope
        if re.search(rf"(?<!\d){ISSUE}(?!\d)", line)
        and has_confirmed_result_structure(line)
        and (not require_keyword or line_keyword in line)
    ]
    zodiacs = [extract_target_zodiac(line, target, rule) for line in issue_rows]
    picked = zodiacs[0] if target.position == "top" and zodiacs else (
        zodiacs[-1] if zodiacs else None
    )
    ok = (
        len(issue_rows) == 1
        and picked == verify[name].get("written")
        and verify[name].get("written")
    )
    results.append(
        {
            "name": name,
            "mode": mode,
            "position": target.position,
            "issue_rows": len(issue_rows),
            "zodiacs": zodiacs,
            "picked": picked,
            "written": verify[name].get("written"),
            "ok": bool(ok),
            "row": issue_rows[0][:120] if issue_rows else "",
        }
    )
    flag = "OK " if ok else "!! "
    print(
        f"{flag}{name:<12} {mode:<24} {target.position:<5} "
        f"317行数={len(issue_rows)} 取值={picked} 写入={verify[name].get('written')}"
    )
    if not ok:
        for line in issue_rows[:4]:
            print("      ", line[:110])

(HERE / f"unique-{ISSUE}.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
)
bad = [r for r in results if not r.get("ok")]
print("\n通过", len(results) - len(bad), "/", len(results), "未通过:", [r["name"] for r in bad])
