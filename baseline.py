"""Harness-free baseline for the ablation: ask the model for the final answer directly (no solver)."""
import json
import re

_SYS = ("Solve the rota puzzle from the shift notes. Reply with ONLY a JSON object, one of:\n"
        '{"case":"unique","assignment":{"<name>":{"block":"<hh:mm>","station":"<station, only if on a station>"}}}\n'
        '{"case":"ambiguous","assignments":[{...},{...}]}   (all consistent assignments)\n'
        '{"case":"inconsistent","conflicts":["<verbatim statement>", "..."]}')


def answer_item(item, client, budget, flags=None, trace=None):
    try:
        reply = client.chat(_SYS, item["text"], max_tokens=3000)
    except Exception:
        return {}
    if trace is not None:
        trace.append({"id": item["id"], "reply": reply})
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}