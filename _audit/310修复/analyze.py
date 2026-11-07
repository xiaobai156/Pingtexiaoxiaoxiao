"""逐页核对 anchor / section_end / 309 数据行的行号关系，定位失败原因。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
BODIES = HERE / "bodies"
ISSUE = "309"

import glob

rules = {}
for path in glob.glob(str(ROOT / "config" / "sites" / "*.json")):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules[data["target"]["name"]] = data


def find(lines, needle, start=0):
    if not needle:
        return []
    return [i for i in range(start, len(lines)) if needle in lines[i]]


for body in sorted(BODIES.glob("*.txt")):
    name = body.stem
    lines = body.read_text(encoding="utf-8").splitlines()
    cfg = rules.get(name)
    if not cfg:
        print(name, "无配置")
        continue
    parser = cfg["parser"]
    anchor = parser.get("section_anchor", "")
    end = parser.get("section_end", "")
    keyword = parser["keyword"]
    data_hits = [i for i, line in enumerate(lines) if ISSUE in line and keyword in line]
    print(f"--- {name} mode={parser['mode']} pos={cfg['target']['position']}")
    print(f"    anchor={anchor!r} 行号={find(lines, anchor)[:4]}")
    print(f"    end={end!r} 行号={find(lines, end)[:4]}")
    print(f"    309+关键字行号={data_hits[:4]}")
