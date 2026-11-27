"""個別修補：舊切題器處理不了的版面 → data/questions/extra_fix.jsonl（extra_* 優先於 exam_pdf）。
目前：92 學測／92 學測補考 英文第 16–20 題「句子配合」——左欄是前半句（題幹），右欄 (A)~(J) 是共用的後半句。"""
import json, re, subprocess, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def answers():
    a = {}
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l); a[f"{r['exam']}|{r['year']}|{r['subject']}|{r['q']}"] = r
    return a

def sentence_matching(pdf, exam, year, qs=range(16, 21)):
    txt = unicodedata.normalize("NFKC", subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout)
    lines = txt.splitlines()
    i0 = next(i for i, l in enumerate(lines) if re.match(rf"^\s*{qs[0]}\.", l))
    stems, pool = {}, {}
    for l in lines[i0:i0 + 20]:
        m = re.match(r"^\s*(\d{1,2})\.\s*(.*?)\s{2,}\(\s*([A-J])\s*\)\s*(.*)$", l)
        if m:
            stems[int(m.group(1))] = m.group(2).strip(); pool[m.group(3)] = m.group(4).strip(); continue
        m = re.match(r"^\s*\(\s*([A-J])\s*\)\s*(.*)$", l)
        if m: pool[m.group(1)] = m.group(2).strip()
        if len(pool) == 10 and len(stems) == len(qs): break
    assert sorted(stems) == list(qs) and len(pool) == 10, (pdf.name, stems, pool)
    A = answers(); out = []
    for q in qs:
        k = f"{exam}|{year}|英文|{q}"
        out.append({"key": k, "exam": exam, "year": year, "subject": "英文", "q": str(q), "stem": stems[q],
                    "options": dict(sorted(pool.items())), "answer": A[k]["answer"], "accept": A[k]["accept"],
                    "src": pdf.name, "note": "句子配合：共用選項池"})
    return out

if __name__ == "__main__":
    Q = ROOT / "data/raw/gsat/Q_"
    rows = sentence_matching(Q / "92學年度學科能力測驗－英文__試題內容.pdf", "GSAT", 92)
    rows += sentence_matching(Q / "92學年度學科能力測驗(補考)－英文__試題內容.pdf", "GSAT-makeup", 92)
    with open(ROOT / "data/questions/extra_fix.jsonl", "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for r in rows: print(r["key"], r["answer"], "|", r["stem"])
