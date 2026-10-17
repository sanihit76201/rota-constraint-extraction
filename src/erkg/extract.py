"""Model-based constraint extraction.

One model call = one full pass over an item: the model reads the numbered
statements and writes one atom per statement in a tiny closed language.  The
reply is parsed tolerantly and every atom is *grounded* (names, blocks and
stations must exist on that item's rota) before it reaches the solver.

v3 changes (vs v2):
  * prompt forbids commentary; parser drops `#` comment text, so rambling can
    no longer eat the token budget or smuggle in phantom atoms
  * one atom per statement is the norm: a line with more than MAX_ATOMS atoms
    is treated as unusable (SKIP) instead of poisoning the solver
  * station-family rules/examples (precedes / done before / not put on ...)
  * ballots() exposed so the pipeline can do solver-guided repair

v4 changes:
  * ground_atom() repairs the atom family when the 2nd argument is a station/block
    (AT(p, station) -> STATION, STATION(p, block) -> AT, and the NOT_ forms)
  * extra few-shot: refused/declined/lobbied requests, other hedge openers
"""
import re
from collections import Counter

ATOM_RE = re.compile(r"\b(AT|NOT_AT|STATION|NOT_STATION|BEFORE|DIRECTLY_BEFORE|BETWEEN)\s*\(([^()]*)\)", re.I)
LINE_RE = re.compile(r"^\s*[\[(*]*\s*(\d+)\s*[\])\.:\-*]*\s*(.*)$")
MAX_ATOMS = 2

OPS = {"AT": "at", "NOT_AT": "not_at", "STATION": "st", "NOT_STATION": "not_st",
       "BEFORE": "before", "DIRECTLY_BEFORE": "directly_before", "BETWEEN": "between"}

_RULES = """\
You convert shift-note statements into constraints for a scheduling puzzle.
For EVERY numbered statement write exactly one output line and nothing else:
  <number>. <first ~6 words of the statement> => <atoms>
where <atoms> is SKIP, or ONE atom. Never leave a number out. Never write explanations, notes, reasoning or comments \
(no lines starting with #). After the last statement, stop.

Atoms. X and Y may each be a person OR a station name (a station name means "whoever is on that station"):
  AT(person, block)              person works that block
  NOT_AT(person, block)          person does NOT work that block
  STATION(person, station)       person is on that station
  NOT_STATION(person, station)   person is NOT on that station
  BEFORE(earlier, later)         the FIRST argument works EARLIER in the day than the second (not necessarily adjacent)
  DIRECTLY_BEFORE(first, second) second's block comes immediately after first's, nothing in between
  BETWEEN(middle; end1, end2)    the part before the semicolon is the one in the MIDDLE; end1/end2 are the two outer people, in either order

Pick the atom by what the statement is ABOUT:
 * About two people or stations and their order in the day -> BEFORE, DIRECTLY_BEFORE or BETWEEN. Never AT / NOT_AT.
 * About one person and one STATION NAME -> STATION or NOT_STATION. Never AT / NOT_AT.
 * About one person and one TIME (like 09:00) -> AT or NOT_AT.
 * One statement = one atom. Never expand a statement into several NOT_AT atoms.

Direction check for BEFORE (put the one who works earlier FIRST):
  "A is on later than B" / "A comes after B" / "B works earlier than A" / "B is done before A starts" / "A takes over from B" -> BEFORE(B, A)
  "the person on <station> precedes A" / "<station> is covered before A comes on" / "whoever has <station> works earlier than A" -> BEFORE(<station>, A)
  "A is on later than whoever has <station>" -> BEFORE(<station>, A)
Direction check for DIRECTLY_BEFORE:
  "A then B, back to back" / "A hands straight over to B" / "A is on the block immediately before B" / "no block between A's and B's, in that order" -> DIRECTLY_BEFORE(A, B)
  "B is on the block directly after A" / "B relieves A directly" -> DIRECTLY_BEFORE(A, B)
Station statements:
  "X is not on / not assigned to / not been put on / ruled out for <station>", "<station> is covered by someone other than X" -> NOT_STATION(X, station)
  "X is on / has <station>", "<station> is covered by X", "<station> is X's station", "<station> is down to X" -> STATION(X, station)
Block statements:
  "X is unavailable at / cannot do / is not on <block>" -> NOT_AT(X, block)
  "X is on / takes / opens up at <block>", "<block> is X's", "whoever has <block> is X" -> AT(X, block)

Rules:
- Hedges ("I think", "as far as I know", "from memory", "going off the roster") carry FULL force. Ignore them; never SKIP because of a hedge.
- A restatement marker ("noted twice:", "worth repeating:") only introduces an ordinary statement; convert what follows.
- SKIP everything that is not a constraint on the CURRENT plan: errands, who attended/joined/signed/keeps something, building or catering news, \
what somebody wanted, asked for, put in for or lobbied for (even when it was refused or turned down -- that tells you nothing about the plan, SKIP it), \
counterfactuals ("would have", "had X happened"), opinions ("better fit", "would have solved"), \
how things USED to be (last month, previous cycle, in the spring, old arrangement), and open questions ("nobody could remember", "left open", "came up but nothing was minuted").
- Copy names, blocks and stations exactly as they appear in the roster."""

