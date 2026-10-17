"""item text -> answer: the model extracts, the solver decides, the solver also sanity-checks the model."""
from dataclasses import dataclass
from .header import parse_item
from .solver import Space, minimal_core
from . import extract

MAX_AMBIGUOUS = 4          # the brief: 2..4 consistent assignments
MIN_CORE = 3               # the brief: a real contradiction cites at least 3 statements


@dataclass
class Flags:
    guided: bool = True      # rules + few-shot in the prompt
    vote: bool = True        # use the whole budget on independent passes and vote
    ground: bool = True      # validate atoms against the rota before solving
    minimize: bool = True    # cite a minimal conflicting set (vs. every constrained statement)
    repair: bool = True      # solver-guided: stop early when plausible, re-extract / repair when not


def solve(rota, space, chosen, flags=Flags()):
    """chosen: {line_index: atoms}.  -> (answers.json entry, n_solutions, core_size)."""
    line_masks = {}
    for k, atoms in chosen.items():
        atoms = [a for a in atoms if space.valid(a)]
        if not atoms:
            continue
        m = space.mask(atoms[0]).copy()
        for a in atoms[1:]:
            m &= space.mask(a)
        line_masks[k] = m
    keys = sorted(line_masks)
    sols = space.solutions([line_masks[k] for k in keys])
    if len(sols) == 1:
        return {"case": "unique", "assignment": space.render(sols[0])}, 1, 0
    if len(sols) > 1:
        return ({"case": "ambiguous", "assignments": [space.render(u) for u in sols[:MAX_AMBIGUOUS]]},
                len(sols), 0)
    if flags.minimize:
        masks = [line_masks[k] for k in keys]
        core = minimal_core(masks, space)
        if len(core) < MIN_CORE:
            # The brief says a real contradiction cites >= 3 statements, so a 1-2 statement
            # conflict is an extraction error.  Drop one member at a time; if what is left is
            # still contradictory, cite that (genuine) conflict instead.
            core = _larger_core(masks, space, core) or core
        cited = [rota.lines[keys[i]] for i in core]
    else:
        cited = [rota.lines[k] for k in keys]
    return {"case": "inconsistent", "conflicts": cited}, 0, len(cited)


def _larger_core(masks, space, small):
    for drop in small:
        rest = [i for i in range(len(masks)) if i != drop]
        sub = [masks[i] for i in rest]
        if len(space.solutions(sub)):
            continue                                    # dropping this one removes the contradiction
        core = minimal_core(sub, space)
        if len(core) >= MIN_CORE:
            return [rest[i] for i in core]
    return None


def decide(rota, space, chosen, flags=Flags()):
    return solve(rota, space, chosen, flags)[0]


def plausible(n_sols, core):
    """The brief fixes the shape of a valid item: exactly 1 solution, 2..4 solutions, or a
    contradiction citing >= 3 statements.  Anything else means the extraction is wrong."""
    if n_sols == 1 or 2 <= n_sols <= MAX_AMBIGUOUS:
        return True
    return n_sols == 0 and core >= MIN_CORE


def repair(rota, space, runs, chosen, flags):
    """Try to turn an implausible vote into a plausible one by swapping ONE statement's atom for a
    different atom some other run produced (SKIP counts as an atom).  Most-voted alternative first."""
    bl = extract.ballots(runs, space, flags.ground)
    cands = []
    for k, votes in bl.items():
        counts = {}
        for b in votes:
            counts[b] = counts.get(b, 0) + 1
        for alt, n in counts.items():
            if alt != chosen.get(k, ()):
                cands.append((-n, k, alt))
    for _, k, alt in sorted(cands):
        trial = dict(chosen)
        trial[k] = alt
        ans, n, core = solve(rota, space, trial, flags)
        if plausible(n, core):
            return trial
    return None


def answer_item(item, client, budget, flags=Flags(), trace=None):
    rota = parse_item(item["text"])
    space = Space(rota)
    system, user = extract.build_prompt(rota, guided=flags.guided)
    n_calls = budget if flags.vote else 1
    runs, chosen = [], {}
    for _ in range(n_calls):
        try:
            reply = client.chat(system, user)
        except Exception as e:                       # network / budget: lose this sample only
            if trace is not None:
                trace.append({"id": item["id"], "error": repr(e)})
            continue
        if trace is not None:
            trace.append({"id": item["id"], "reply": reply})
        runs.append(extract.parse_reply(reply, rota))
    chosen = extract.vote(runs, space, ground=flags.ground)
    if flags.repair and len(runs) >= 2:
        _, n, core = solve(rota, space, chosen, flags)
        if not plausible(n, core):
            fixed = repair(rota, space, runs, chosen, flags)
            if fixed is not None:
                chosen = fixed
    return decide(rota, space, chosen, flags)