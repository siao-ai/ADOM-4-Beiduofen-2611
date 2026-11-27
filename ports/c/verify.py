#!/usr/bin/env python3 -B
"""Parity test for the C port: feed every prompt to `adom --batch`, compare (text, key, hit, route)
with the Python reference answers.

    python3 -B ports/c/verify.py [--bin PATH] [--set public|full] [--runner "ssh host"]
"""
import argparse, json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

def unesc(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append({"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}[s[i + 1]]); i += 2
        else: out.append(s[i]); i += 1
    return "".join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=os.path.join(HERE, "build_adom"))
    ap.add_argument("--set", default="public")
    ap.add_argument("--runner", default="", help='prefix command, e.g. "ssh user@arm64-host"')
    a = ap.parse_args()
    d = os.path.join(ROOT, "tests", "public") if a.set == "public" else os.path.join(ROOT, "tests")
    P = json.load(open(os.path.join(d, "parity_prompts.json"), encoding="utf-8"))
    E = json.load(open(os.path.join(d, "parity_expected.json"), encoding="utf-8"))
    data = b"\0".join(p.encode("utf-8") for p in P)
    cmd = (a.runner.split() + [a.bin, "--batch"]) if a.runner else [a.bin, "--batch"]
    t0 = time.time()
    out = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, check=True).stdout.decode("utf-8")
    dt = time.time() - t0
    rows = out.split("\n")[:-1]
    assert len(rows) == len(P), (len(rows), len(P))
    by, bad = {}, 0
    for i, (row, e) in enumerate(zip(rows, E)):
        text, key, hit, route = row.split("\t")
        got = {"text": unesc(text), "key": unesc(key) or None, "hit": hit == "true", "route": route}
        ok = all(got[f] == e[f] for f in ("text", "key", "hit", "route"))
        by.setdefault(e["route"], [0, 0]); by[e["route"]][1] += 1; by[e["route"]][0] += ok
        if not ok:
            bad += 1
            if bad <= 5: print("MISMATCH #%d %r\n  exp %s\n  got %s" % (i, P[i][:80], e, got))
    print("RESULT identical %d/%d (%s) total %.2fs, %.3f ms/prompt (incl. process start + pipe)"
          % (len(P) - bad, len(P), ", ".join("%s %d/%d" % (k, v[0], v[1]) for k, v in by.items()), dt, dt * 1000 / len(P)))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
