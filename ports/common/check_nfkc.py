#!/usr/bin/env python3 -B
"""How far is per-code-point NFKC (what the table-driven ports do) from real NFKC on the test sets?
    python3 -B ports/common/check_nfkc.py"""
import json, os, unicodedata
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
for name, rel in (("public", "tests/public/parity_prompts.json"), ("full", "tests/parity_prompts.json")):
    P = json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))
    diff = sum(unicodedata.normalize("NFKC", p) != "".join(unicodedata.normalize("NFKC", c) for c in p) for p in P)
    print("per-code-point NFKC == full NFKC on %s set: %d/%d prompts" % (name, len(P) - diff, len(P)))
