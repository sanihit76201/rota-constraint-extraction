"""DEV: per-statement accuracy of the model's trace vs the template-parser oracle.
   python tests/line_accuracy.py trace.jsonl
"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def find_data():
    for d in (ROOT, os.path.join(ROOT, "candidate_package")):
        if os.path.exists(os.path.join(d, "items.json")):
            return d
    sys.exit("items.json not found")


DATA = find_data()
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "dev")]
from erkg.header import parse_item
from erkg.solver import Space
from erkg import extract
from template_parser import parse_line

trace_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "trace.jsonl")
items = json.load(open(os.path.join(DATA, "items.json"), encoding="utf-8"))
replies, errors = {}, collections.Counter()
for l in open(trace_path, encoding="utf-8"):
    t = json.loads(l)
    if "reply" in t and t["id"] not in replies:
        replies[t["id"]] = t["reply"]
    if "error" in t:
        errors[t["error"][:80]] += 1

counts = collections.Counter()
examples = collections.defaultdict(list)
bad_atoms = []
items_all_right = 0
missing_items = []
for it in items:
    rota = parse_item(it["text"]); space = Space(rota)
    if it["id"] not in replies:
        missing_items.append(it["id"])
    run = extract.parse_reply(replies.get(it["id"], ""), rota)
    all_ok = True
    for k, line in enumerate(rota.lines):
        tg = [extract.ground_atom(a, space) for a in parse_line(line, rota)]
        truth = tuple(sorted(set(extract._canon(a) for a in tg if a)))
        if k not in run:
            cat, model = "no_output_line", None
        else:
            g = []
            for a in run[k]:
                ga = extract.ground_atom(a, space)
                if ga is None:
                    bad_atoms.append((it["id"], a))
                else:
                    g.append(extract._canon(ga))
            model = tuple(sorted(set(g)))
            if truth == model:
                cat = "ok_skip" if not truth else "ok_atom"
            elif not truth:
                cat = "FALSE_CONSTRAINT (distractor taken as real)"
            elif not model:
                cat = "MISSED_CONSTRAINT (real line skipped or atom unusable)"
            elif {a[0] for a in truth} == {a[0] for a in model}:
                cat = "right_op_WRONG_ARGS"
            else:
                cat = "WRONG_OP"
        counts[cat] += 1
        if not cat.startswith("ok"):
            all_ok = False
            if len(examples[cat]) < 8:
                examples[cat].append((it["id"], line, truth, model))
    items_all_right += all_ok

total = sum(counts.values())
print("statements: %d   items with every statement right: %d/%d   ungrounded atoms: %d"
      % (total, items_all_right, len(items), len(bad_atoms)))
print("items with no reply in trace: %s   api/pipeline errors: %s\n" % (missing_items[:10], dict(errors)))
for cat, n in counts.most_common():
    print("%5d  %5.1f%%  %s" % (n, 100.0 * n / total, cat))
print("\n=== sample ungrounded atoms (model wrote something unusable) ===")
for iid, a in bad_atoms[:15]:
    print(" ", iid, a)
for cat, ex in examples.items():
    print("\n=== %s ===" % cat)
    for iid, line, truth, model in ex:
        print("[%s] %s\n    oracle: %s\n    model : %s" % (iid, line, truth, model))
