"""Statement normalisation matching the scorer's (hedge openers / restatement prefix)."""
HEDGES = ("i'm fairly sure ", "from what i recall, ", "as far as i know, ", "i believe ",
          "going off the roster, ", "if memory serves, ", "my recollection is that ",
          "unless i have this wrong, ", "speaking from memory, ", "i'm reasonably confident ")


def strip_hedge(line):
    s = " ".join(line.split())
    head, sep, tail = s.partition(": ")
    if sep and tail and len(head) < 60:
        s = tail
    low = s.lower()
    for h in HEDGES:
        if low.startswith(h):
            s = s[len(h):]
            break
    return s