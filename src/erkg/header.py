"""Parse the (templated) item header and split the body into statement lines."""
import re
from dataclasses import dataclass, field


@dataclass
class Rota:
    people: list
    blocks: list
    stations: list
    holders: list            # people who are on a station
    lines: list = field(default_factory=list)   # body statements, verbatim, in order


class HeaderError(ValueError):
    pass


def parse_item(text: str) -> Rota:
    raw = text.split("\n")
    header = raw[0]
    people = _list_after(header, r"on the rota:\s*(.*?)\.\s+Blocks")
    blocks = re.findall(r"\b\d{1,2}:\d{2}\b", _grab(header, r"Blocks run\s*(.*?),\s*one person per block"))
    stations = _list_after(header, r"one person on each:\s*(.*?)\.\s+The people on a station")
    holders = _list_after(header, r"The people on a station are\s*(.*?);")
    if not (people and blocks and stations and holders):
        raise HeaderError("could not parse header: %r" % header[:200])
    lines = [l.strip() for l in raw[1:] if l.strip()]
    return Rota(people, blocks, stations, holders, lines)


def _grab(s, pat):
    m = re.search(pat, s, re.S)
    if not m:
        raise HeaderError("header pattern not found: " + pat)
    return m.group(1)


def _list_after(s, pat):
    body = _grab(s, pat)
    body = re.sub(r"\s+and\s+", ", ", body)
    return [x.strip() for x in body.split(",") if x.strip()]