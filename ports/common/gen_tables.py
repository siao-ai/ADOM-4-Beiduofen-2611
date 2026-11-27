#!/usr/bin/env python3 -B
"""Build-time Unicode tables for ports that live in runtimes without Unicode support.

Everything here is derived from the *same* CPython `unicodedata` / `re` that produced
tests/parity_expected.json, so the ports inherit the reference's exact Unicode version.

    python3 -B ports/common/gen_tables.py > tables.json
"""
import json, re, sys, unicodedata

ALL = [c for c in range(0x110000) if not 0xD800 <= c < 0xE000]

def keepish(c):  # anything a text key could keep: Han, a-z, 0-9
    return (0x3400 <= c <= 0x4DBF or 0x4E00 <= c <= 0x9FFF or 0xF900 <= c <= 0xFAFF
            or 0x61 <= c <= 0x7A or 0x30 <= c <= 0x39)

def ranges(cps):
    out, start, prev = [], None, None
    for c in cps:
        if start is None: start = prev = c
        elif c == prev + 1: prev = c
        else: out.append([start, prev]); start = prev = c
    if start is not None: out.append([start, prev])
    return out

def build():
    nfkc = {}
    for c in ALL:
        t = unicodedata.normalize("NFKC", chr(c))
        if t != chr(c): nfkc[c] = [ord(x) for x in t]
    lower = {}
    for c in ALL:
        if 0x41 <= c <= 0x5A: continue
        l = chr(c).lower()
        if l != chr(c) and any(keepish(ord(x)) for x in l): lower[c] = [ord(x) for x in l]
    ws = [c for c in ALL if re.match(r"\s", chr(c))]
    word = ranges([c for c in ALL if re.match(r"\w", chr(c))])
    ci = {L: [c for c in ALL if re.match(L, chr(c), re.I) and c not in (ord(L), ord(L.upper()))]
          for L in "abcdefghijklmnopqrstuvwxyz"}
    ci = {k: v for k, v in ci.items() if v}
    return {"unidata": unicodedata.unidata_version, "nfkc": nfkc, "lower": lower, "ws": ws,
            "word": word, "ci": ci}

if __name__ == "__main__":
    json.dump(build(), sys.stdout, ensure_ascii=True, separators=(",", ":"))