_FEWSHOT = """\
Example (invented roster: Ana, Bo, Cy, Di, Ed; blocks 08:00, 10:00, 12:00, 14:00, 16:00; stations: welding, painting, lifting)
1. As far as I know, Ana is on the block directly before Bo.
2. Cy has the keys to the van.
3. Painting is covered by someone other than Di.
4. Ed asked for 08:00 and was told no.
5. Whichever order Ana and Cy come in, Di sits between them.
6. If Bo had worked 12:00, the handover would have been easier.
7. Lifting is covered earlier in the day than Ed's block.
8. Last winter Cy was on welding.
9. The 14:00 block is Ed's.
10. Di is not on 10:00, I'm fairly sure.
11. Cy takes over from Bo later in the day.
12. Welding is Ana's station.
13. Ana, Bo and Cy went on the site visit.
14. Ana and Bo? That ended up being left open.
15. Ed comes later in the day than Di.
16. Going off the roster, Bo has not been put on lifting.
17. Cy is on after one of Ed and Ana and before the other.
18. Di put in for 16:00 and was turned down.
19. The person on welding precedes Ed.
20. Whoever has painting is done before Bo starts.
21. Di then Cy, back to back.
22. Ed has not been put on welding.
23. There is no block between Bo's and Ed's, in that order.
24. Cy wanted 08:00 and did not get it.
25. Bo asked to switch to the 10:00 block; the request was declined.
26. Speaking from memory, Di is assigned to lifting.
27. Ed hoped for the 12:00 block, but it went to someone else.
28. My recollection is that Ana cannot cover the 12:00 block at all.
29. Going off the roster, the 16:00 block is Bo's.
30. Speaking from memory, Ed has to sit somewhere between Bo and Di.
31. Cy lobbied for 14:00 without success.
32. My recollection is that Ed has not been put on painting.
Output:
1. As far as I know, Ana => DIRECTLY_BEFORE(Ana, Bo)
2. Cy has the keys to => SKIP
3. Painting is covered by someone => NOT_STATION(Di, painting)
4. Ed asked for 08:00 and => SKIP
5. Whichever order Ana and Cy => BETWEEN(Di; Ana, Cy)
6. If Bo had worked 12:00, => SKIP
7. Lifting is covered earlier in => BEFORE(lifting, Ed)
8. Last winter Cy was on => SKIP
9. The 14:00 block is Ed's. => AT(Ed, 14:00)
10. Di is not on 10:00, => NOT_AT(Di, 10:00)
11. Cy takes over from Bo => BEFORE(Bo, Cy)
12. Welding is Ana's station. => STATION(Ana, welding)
13. Ana, Bo and Cy went => SKIP
14. Ana and Bo? That ended => SKIP
15. Ed comes later in the => BEFORE(Di, Ed)
16. Going off the roster, Bo => NOT_STATION(Bo, lifting)
17. Cy is on after one => BETWEEN(Cy; Ed, Ana)
18. Di put in for 16:00 => SKIP
19. The person on welding precedes => BEFORE(welding, Ed)
20. Whoever has painting is done => BEFORE(painting, Bo)
21. Di then Cy, back to => DIRECTLY_BEFORE(Di, Cy)
22. Ed has not been put => NOT_STATION(Ed, welding)
23. There is no block between => DIRECTLY_BEFORE(Bo, Ed)
24. Cy wanted 08:00 and did => SKIP
25. Bo asked to switch to => SKIP
26. Speaking from memory, Di is => STATION(Di, lifting)
27. Ed hoped for the 12:00 => SKIP
28. My recollection is that Ana => NOT_AT(Ana, 12:00)
29. Going off the roster, the 16:00 => AT(Bo, 16:00)
30. Speaking from memory, Ed has => BETWEEN(Ed; Bo, Di)
31. Cy lobbied for 14:00 without => SKIP
32. My recollection is that Ed => NOT_STATION(Ed, painting)"""

_BARE_RULES = """\
You convert shift-note statements into constraints. Output one line per numbered statement, formatted `<number>. => <atoms>`.
Atoms: AT(person, block), NOT_AT(person, block), STATION(person, station), NOT_STATION(person, station), \
BEFORE(earlier, later), DIRECTLY_BEFORE(first, second), BETWEEN(middle; end1, end2), or SKIP. X, Y may be a person or a station name."""


