"""Validate solver + output path with the template parser standing in for the model."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def find_data():
    for d in (ROOT, os.path.join(ROOT, "candidate_package"), os.path.abspath(os.path.join(ROOT, ".."))):
        if all(os.path.exists(os.path.join(d, f)) for f in ("items.json", "visible_key.json", "score.py")):
            return d
    sys.exit("Could not find items.json / visible_key.json / score.py near " + ROOT)


DATA = find_data()
print("using data from:", DATA)
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "dev"), DATA]
from erkg.header import parse_item
from erkg.solver import Space
from erkg import extract
from erkg.pipeline import decide
from template_parser import reply_for
import score

items = json.load(open(os.path.join(DATA, "items.json"), encoding="utf-8"))
key = json.load(open(os.path.join(DATA, "visible_key.json"), encoding="utf-8"))
ans = {}
for it in items:
    rota = parse_item(it["text"]); space = Space(rota)
    parsed = extract.parse_reply(reply_for(rota), rota)
    ans[it["id"]] = decide(rota, space, extract.vote([parsed], space))
res = score.score(key, ans, items)
print(json.dumps({k: res[k] for k in ("macro_exact_match", "per_case_rate", "confusion", "inconsistent_label_only")}, indent=1))
bad = [i for i, v in res["per_item"].items() if v < 1]
print("failing:", bad)