import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
from pingte.application.runtime import build_runtime
ROOT = Path(__file__).resolve().parents[2]
runtime = build_runtime(ROOT)
OUT = Path(r"C:/Users/Administrator/Desktop/每天工具/爬虫合集/大围杀号生肖数据统一归纳/11.18平特肖.txt")
text = OUT.read_text(encoding="utf-8")
body = text.split("\n排行榜\n",1)[0]
lines = [l.strip() for l in body.splitlines() if l.strip()]
print("成功条数", len(lines), "唯一", len({l.split(maxsplit=1)[1] for l in lines}))
order = [t.name for t in runtime.targets]
names = [l.split(maxsplit=1)[1] for l in lines]
print("顺序=targets顺序", names == [n for n in order if n in set(names)])
print("万水千山 ->", dict(l.split(maxsplit=1)[::-1]).get("万水千山"))
print("排行榜:", text.split("\n排行榜\n",1)[1].replace("\n"," ").strip())
cache = json.load(open(ROOT/"recent_10_cache.json", encoding="utf-8-sig"))
print("缓存 issues", cache["issues"])
s = [x for x in cache["sites"] if x["name"]=="万水千山"][0]
print("缓存 万水千山 322 =", s["values"].get("322"), "| 有322的站数", sum(1 for x in cache["sites"] if x["values"].get("322")))
ev = json.loads((ROOT/"evidence"/"11.18-322期.json").read_text(encoding="utf-8-sig"))
rows = ev["results"]
print("证据条数", len(rows), "target_id 唯一", len({r["target_id"] for r in rows}))
evd = {r["name"]: r["zodiac"] for r in rows}
print("证据与TXT一致", all(evd.get(l.split(maxsplit=1)[1])==l.split(maxsplit=1)[0] for l in lines))
print("证据含万水千山", evd.get("万水千山"))
