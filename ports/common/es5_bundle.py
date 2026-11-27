#!/usr/bin/env python3 -B
"""Assemble the ES5 engine bundle: Unicode tables + base64 model + ports/pdf/adom_es5.js.
The result is pure 7-bit ASCII (every non-ASCII code unit becomes \\uXXXX), so it can be pasted
into a PDF stream, a javascript: URL, or a C string without any encoding questions.

    python3 -B ports/common/es5_bundle.py OUT.js
"""
import base64, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from gen_tables import build

MODEL = os.path.join(ROOT, "models", "ADOM-4-Beiduofen-2611.adom")
ENGINE = os.path.join(ROOT, "ports", "pdf", "adom_es5.js")

def ascii_js(src):
    out = []
    for ch in src:
        o = ord(ch)
        if o < 0x80: out.append(ch)
        elif o < 0x10000: out.append("\\u%04x" % o)
        else:
            o -= 0x10000
            out.append("\\u%04x\\u%04x" % (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)))
    return "".join(out)

def bundle(tables=None):
    t = tables or build()
    tj = {"nfkc": t["nfkc"], "lower": t["lower"], "ws": t["ws"], "word": t["word"], "ci": t["ci"]}
    model = base64.b64encode(open(MODEL, "rb").read()).decode()
    src = ("/* ADOM-4-Beiduofen-2611 ES5 bundle. Unicode tables: CPython unicodedata %s */\n" % t["unidata"]
           + "var ADOM_TABLES = " + json.dumps(tj, ensure_ascii=True, separators=(",", ":")) + ";\n"
           + "var ADOM_MODEL_B64 = \"" + model + "\";\n"
           + open(ENGINE, encoding="utf-8").read())
    return ascii_js(src)

if __name__ == "__main__":
    open(sys.argv[1], "w", encoding="ascii").write(bundle())