def build_prompt(rota, guided=True):
    system = _RULES + "\n\n" + _FEWSHOT if guided else _BARE_RULES
    lines = "\n".join("%d. %s" % (i + 1, l) for i, l in enumerate(rota.lines))
    user = ("Roster: %s\nBlocks: %s\nStations: %s\n\nStatements:\n%s\n\nOutput (%d lines, no comments):"
            % (", ".join(rota.people), ", ".join(rota.blocks), ", ".join(rota.stations), lines, len(rota.lines)))
    return system, user


def _atoms_in(text):
    atoms = []
    for op, args in ATOM_RE.findall(text):
        parts = tuple(a.strip().strip("'\"") for a in re.split(r"[;,]", args) if a.strip())
        atoms.append((OPS[op.upper()],) + parts)
    if len(atoms) > MAX_ATOMS:        # a statement is one constraint; a long expansion is an error, not signal
        return ()
    return tuple(atoms)


def _clean(raw):
    """Drop `#` commentary: whole comment lines and trailing ` # ...` text."""
    if raw.lstrip().startswith("#"):
        return ""
    return re.sub(r"\s+#.*$", "", raw)


def parse_reply(reply, rota, ground=True):
    """-> {line_index: tuple-of-atoms or ()}. Lines the model never mentioned are absent.

    Atoms are read only from the part after `=>` (the echoed statement is ignored).
    If the reply carries no usable numbering, fall back to positional alignment of its `=>` lines.
    """
    out, positional = {}, []
    for raw in (reply or "").splitlines():
        raw = _clean(raw)
        if not raw.strip():
            continue
        body = raw.rsplit("=>", 1)[1] if "=>" in raw else None
        m = LINE_RE.match(raw)
        if body is not None:
            positional.append(_atoms_in(body))
        if not m:
            continue
        k = int(m.group(1)) - 1
        if not 0 <= k < len(rota.lines) or k in out:      # first answer for a number wins
            continue
        rest = m.group(2)
        out[k] = _atoms_in(rest.rsplit("=>", 1)[1] if "=>" in rest else rest)
    if len(out) < len(rota.lines) / 2 and len(positional) >= len(rota.lines) / 2:
        out = {i: a for i, a in enumerate(positional[:len(rota.lines)])}
    return out


_BLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def ground_atom(atom, space):
    """Case-insensitive snap of names/blocks/stations onto the rota; None if invalid."""
    r = space.rota
    canon = {}
    for s in list(r.people) + list(r.stations) + list(r.blocks):
        canon[s.lower()] = s

    def snap(a):
        a = a.strip()
        if a.lower().endswith("'s"):
            a = a[:-2]
        m = _BLOCK_RE.match(a)
        if m:
            a = "%02d:%s" % (int(m.group(1)), m.group(2))
        if a.lower().endswith(" station"):
            a = a[:-8]
        return canon.get(a.lower(), a)

    c = (atom[0],) + tuple(snap(a) for a in atom[1:])
    # type repair: the model sometimes picks the wrong family for (person, station) / (person, block)
    if c[0] in ("at", "not_at") and len(c) == 3 and c[2] in r.stations:
        c = ("st" if c[0] == "at" else "not_st", c[1], c[2])
    elif c[0] in ("st", "not_st") and len(c) == 3 and c[2] in r.blocks:
        c = ("at" if c[0] == "st" else "not_at", c[1], c[2])
    return c if space.valid(c) else None


def ballots(parsed_runs, space, ground=True):
    """{line_index: [grounded atom-tuple per run that answered that line]}.
    Ungrounded atoms are dropped, so a run that hallucinated a name votes SKIP for that line."""
    result = {}
    for k in range(len(space.rota.lines)):
        bl = []
        for run in parsed_runs:
            if k not in run:
                continue
            atoms = []
            for a in run[k]:
                g = ground_atom(a, space) if ground else (a if space.valid(a) else None)
                if g is not None:
                    atoms.append(_canon(g))
            bl.append(tuple(sorted(set(atoms))))
        result[k] = bl
    return result


def vote(parsed_runs, space, ground=True):
    """Per-statement plurality over sampled runs -> {line_index: tuple-of-atoms}
    (ties go to the earliest run among the leaders; SKIP is the empty tuple)."""
    result = {}
    for k, bl in ballots(parsed_runs, space, ground).items():
        if not bl:
            result[k] = ()
            continue
        counts = Counter(bl)
        best = max(counts.values())
        result[k] = next(b for b in bl if counts[b] == best)
    return result


def _canon(c):
    if c[0] == "between":
        x, y = sorted(c[2:])
        return ("between", c[1], x, y)
    return c