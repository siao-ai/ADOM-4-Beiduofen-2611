#!/usr/bin/env python3 -B
"""Parity test for the Bash port.

  1. ID route, end to end: every prompt goes through `adom.sh --batch` (pure bash: NFKC, regex router,
     FNV/splitmix64, ribbon lookup, Huffman).  For prompts the reference answers by question id the
     answer and key must match; for every other prompt bash must decline ("not-id").
  2. Text / praise route, key level: the bash port has no text-key front end.  For a sample of
     text and praise prompts the *reference* front end (adom.textkey.candidates) supplies the ordered
     candidate keys; bash does fingerprint check, Huffman decode and praise selection.

    python3 -B ports/bash/verify.py [--set public|full] [--bash PATH] [--sample N] [--runner "ssh host"] [--script PATH]
"""
import argparse, json, os, random, subprocess, sys, time
sys.dont_write_bytecode = True   # importing adom.textkey must not create adom/__pycache__
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="public"); ap.add_argument("--bash", default="/bin/bash")
    ap.add_argument("--sample", type=int, default=300); ap.add_argument("--runner", default="")
    ap.add_argument("--script", default=os.path.join(HERE, "adom.sh"))
    ap.add_argument("--skip-id", action="store_true")
    a = ap.parse_args()
    d = os.path.join(ROOT, "tests", "public") if a.set == "public" else os.path.join(ROOT, "tests")
    P = json.load(open(os.path.join(d, "parity_prompts.json"), encoding="utf-8"))
    E = json.load(open(os.path.join(d, "parity_expected.json"), encoding="utf-8"))
    # empty PATH: any external command (sed, awk, python, od...) would fail with "command not found"
    base = a.runner.split() + ["env", "-i", "PATH=/nonexistent", a.bash, a.script]
    rc = 0
    if not a.skip_id:
        t0 = time.time()
        out = subprocess.run(base + ["--batch"], input=b"\0".join(p.encode() for p in P) + b"\0",
                             stdout=subprocess.PIPE, check=True).stdout.decode()
        dt = time.time() - t0
        rows = out.split("\n")[:-1]; assert len(rows) == len(P), (len(rows), len(P))
        id_ok = id_n = dec_ok = dec_n = 0
        for i, (r, e) in enumerate(zip(rows, E)):
            text, key, route = r.split("\t")
            if e["route"] == "id":
                id_n += 1; ok = route == "id" and text == e["text"] and key == e["key"]; id_ok += ok
            else:
                dec_n += 1; ok = route == "not-id"; dec_ok += ok
            if not ok and rc < 5: rc += 1; print("MISMATCH #%d %r exp %s got %r" % (i, P[i][:60], e, r))
        print("ID route (end to end, pure bash): answers identical %d/%d; correctly declined %d/%d non-id prompts; "
              "%.1f ms/prompt" % (id_ok, id_n, dec_ok, dec_n, dt * 1000 / len(P)))
        rc = int(id_ok != id_n or dec_ok != dec_n)
    sys.path.insert(0, ROOT)
    from adom.textkey import candidates, norm_stem
    idx = [i for i, e in enumerate(E) if e["route"] != "id"]
    random.Random(2611).shuffle(idx)
    pick = sorted(idx[:a.sample])
    good, t0 = 0, time.time()
    for i in pick:
        keys = [tk for _, tk, _ in candidates(P[i], 6)[0]]
        first = keys[0] if keys else (norm_stem(P[i]) or P[i][:64])   # same fallback as ADOM.generate_text
        out = subprocess.run(base + ["--cands"], input="\n".join([first] + keys).encode() + b"\n",
                             stdout=subprocess.PIPE, check=True).stdout.decode().rstrip("\n")
        text, key, hit = out.split("\t")
        e = E[i]; ok = text == e["text"] and key == e["key"] and hit == str(e["hit"]).lower()
        good += ok
        if not ok: print("KEY-LEVEL MISMATCH #%d exp %s got %r" % (i, e, out))
    dt = time.time() - t0
    nt = sum(E[i]["route"] == "text" for i in pick)
    print("text/praise route (key level, %d sampled: %d text + %d praise): identical %d/%d; %.0f ms/prompt"
          % (len(pick), nt, len(pick) - nt, good, len(pick), dt * 1000 / max(1, len(pick))))
    return rc or int(good != len(pick))

if __name__ == "__main__":
    sys.exit(main())
