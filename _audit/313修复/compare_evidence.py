"""对每个失败站：打印昨日 evidence 的 raw_line / block，并列出今日页面里可能的数据行。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"

fail_text = (HERE / "failure.txt").read_text(encoding="utf-8")
items = re.findall(r"失败 (\S+) (\S+) 方向: (\S+) 期数: (\d+)", fail_text)

last: dict[str, tuple[str, dict]] = {}
for path in sorted((ROOT / "evidence").glob("*.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        continue
    for record in data.get("results", []):
        last[record.get("name", "")] = (path.stem, record)

ZOD = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
for name, url, pos, issue in items:
    path = BODIES / f"{name}.txt"
    ev_name, rec = last.get(name, ("", {}))
    print("=" * 78)
    print(f"{name}  上次={ev_name} 期={rec.get('issue')} 值={rec.get('zodiac')}")
    print(f"  raw_line = {rec.get('raw_line')!r}")
    print(f"  anchor   = {rec.get('anchor_line')!r}  block={rec.get('block_id')}")
    if not path.exists():
        print("  （共用正文，跳过逐行）")
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    cand = []
    for i, ln in enumerate(lines):
        if f"{issue}期" not in ln:
            continue
        if not any(z in ln for z in ZOD):
            continue
        if "开" not in ln:
            continue
        cand.append((i + 1, ln.strip()))
    print(f"  今日 317+生肖+开 的行 {len(cand)} 条：")
    for no, ln in cand[:8]:
        print(f"    {no}: {ln[:100]}")
