"""python tests/show_reply.py trace.jsonl B2-011   -> prints the raw model reply for one item"""
import json, sys
path, iid = sys.argv[1], sys.argv[2]
for l in open(path, encoding="utf-8"):
    t = json.loads(l)
    if t["id"] == iid:
        print(t.get("reply") or t)
        print("-" * 60)
