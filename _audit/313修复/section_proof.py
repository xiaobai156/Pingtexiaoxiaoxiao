"""按站点自身栏目锚点，打印命中区块原文，用于逐站人工核对写入值是否来自正确栏目。"""
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

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
ISSUE = "317"

runtime = build_runtime(ROOT)
by_name = {t.name: t for t in runtime.targets}

text = (HERE / "failure.txt").read_text(encoding="utf-8")
names: list[str] = []
for name in re.findall(r"失败 (\S+) (\S+) 方向", text):
    if name[0] not in names:
        names.append(name[0])

verify = {
    row["name"]: row
    for row in json.loads((HERE / f"verify-{ISSUE}.json").read_text(encoding="utf-8"))
}

for name in names:
    target = by_name[name]
    rule = runtime.registry.rules.rule_for(target)
    path = BODIES / f"{name}-verify.txt"
    if not path.exists():
        print(f"--- {name}: 无快照")
        continue
    lines = clean_lines(path.read_text(encoding="utf-8"))
    mode = rule.get("mode", "")
    print("=" * 78)
    print(f"{name} [{target.target_id}] mode={mode} kw={target.keyword} 写入={verify[name].get('written') or '-'}")
    if mode in {"anchored_section", "anchored_formula_section"}:
        anchor = str(rule.get("section_anchor", "")).replace("{issue}", ISSUE)
        end = str(rule.get("section_end", "")).replace("{issue}", ISSUE)
        anchor_exact = bool(rule.get("section_anchor_exact"))
        end_exact = bool(rule.get("section_end_exact"))
        starts = [
            i for i, l in enumerate(lines)
            if (l == anchor if anchor_exact else anchor in l)
        ]
        ends = [
            i for i, l in enumerate(lines)
            if (l == end if end_exact else end in l)
        ]
        print(f"  锚点 {anchor!r} 命中 {len(starts)} 处 {starts[:5]} | 尾锚点 {end!r} 命中 {len(ends)} 处 {ends[:5]}")
        if starts:
            start = starts[0]
            stop = next((e for e in ends if e > start), min(len(lines), start + 30))
            print(f"  区块 {start + 1}..{stop + 1} 原文：")
            shown = 0
            for i in range(start, min(stop + 1, start + 30)):
                if lines[i].strip():
                    print(f"    {i + 1:5d}: {lines[i][:110]}")
                    shown += 1
                if shown >= 12:
                    break
    elif mode == "author_section":
        anchor = str(rule.get("section_anchor", ""))
        starts = [i for i, l in enumerate(lines) if anchor in l]
        print(f"  作者锚点 {anchor!r} 命中 {starts[:5]}")
        if starts:
            for i in range(starts[0], min(len(lines), starts[0] + 14)):
                if lines[i].strip():
                    print(f"    {i + 1:5d}: {lines[i][:110]}")
    else:
        hits = [
            (i, l) for i, l in enumerate(lines)
            if re.search(rf"(?<!\d){ISSUE}(?!\d)", l)
            and has_confirmed_result_structure(l)
            and target.keyword in l
        ]
        print(f"  含关键词且结构成立的行: {len(hits)}")
        for i, l in hits[:6]:
            print(f"    {i + 1:5d}: {l[:110]}")
