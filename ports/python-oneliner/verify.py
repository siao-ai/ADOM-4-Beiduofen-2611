#!/usr/bin/env python3 -B
"""Parity test for the one-liner: run `python3 adom1.py --batch` (prompts as a JSON list on stdin)
and compare (text, key, hit, route) against the reference answers.  Also re-checks with ast that
adom1.py is one line holding one expression statement.

    python3 -B ports/python-oneliner/verify.py [--set public|full] [--python python3] [--runner "ssh host"] [--script PATH]
"""
import argparse, ast, json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="public"); ap.add_argument("--python", default="python3")
    ap.add_argument("--runner", default=""); ap.add_argument("--script", default=os.path.join(HERE, "adom1.py"))
    a = ap.parse_args()
    src = open(os.path.join(HERE, "adom1.py"), encoding="utf-8").read()
    t = ast.parse(src)
    assert src.count("\n") == 1 and len(t.body) == 1 and isinstance(t.body[0], ast.Expr)
    print("adom1.py: 1 line, 1 expression statement, %d characters" % (len(src) - 1))
    d = os.path.join(ROOT, "tests", "public") if a.set == "public" else os.path.join(ROOT, "tests")
    P = json.load(open(os.path.join(d, "parity_prompts.json"), encoding="utf-8"))
    E = json.load(open(os.path.join(d, "parity_expected.json"), encoding="utf-8"))
    cmd = a.runner.split() + [a.python, "-I", "-B", a.script, "--batch"]
    t0 = time.time()
    G = json.loads(subprocess.run(cmd, input=json.dumps(P).encode(), stdout=subprocess.PIPE, check=True).stdout)
    dt = time.time() - t0
    by, bad = {}, 0
    for i, (g, e) in enumerate(zip(G, E)):
        ok = all(g[f] == e[f] for f in ("text", "key", "hit", "route"))
        by.setdefault(e["route"], [0, 0]); by[e["route"]][1] += 1; by[e["route"]][0] += ok
        if not ok:
            bad += 1
            if bad <= 5: print("MISMATCH #%d %r\n  exp %s\n  got %s" % (i, P[i][:80], e, g))
    print("RESULT identical %d/%d (%s) %.3f ms/prompt (incl. interpreter start)"
          % (len(P) - bad, len(P), ", ".join("%s %d/%d" % (k, v[0], v[1]) for k, v in by.items()), dt * 1000 / len(P)))
    return 1 if bad or len(G) != len(P) else 0

if __name__ == "__main__":
    sys.exit(main())
