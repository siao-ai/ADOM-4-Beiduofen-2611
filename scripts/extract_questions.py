"""從題本（PDF 文字層或 docx）切出每一題的題幹與選項 → data/questions/<來源>.jsonl
每行：{"key": 題號鍵, "stem": 題幹, "options": {"A": ...}, "src": 檔名, "kind": "pdf|docx"}
驗收：每卷抽出的題號集合 vs all.jsonl 的題號集合（選填格 13-1 視為第 13 題）。"""
import json, re, subprocess, sys, unicodedata, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def pdf_text(p):
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout

def docx_text(p):
    with zipfile.ZipFile(p) as z:
        x = z.read("word/document.xml").decode("utf-8")
    x = re.sub(r"<w:tab/>", "\t", x)
    paras = re.findall(r"<w:p[ >].*?</w:p>", x, re.S)
    out = []
    for para in paras:
        out.append("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para)))
    import html
    return html.unescape("\n".join(out))

JUNK = re.compile(r"(第\s*\d+\s*頁|共\s*\d+\s*頁|^\s*-\s*\d+\s*-\s*$|請記得在答題卷|^\s*\d+\s*年\s*學測|考科\s*$|-\s*\d+\s*-|請翻頁|背面尚有試題|^\s*第\s*\d+\s*頁\s*$)")
SECTION = re.compile(r"(第[壹貳參肆伍]部分|說明：|^\s*[一二三四五六七八九十]+、|第\s*\d+\s*至\s*\d+\s*題為題組|^\s*\d+\s*-\s*\d+\s*題為題組)")
QSTART = re.compile(r"^\s*(\d(?:\s?\d)?)\s*[\.．、](?!\d+(?:\s|$))\s*(.*)$")
OPT = re.compile(r"[\(（]\s*([A-E])\s*[\)）]")

def clean_lines(text):
    lines = []
    for l in unicodedata.normalize("NFKC", text).replace("\f", "\n").splitlines():
        if JUNK.search(l): continue
        lines.append(l.rstrip())
    return lines

def has_options_ahead(lines, i, span=60):
    """題目開頭之後、下一個題號之前，要看得到選項標記（排除封面說明「1. 所有試題均為…」）。
    數學選填題沒有 (A)，改看「選填」字樣或題組格號。"""
    for l in lines[i + 1:i + span] if not OPT.search(lines[i]) else []:
        if QSTART.match(l): return False
        if OPT.search(l) or re.search(r"[\(（]\s*[1-5]\s*[\)）]", l): return True
    return bool(OPT.search(lines[i])) or bool(re.search(r"[\(（]\s*[1-5]\s*[\)）]", lines[i]))

def segment(text, expected):
    """expected：該卷應有的主題號（int）集合。依序尋找題號開頭，只接受遞增且在 expected 內的。"""
    lines = clean_lines(text)
    exp = sorted(expected)
    # 封面作答說明也有「1. 2. 3.」：從全卷第一個選項標記往前最近的題號開始掃
    first_opt = next((i for i, l in enumerate(lines) if OPT.search(l)), 0)
    begin = max([i for i in range(first_opt + 1) if QSTART.match(lines[i])] or [0])
    starts = []  # (line_idx, qnum)
    want_i = 0
    for i, l in enumerate(lines):
        m = QSTART.match(l)
        if not m or want_i >= len(exp): continue
        n = int(m.group(1).replace(" ", ""))
        # 允許跳過不在 expected 的題號（非選題）；只接受下一個期望或之後的
        if n in expected and n >= exp[want_i] and (not starts or n > starts[-1][1]) and i >= begin:
            while exp[want_i] < n: want_i += 1
            starts.append((i, n)); want_i += 1
    out = {}
    for j, (i, n) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
        block = []
        for l in lines[i:end]:
            if block and (SECTION.search(l) or SECTION.search(re.sub(r"\s", "", l)) or QSTART.match(l) or re.search(r"背面還有試題|^\s*第[一二三四五六七八九十]+題\s*[\(（]", l)):
                break   # 下一題（含非選題）、下一個題組／大題說明開始
            block.append(l)
        block[0] = QSTART.match(block[0]).group(2)
        body = "\n".join(block).strip()
        parts = OPT.split(body)
        stem = parts[0].strip()
        opts = {parts[k]: parts[k + 1].strip() for k in range(1, len(parts) - 1, 2)}
        out[n] = {"stem": stem, "options": opts}
    return out

def expected_by_paper():
    exp = {}
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l)
        if r["exam"] == "TWV": continue
        m = re.match(r"^(\d+)", r["q"])
        if not m or r["q"].startswith("P2-") or r["q"].isalpha(): continue
        exp.setdefault((r["exam"], r["year"], r["subject"]), set()).add(int(m.group(1)))
    return exp

