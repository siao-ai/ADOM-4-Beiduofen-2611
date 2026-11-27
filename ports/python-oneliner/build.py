#!/usr/bin/env python3 -B
"""Collapse oneliner_src.pyexpr into adom1.py: ONE line, ONE expression statement, with the model
(read from models/ at build time) inlined as base64.  Proof of one-line-ness is checked with ast."""
import ast, base64, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

def main():
    model = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "models", "ADOM-4-Beiduofen-2611.adom")
    src = open(os.path.join(HERE, "oneliner_src.pyexpr"), encoding="utf-8").read()
    one = re.sub(r"\n\s*", "", src.strip())          # the source never needs a newline outside brackets
    one = one.replace("@@MODEL@@", base64.b64encode(open(model, "rb").read()).decode())
    tree = ast.parse(one)
    assert "\n" not in one and len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr), "not a single expression"
    out = os.path.join(HERE, "adom1.py")
    open(out, "w", encoding="utf-8").write(one + "\n")
    code = len(one) - len(base64.b64encode(open(model, "rb").read()))
    print("wrote %s: 1 line, 1 expression, %d chars (%d of code + base64 model)" % (out, len(one), code))

if __name__ == "__main__":
    main()
