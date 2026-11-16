"""对 316 失败站做离线诊断：打印规则、锚点命中、316 期数据行位置。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

targets = json.loads((ROOT / "targets.json").read_text(encoding="utf-8"))
index = {t["name"]: t for t in targets["targets"]}

fail_names = re.findall(r"失败 (\S+) ", (HERE / "failure.txt").read_text(encoding="utf-8"))

for name in fail_names:
    body_path = BODIES / f"{name}.txt"
    lines = body_path.read_text(encoding="utf-8").splitlines()
    target = index.get(name)
    rule = {k: v for k, v in (target or {}).items() if k in {
        "mode", "section_anchor", "section_end", "section_end_exact", "keyword",
        "position", "data_structure", "source_strategy", "frame_scope", "issue_format"}}
    print("=" * 70)
    print(name, target.get("id") if target else "NOT FOUND", target.get("url") if target else "")
    print(json.dumps(rule, ensure_ascii=False))
    print("行数", len(lines), "字节", body_path.stat().st_size)

    anchor = rule.get("section_anchor") or ""
    end = rule.get("section_end") or ""
    if anchor:
        hits = [i + 1 for i, line in enumerate(lines) if anchor in line]
        print("anchor 命中行", hits[:10], "共", len(hits))
    if end:
        hits = [i + 1 for i, line in enumerate(lines) if end in line]
        print("end 命中行", hits[:10], "共", len(hits))

    kw = rule.get("keyword") or ""
    if kw:
        hits = [i + 1 for i, line in enumerate(lines) if kw in line]
        print("keyword 命中行", hits[:10], "共", len(hits))

    issue_lines = [(i + 1, line.strip()) for i, line in enumerate(lines) if "316" in line]
    print("含 316 的行数", len(issue_lines))
    for lineno, text in issue_lines[:12]:
        print("  ", lineno, text[:160])
