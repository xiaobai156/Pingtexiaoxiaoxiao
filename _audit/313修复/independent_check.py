"""独立复核：不依赖站点解析规则，直接在页面上找所有 317 期含生肖的行，检查唯一性与方向。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pingte.domain.zodiac import ZODIACS  # noqa: E402

HERE = Path(__file__).resolve().parent
ISSUE = "317"
BODIES = HERE / "bodies"

report = json.loads((HERE / f"verify-{ISSUE}.json").read_text(encoding="utf-8"))

zodiac_only = re.compile(rf"^[{ZODIACS}]+$")


def runs(text: str) -> list[str]:
    """连续生肖字组成的片段，长度 1-4。"""
    found = []
    for match in re.finditer(rf"[{ZODIACS}]{{1,4}}", text):
        found.append(match.group(0))
    return found


print(f"{'站点':<14}{'写入':<6}{'页面317含生肖行':<10}判定")
print("-" * 78)
conclusions = []
for row in report:
    name = row["name"]
    path = BODIES / f"{name}-verify.txt"
    if not path.exists():
        print(f"{name:<14}{'—':<6}{'无快照':<10}跳过")
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = []
    for index, line in enumerate(lines):
        if not re.search(rf"(?<!\d){ISSUE}(?!\d)", line):
            continue
        if not re.search(r"开|開", line):
            continue
        fragments = [f for f in runs(line) if len(f) >= 1]
        if not fragments:
            continue
        hits.append((index, line.strip(), fragments))
    # 只保留「像结果行」的：含 开/開 且紧跟状态
    result_like = [
        h for h in hits
        if re.search(r"开[^0-9]{0,3}[0-9？?]{1,}|开[：:\s]*[0-9？?]", h[1])
        and re.search(r"准|中|错|對|对", h[1])
    ]
    distinct = {tuple(h[2]) for h in result_like}
    verdict = "唯一" if len(distinct) == 1 else f"多候选{len(distinct)}组"
    print(
        f"{name:<14}{row.get('written','-') or '-':<6}"
        f"{len(result_like):<10}{verdict}"
    )
    for index, line, fragments in result_like[:4]:
        print(f"    行{index + 1}: {fragments} | {line[:100]}")
    conclusions.append(
        {
            "name": name,
            "written": row.get("written", ""),
            "result_like": len(result_like),
            "distinct": [list(d) for d in distinct],
            "verdict": verdict,
            "lines": [h[1][:140] for h in result_like[:4]],
        }
    )

(HERE / f"independent-{ISSUE}.json").write_text(
    json.dumps(conclusions, ensure_ascii=False, indent=1), encoding="utf-8"
)
