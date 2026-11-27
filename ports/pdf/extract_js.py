#!/usr/bin/env python3
"""Pull the JavaScript back out of the built PDF with an independent parser (pikepdf / libqpdf),
so the parity test runs on the bytes that are actually inside the PDF, not on the build inputs.

    uv run --with pikepdf python ports/pdf/extract_js.py ports/pdf/ADOM-4-Beiduofen-2611.pdf OUTDIR

Writes OUTDIR/doclevel.js and OUTDIR/button.js, prints a structural report, exits non-zero on problems.
"""
import os, sys
import pikepdf

def js_of(action):
    js = action.get("/JS")
    if js is None: return None
    if isinstance(js, pikepdf.Stream): return js.read_bytes().decode("latin-1")
    return str(js)

def main(path, outdir):
    os.makedirs(outdir, exist_ok=True)
    pdf = pikepdf.open(path)
    # libqpdf's checks (what `qpdf --check` runs): xref/object syntax, every stream decodes, page tree is sane
    problems = list(pdf.check_pdf_syntax())
    pdf._check_document_structures()
    print("libqpdf %s check_pdf_syntax: %s" % (pikepdf.__libqpdf_version__, "no problems" if not problems else problems))
    print("linearized:", pdf.is_linearized, "| pages:", len(pdf.pages), "| PDF version:", pdf.pdf_version)
    root = pdf.Root
    acro = root.get("/AcroForm")
    assert acro is not None, "no /AcroForm"
    names = [str(f.get("/T")) for f in acro.Fields]
    print("AcroForm fields:", ", ".join("%s(%s)" % (str(f.get("/T")), str(f.get("/FT"))) for f in acro.Fields))
    buttons = [f for f in acro.Fields if f.get("/FT") == pikepdf.Name("/Btn")]
    assert len(buttons) == 1, "expected exactly one button"
    b = buttons[0]
    assert int(b.get("/Ff", 0)) & (1 << 16), "button is not a push button"
    a = b.get("/A")
    assert a is not None and a.get("/S") == pikepdf.Name("/JavaScript"), "button has no JavaScript action"
    btn = js_of(a)
    print("button '%s' /A /S /JavaScript: %d bytes of JS" % (str(b.T), len(btn)))
    # document-level scripts: Catalog /Names /JavaScript name tree
    tree = root.Names.JavaScript
    arr = tree.Names
    doc = []
    for i in range(0, len(arr), 2):
        s = js_of(arr[i + 1])
        print("document-level script '%s': %d bytes" % (str(arr[i]), len(s)))
        doc.append(s)
    doc = "\n".join(doc)
    for name, s in (("doclevel.js", doc), ("button.js", btn)):
        assert all(ord(c) < 128 for c in s), name + " is not pure ASCII"
        open(os.path.join(outdir, name), "w", encoding="ascii").write(s)
    assert "ADOM5.chat" in btn and "getField" in btn
    assert {"prompt", "infer", "answer", "meta"} <= set(names)
    print("extracted ->", outdir)
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
