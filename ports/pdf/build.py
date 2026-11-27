#!/usr/bin/env python3 -B
"""Build ports/pdf/ADOM-4-Beiduofen-2611.pdf -- a one-page AcroForm whose push button runs the
full ADOM inference in Acrobat JavaScript.  No third-party Python packages; the PDF is written
object by object.

    python3 -B ports/pdf/build.py            # -> ports/pdf/ADOM-4-Beiduofen-2611.pdf

Layout of the JavaScript:
  * document-level script  (Catalog /Names /JavaScript "ADOM-engine"): Unicode tables, the untouched
    .adom model as base64, and the ES5 engine (adom_es5.js).  Runs once when the document opens.
  * push button "infer"    (/A << /S /JavaScript /JS ... >>): reads field "prompt", calls ADOM5.chat,
    writes fields "answer" and "meta".
"""
import os, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from es5_bundle import bundle, MODEL

OUT = os.path.join(HERE, "ADOM-4-Beiduofen-2611.pdf")
BUILD = os.path.join(HERE, "build")

BUTTON_JS = r"""// ADOM-4-Beiduofen-2611: inference button
if (typeof ADOM5 === "undefined") {
  app.alert("ADOM engine not loaded: please enable JavaScript for this document.");
} else {
  try {
    var t0 = new Date().getTime();
    var r = ADOM5.chat(this.getField("prompt").valueAsString);
    var ms = new Date().getTime() - t0;
    this.getField("answer").value = r.text;
    this.getField("meta").value = "route=" + r.route + "; hit=" + r.hit + "; ms=" + ms + "; key=" + r.key;
  } catch (e) {
    app.alert("ADOM inference error: " + e);
  }
}
"""

def pdf_str(s):
    """PDF literal string for ASCII text."""
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"

def pdf_text(s):
    """PDF text string: UTF-16BE with BOM, hex."""
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"

def ucs2_hex(s):
    return "<" + s.encode("utf-16-be").hex().upper() + ">"

class PDF:
    def __init__(self):
        self.objs = []
    def add(self, body):
        self.objs.append(body if isinstance(body, bytes) else body.encode("latin-1"))
        return len(self.objs)
    def set(self, n, body):
        self.objs[n - 1] = body if isinstance(body, bytes) else body.encode("latin-1")
    def stream(self, data, extra="", compress=True):
        if isinstance(data, str): data = data.encode("latin-1")
        if compress:
            data = zlib.compress(data, 9); extra += " /Filter /FlateDecode"
        return b"<< /Length %d%s >>\nstream\n" % (len(data), extra.encode()) + data + b"\nendstream"
    def write(self, path, root):
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offs = []
        for i, body in enumerate(self.objs, 1):
            offs.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(self.objs) + 1)
        for o in offs: out += b"%010d 00000 n \n" % o
        out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(self.objs) + 1, root, self.info, xref)
        open(path, "wb").write(out)
        return len(out)

