"""Exact solver. Constraints are tuples over a closed vocabulary:

  ("at", P, B) / ("not_at", P, B)
  ("st", P, S) / ("not_st", P, S)
  ("before", X, Y)            X's block strictly earlier than Y's
  ("directly_before", X, Y)   Y's block immediately follows X's
  ("between", M, X, Y)        M strictly between X and Y, either order

X/Y/M are a person or a station name (= whoever holds that station).
"""
import itertools
import numpy as np


class Space:
    def __init__(self, rota):
        self.rota = rota
        self.pi = {p: i for i, p in enumerate(rota.people)}
        self.bi = {b: i for i, b in enumerate(rota.blocks)}
        self.si = {s: i for i, s in enumerate(rota.stations)}
        n = len(rota.people)
        bperms = np.array(list(itertools.permutations(range(len(rota.blocks)), n)), dtype=np.int8)
        hold_idx = [self.pi[h] for h in rota.holders]
        sperms = np.array(list(itertools.permutations(hold_idx, len(rota.stations))), dtype=np.int8)
        nb, ns = len(bperms), len(sperms)
        self.P = np.repeat(bperms, ns, axis=0)          # U x n : block index of each person
        self.S = np.tile(sperms, (nb, 1))               # U x k : person holding each station
        self.U = len(self.P)
        self._rows = np.arange(self.U)

    def pos(self, ref):
        if ref in self.pi:
            return self.P[:, self.pi[ref]]
        if ref in self.si:
            return self.P[self._rows, self.S[:, self.si[ref]]]
        raise KeyError(ref)

    def known_ref(self, ref):
        return ref in self.pi or ref in self.si

    def valid(self, c):
        op = c[0]
        if op in ("at", "not_at"):
            return len(c) == 3 and c[1] in self.pi and c[2] in self.bi
        if op in ("st", "not_st"):
            return len(c) == 3 and c[1] in self.pi and c[2] in self.si
        if op in ("before", "directly_before"):
            return len(c) == 3 and self.known_ref(c[1]) and self.known_ref(c[2]) and c[1] != c[2]
        if op == "between":
            return (len(c) == 4 and all(self.known_ref(x) for x in c[1:])
                    and len(set(c[1:])) == 3)
        return False

    def mask(self, c):
        op = c[0]
        if op == "at":
            return self.P[:, self.pi[c[1]]] == self.bi[c[2]]
        if op == "not_at":
            return self.P[:, self.pi[c[1]]] != self.bi[c[2]]
        if op in ("st", "not_st"):
            m = self.S[:, self.si[c[2]]] == self.pi[c[1]]
            return m if op == "st" else ~m
        if op == "before":
            return self.pos(c[1]) < self.pos(c[2])
        if op == "directly_before":
            return self.pos(c[2]) - self.pos(c[1]) == 1
        if op == "between":
            m, x, y = self.pos(c[1]), self.pos(c[2]), self.pos(c[3])
            return ((x < m) & (m < y)) | ((y < m) & (m < x))
        raise ValueError(c)

    def solutions(self, masks):
        ok = np.ones(self.U, dtype=bool)
        for m in masks:
            ok &= m
        return np.flatnonzero(ok)

    def render(self, u):
        r = self.rota
        out = {p: {"block": r.blocks[int(self.P[u, self.pi[p]])]} for p in r.people}
        for s in r.stations:
            out[r.people[int(self.S[u, self.si[s]])]]["station"] = s
        return out


def minimal_core(masks, space, order=None):
    """Deletion-based minimal unsatisfiable subset (indices into `masks`), or None if satisfiable."""
    idx = list(range(len(masks))) if order is None else list(order)
    if len(space.solutions([masks[i] for i in idx])):
        return None
    core = idx[:]
    for i in idx:
        trial = [j for j in core if j != i]
        if not len(space.solutions([masks[j] for j in trial])):
            core = trial
    return core