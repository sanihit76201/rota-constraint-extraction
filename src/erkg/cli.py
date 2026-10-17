import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from . import llm
from .pipeline import answer_item, Flags

BUDGETS = {"1x": 1, "3x": 3, "10x": 10}


def run_all(items, endpoint, budget, flags=Flags(), workers=8, trace=None, fn=answer_item):
    def one(it):
        client = llm.ItemClient(endpoint, it["id"], budget)
        t = []
        try:
            ans = fn(it, client, budget, flags, t)
        except Exception as e:      # an item must never take the run down
            ans, t = {}, t + [{"id": it["id"], "error": "pipeline: %r" % e}]
        return it["id"], ans, t, client.used
    out, used = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for iid, ans, t, n in ex.map(one, items):
            out[iid] = ans
            used[iid] = n
            if trace is not None:
                trace.extend(t)
    return out, used


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run")
    ap.add_argument("items")
    ap.add_argument("--budget", choices=sorted(BUDGETS), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--trace", help="optional jsonl of raw model replies")
    a = ap.parse_args(argv)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    llm.load_env(root)
    items = json.load(open(a.items, encoding="utf-8"))
    trace = [] if a.trace else None
    answers, used = run_all(items, llm.Endpoint(), BUDGETS[a.budget], workers=a.workers, trace=trace)
    json.dump(answers, open(a.out, "w", encoding="utf-8"), indent=2)
    if a.trace:
        with open(a.trace, "w", encoding="utf-8") as f:
            for t in trace:
                f.write(json.dumps(t) + "\n")
    print("wrote %s  (%d items, model calls: min %d / max %d per item)"
          % (a.out, len(answers), min(used.values()), max(used.values())), file=sys.stderr)


if __name__ == "__main__":
    main()