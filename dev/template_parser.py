"""DEV ONLY -- not used by ./run. Regex parser for the visible set's templates (test oracle + ablation row)."""
import re
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from erkg.score_helpers import strip_hedge   # noqa: E402


def parse_line(line, rota):
    N = "(" + "|".join(map(re.escape, rota.people)) + ")"
    S = "(" + "|".join(map(re.escape, rota.stations)) + ")"
    T = r"(\d\d:\d\d)"
    s = strip_hedge(line).rstrip(".")
    R = lambda p: re.match(p, s, re.I)
    m = R(N + r" sits between " + N + " and " + N + r" on the rota")
    if m: return [("between", m[1], m[2], m[3])]
    m = R(N + r" is on after one of " + N + " and " + N + " and before the other")
    if m: return [("between", m[1], m[2], m[3])]
    m = R(N + r"'s block falls between " + N + "'s and " + N + "'s, in one order")
    if m: return [("between", m[1], m[2], m[3])]
    m = R(N + r" works at some point between " + N + " and " + N)
    if m: return [("between", m[1], m[2], m[3])]
    m = R(r"put " + N + " between " + N + " and " + N + ", though")
    if m: return [("between", m[1], m[2], m[3])]
    m = R(r"whichever way round " + N + " and " + N + " are, " + N + " is between them")
    if m: return [("between", m[3], m[1], m[2])]
    m = R(r"the " + S + r" station is covered earlier in the day than " + N + "'s block")
    if m: return [("before", m[1], m[2])]
    m = R(N + r" is on later than whoever has " + S)
    if m: return [("before", m[2], m[1])]
    m = R(r"the person on " + S + " precedes " + N)
    if m: return [("before", m[1], m[2])]
    m = R(r"whoever is on " + S + " works earlier in the day than " + N)
    if m: return [("before", m[1], m[2])]
    m = R(r"whoever has " + S + " is done before " + N + " starts")
    if m: return [("before", m[1], m[2])]
    m = R(S + r" is covered before " + N + " comes on")
    if m: return [("before", m[1], m[2])]
    m = R(r"by the time " + N + " starts, " + N + " has already been on")
    if m: return [("before", m[2], m[1])]
    m = R(N + " is done before " + N + " starts")
    if m: return [("before", m[1], m[2])]
    m = R(N + " works earlier in the day than " + N)
    if m: return [("before", m[1], m[2])]
    m = R(N + " comes later in the day than " + N)
    if m: return [("before", m[2], m[1])]
    m = R(N + r"'s block falls somewhere earlier than " + N + "'s")
    if m: return [("before", m[1], m[2])]
    m = R(N + " takes over from " + N + " later in the day")
    if m: return [("before", m[2], m[1])]
    m = R(N + " relieves " + N + " directly")
    if m: return [("directly_before", m[2], m[1])]
    m = R(N + " is on the block directly after " + N)
    if m: return [("directly_before", m[2], m[1])]
    m = R(N + " is on the block immediately before " + N)
    if m: return [("directly_before", m[1], m[2])]
    m = R(N + " hands straight over to " + N)
    if m: return [("directly_before", m[1], m[2])]
    m = R(N + " then " + N + ", back to back")
    if m: return [("directly_before", m[1], m[2])]
    m = R(r"there is no block between " + N + "'s and " + N + "'s, in that order")
    if m: return [("directly_before", m[1], m[2])]
    for p, a, b in ((N + r" has not been put on " + S, 1, 2), (N + r" is not on " + S + "$", 1, 2),
                    (N + r" is not assigned to " + S, 1, 2), (r"you can rule " + N + " out for " + S, 1, 2),
                    (S + r" is not " + N + "'s station", 2, 1), (S + r" is covered by someone other than " + N, 2, 1)):
        m = R(p)
        if m: return [("not_st", m[a], m[b])]
    for p, a, b in ((N + r" is assigned to " + S, 1, 2), (N + r" is on " + S + "$", 1, 2),
                    (N + r" has " + S + " this week", 1, 2), (S + r" is " + N + "'s station", 2, 1),
                    (S + r" is covered by " + N + "$", 2, 1), (r"the " + S + r" station is down to " + N, 2, 1)):
        m = R(p)
        if m: return [("st", m[a], m[b])]
    for p, a, b in ((N + r" is on the " + T + " block", 1, 2), (r"the " + T + r" block is " + N + "'s", 2, 1),
                    (r"whoever drew the " + T + r" block, it was " + N, 2, 1), (N + r" is the one who opens up at " + T, 1, 2),
                    (N + r" takes " + T + ", as things stand", 1, 2), (T + " is when " + N + " is scheduled", 2, 1)):
        m = R(p)
        if m: return [("at", m[a], m[b])]
    for p, a, b in ((N + r" is not on the " + T + " block", 1, 2), (r"you will not find " + N + " on the " + T + " block", 1, 2),
                    (T + " is the one block " + N + " is definitely not on", 2, 1), (N + r" is unavailable at " + T, 1, 2),
                    (N + r" has a standing commitment that rules out the " + T + " block", 1, 2),
                    (r"the " + T + r" block is not " + N + "'s", 2, 1)):
        m = R(p)
        if m: return [("not_at", m[a], m[b])]
    return []


def fmt(atoms):
    if not atoms:
        return "SKIP"
    op = {"at": "AT", "not_at": "NOT_AT", "st": "STATION", "not_st": "NOT_STATION", "before": "BEFORE",
          "directly_before": "DIRECTLY_BEFORE", "between": "BETWEEN"}
    return " ; ".join("%s(%s)" % (op[a[0]], ", ".join(a[1:])) for a in atoms)


def reply_for(rota):
    return "\n".join("%d: %s" % (i + 1, fmt(parse_line(l, rota))) for i, l in enumerate(rota.lines))