def main():
    os.makedirs(BUILD, exist_ok=True)
    engine = bundle()
    # model facts are read from the model file at build time (nothing about the model is hard-coded)
    import hashlib
    raw = open(MODEL, "rb").read()
    def varint(buf, p):
        n = sh = 0
        while True:
            b = buf[p]; p += 1; n |= (b & 0x7F) << sh; sh += 7
            if not b & 0x80: return n, p
    _, q = varint(raw, 6); n_params, q = varint(raw, q)
    sha = hashlib.sha256(raw).hexdigest()
    open(os.path.join(BUILD, "doclevel.js"), "w", encoding="ascii").write(engine)
    open(os.path.join(BUILD, "button.js"), "w", encoding="ascii").write(BUTTON_JS)

    p = PDF()
    catalog = p.add("")          # 1, filled later
    pages = p.add("")            # 2
    page = p.add("")             # 3
    helv = p.add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    helvb = p.add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    cour = p.add("<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    cidf = p.add("<< /Type /Font /Subtype /CIDFontType0 /BaseFont /MSung-Light "
                 "/CIDSystemInfo << /Registry (Adobe) /Ordering (CNS1) /Supplement 4 >> "
                 "/FontDescriptor << /Type /FontDescriptor /FontName /MSung-Light /Flags 6 "
                 "/FontBBox [-160 -249 1015 888] /ItalicAngle 0 /Ascent 880 /Descent -120 "
                 "/CapHeight 880 /StemV 93 >> /DW 1000 /W [1 95 500] >>")
    msung = p.add("<< /Type /Font /Subtype /Type0 /BaseFont /MSung-Light-UniCNS-UCS2-H "
                  "/Encoding /UniCNS-UCS2-H /DescendantFonts [%d 0 R] >>" % cidf)
    fonts = "<< /Helv %d 0 R /HeBo %d 0 R /Cour %d 0 R /MSung %d 0 R >>" % (helv, helvb, cour, msung)

    # ---- page content
    W, H = 595, 842
    lines = []
    def text(x, y, font, size, s, cjk=False):
        lines.append("BT /%s %g Tf %g %g Td %s Tj ET" % (font, size, x, y, ucs2_hex(s) if cjk else pdf_str(s)))
    lines.append("0.10 0.16 0.32 rg 0 %d %d 92 re f" % (H - 92, W))
    lines.append("1 1 1 rg")
    text(40, H - 46, "HeBo", 20, "ADOM-4-Beiduofen-2611")
    text(40, H - 70, "Helv", 10.5, "Portable Document Inference Edition  |  {:,} one-bit parameters  |  JavaScript required".format(n_params))
    lines.append("0 0 0 rg")
    text(40, H - 124, "MSung", 13, "輸入題目或題號，按下「推論」。例：115學測社會第1題、台灣價值第3題", cjk=True)
    text(40, H - 142, "Helv", 9.5, "Type a question id or paste a full question (stem + options), then press INFER.")
    text(40, H - 166, "HeBo", 10, "PROMPT")
    lines.append("0.6 g 40 %d %d 1 re f 0 g" % (H - 172, W - 80))
    text(40, H - 418, "HeBo", 10, "ANSWER")
    text(40, H - 548, "HeBo", 10, "TELEMETRY")
    notes = [
        "Inference runs entirely inside this PDF: hash -> ribbon lookup -> canonical Huffman -> text.",
        "The model file is embedded verbatim (base64, {:,} bytes, sha256 {}...) and inflated by hand.".format(len(raw), sha[:12]),
        "Bit-exact with the Python reference on the full parity suite (numbers in ports/pdf/README.md).",
        "No network, no GPU, no BigInt. 64-bit arithmetic is assembled from 16-bit limbs, as nature intended.",
    ]
    for i, s in enumerate(notes):
        text(40, 150 - 14 * i, "Helv", 8.5, s)
    lines.append("0.10 0.16 0.32 rg 0 0 %d 28 re f 1 g" % W)
    text(40, 10, "Helv", 8, "ADOM-4-Beiduofen-2611  |  MMLU-TW (memorised): 100%  |  inference device: your PDF reader")
    content = p.add(p.stream("\n".join(lines)))

    # ---- JavaScript
    js_engine = p.add(p.stream(engine.encode("ascii")))
    js_action = p.add("<< /Type /Action /S /JavaScript /JS %d 0 R >>" % js_engine)
    names_js = p.add("<< /Names [(ADOM-engine) %d 0 R] >>" % js_action)

    # ---- form fields
    def widget(name, rect, extra):
        return ("<< /Type /Annot /Subtype /Widget /F 4 /P %d 0 R /T %s /Rect [%g %g %g %g] %s >>"
                % (page, pdf_str(name), rect[0], rect[1], rect[2], rect[3], extra))
    prompt_rect = (40, H - 400, W - 40, H - 180)
    f_prompt = p.add(widget("prompt", prompt_rect,
        "/FT /Tx /Ff 4096 /DA (/MSung 12 Tf 0 g) /V %s /DV %s /TU %s "
        "/MK << /BG [1 1 1] /BC [0.10 0.16 0.32] >> /BS << /W 1 /S /S >>"
        % (pdf_text(""), pdf_text(""), pdf_text("Prompt"))))
    btn_rect = (W - 160, H - 436, W - 40, H - 408)
    bw, bh = btn_rect[2] - btn_rect[0], btn_rect[3] - btn_rect[1]
    ap = p.add(p.stream("0.10 0.16 0.32 rg 0 0 %g %g re f BT 1 g /HeBo 12 Tf %g 9 Td (INFER) Tj ET" % (bw, bh, bw / 2 - 20),
                        " /Type /XObject /Subtype /Form /BBox [0 0 %g %g] /Resources << /Font %s >>" % (bw, bh, fonts),
                        compress=False))
    f_btn = p.add(widget("infer", btn_rect,
        "/FT /Btn /Ff 65536 /H /P /TU (Run inference) /DA (/HeBo 12 Tf 1 g) "
        "/MK << /BG [0.10 0.16 0.32] /CA (INFER) >> /AP << /N %d 0 R >> "
        "/A << /Type /Action /S /JavaScript /JS %s >>" % (ap, pdf_str(BUTTON_JS))))
    f_answer = p.add(widget("answer", (40, H - 530, W - 40, H - 444),
        "/FT /Tx /Ff 4097 /DA (/MSung 16 Tf 0.05 0.35 0.15 rg) /V () "
        "/MK << /BG [0.95 0.97 0.95] /BC [0.6 0.6 0.6] >> /BS << /W 1 /S /S >>"))
    f_meta = p.add(widget("meta", (40, H - 590, W - 40, H - 556),
        "/FT /Tx /Ff 4097 /DA (/MSung 8 Tf 0.3 g) /V () /MK << /BG [0.96 0.96 0.96] >>"))
    fields = [f_prompt, f_btn, f_answer, f_meta]

    acro = p.add("<< /Fields [%s] /NeedAppearances true /DR << /Font %s >> /DA (/Helv 0 Tf 0 g) >>"
                 % (" ".join("%d 0 R" % f for f in fields), fonts))
    p.set(page, "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Resources << /Font %s >> "
                "/Contents %d 0 R /Annots [%s] >>" % (pages, W, H, fonts, content, " ".join("%d 0 R" % f for f in fields)))
    p.set(pages, "<< /Type /Pages /Kids [%d 0 R] /Count 1 >>" % page)
    p.set(catalog, "<< /Type /Catalog /Pages %d 0 R /AcroForm %d 0 R /Names << /JavaScript %d 0 R >> "
                   "/PageMode /UseNone /ViewerPreferences << /DisplayDocTitle true >> >>" % (pages, acro, names_js))
    p.info = p.add("<< /Title %s /Author (ADOM Labs) /Subject %s /Producer (ports/pdf/build.py) /Creator (ADOM) >>"
                   % (pdf_text("ADOM-4-Beiduofen-2611 — Portable Document Inference Edition"),
                      pdf_text("A 42 KB language model that runs in your PDF reader")))
    n = p.write(OUT, catalog)
    print("wrote %s (%d bytes); doc-level JS %d bytes, button JS %d bytes" % (OUT, n, len(engine), len(BUTTON_JS)))

if __name__ == "__main__":
    main()
