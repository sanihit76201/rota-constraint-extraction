#!/usr/bin/env python3
"""Ablation table on the visible set (needs the real endpoint).

    python ablate.py --runs 2 --budgets 1x,3x --out ablation_1x3x.md
    python ablate.py --runs 2 --budgets 10x --only "full system" --out ablation_10x.md

Each cell is the mean macro exact match over --runs repeats (+- population std).
Cost per cell = runs x 60 items x budget calls, so 10x is expensive: run it for the
full system only.
"""
import argparse, json, os, statistics, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(ROOT, "src"), ROOT]
from erkg import llm, baseline
from erkg.cli import run_all, BUDGETS
from erkg.pipeline import Flags, answer_item
import score

ROWS = {
    "full system":                        (answer_item, Flags()),
    "- guided prompt (bare instruction)": (answer_item, Flags(guided=False)),
    "- vote (extra calls unused)":        (answer_item, Flags(vote=False)),
    "- grounding of atoms":               (answer_item, Flags(ground=False)),
    "- core minimisation (cite all)":     (answer_item, Flags(minimize=False)),
    "- solver-guided repair":             (answer_item, Flags(repair=False)),
    "- solver (model answers directly)":  (baseline.answer_item, None),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--budgets", default="1x,3x,10x")
    ap.add_argument("--only", default="", help="substring filter on row names")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--items", default="items.json")
    ap.add_argument("--key", default="visible_key.json")
    ap.add_argument("--out", default="ablation.md")
    a = ap.parse_args()
    llm.load_env(ROOT)
    items = json.load(open(os.path.join(ROOT, a.items), encoding="utf-8"))
    key = json.load(open(os.path.join(ROOT, a.key), encoding="utf-8"))
    ep = llm.Endpoint()
    budgets = a.budgets.split(",")
    lines = ["| variant | " + " | ".join(budgets) + " |", "|---|" + "---|" * len(budgets)]
    for name, (fn, flags) in ROWS.items():
        if a.only and a.only not in name:
            continue
        cells = []
        for b in budgets:
            vals = []
            for r in range(a.runs):
                ans, _ = run_all(items, ep, BUDGETS[b], flags or Flags(), a.workers, fn=fn)
                vals.append(score.score(key, ans, items)["macro_exact_match"])
            cells.append("%.1f%% (±%.1f, n=%d)" % (100 * statistics.mean(vals),
                         100 * (statistics.pstdev(vals) if len(vals) > 1 else 0), len(vals)))
            print(name, b, cells[-1], flush=True)
        lines.append("| %s | %s |" % (name, " | ".join(cells)))
    open(os.path.join(ROOT, a.out), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()