def _single():
    exam, year, subject, path = sys.argv[1], int(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    exp = expected_by_paper()[(exam, year, subject)]
    text = docx_text(path) if path.suffix == ".docx" else pdf_text(path)
    seg = segment(text, exp)
    missing = sorted(exp - set(seg))
    print(f"{exam} {year} {subject} [{path.suffix}] 抽到 {len(seg)}/{len(exp)}  缺 {missing}")
    for n in sorted(seg)[:3] + sorted(seg)[-2:]:
        s = seg[n]; print(f"  {n}: {s['stem'][:60]!r}  opts={list(s['options'])}")

# ---------------- 批次模式 ----------------
CAP_SUBJ = {"國文科": "國文", "英語（閱讀）": "英語閱讀", "英語(閱讀)": "英語閱讀", "英語科": "英語閱讀", "數學科": "數學", "社會科": "社會", "自然科": "自然"}

def papers(kind):
    """列出 (exam, year, subject, path)。kind = pdf | docx"""
    out = []
    gdir = ROOT / ("data/raw/gsat/Q_" if kind == "pdf" else "data/raw/gsat/D_")
    for p in sorted(gdir.glob("*.pdf" if kind == "pdf" else "*.docx")):
        m = re.match(r"(\d+)學年度學科能力測驗(\(補考\))?－(.+?)(?:（選擇題）)?(?:__|\.docx)", p.name)
        if not m: continue
        out.append(("GSAT-makeup" if m.group(2) else "GSAT", int(m.group(1)), m.group(3), p))
    if kind == "pdf":
        for p in sorted((ROOT / "data/raw/cap").glob("*.pdf")):
            y, lab = p.stem.split("__")
            if lab in CAP_SUBJ: out.append(("CAP", int(y), CAP_SUBJ[lab], p))
    return out

def batch(kind):
    exp = expected_by_paper()
    ans = {}
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l); ans[(r["exam"], r["year"], r["subject"], r["q"])] = r
    rows, report = [], []
    for exam, year, subject, path in papers(kind):
        e = exp.get((exam, year, subject))
        if not e: continue
        text = docx_text(path) if kind == "docx" else pdf_text(path)
        if len(re.sub(r"\s", "", text)) < 200:
            report.append((exam, year, subject, 0, len(e), "掃描檔（無文字層）")); continue
        seg = segment(text, e)
        for n, s in seg.items():
            cells = sorted([r for (ex, y, su, q), r in ans.items() if (ex, y, su) == (exam, year, subject) and re.fullmatch(rf"{n}(-\d+)?", q)],
                           key=lambda r: [int(x) for x in r["q"].split("-")])
            if not cells: continue
            if len(cells) == 1:
                a, acc = cells[0]["answer"], cells[0]["accept"]
            else:  # 選填多格 → 串成一個答案
                a = "".join(c["answer"] for c in cells); acc = [a]
            rows.append({"key": f"{exam}|{year}|{subject}|{n}", "exam": exam, "year": year, "subject": subject, "q": str(n),
                         "stem": s["stem"], "options": s["options"], "answer": a, "accept": acc, "src": path.name, "kind": kind})
        report.append((exam, year, subject, len(seg), len(e), ""))
    out = ROOT / "data/questions"; out.mkdir(exist_ok=True)
    with open(out / f"exam_{kind}.jsonl", "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    got = sum(x[3] for x in report); tot = sum(x[4] for x in report)
    print(f"[{kind}] 抽到 {got}/{tot} 題（以主題號計）  → data/questions/exam_{kind}.jsonl")
    for x in report:
        if x[3] < x[4]: print("   ", *x)

if __name__ == "__main__":
    if sys.argv[1] in ("pdf", "docx"): batch(sys.argv[1])
    else: _single()
