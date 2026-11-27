"""解析會考參考答案一覽表（欄位依表頭文字位置對齊）→ data/answers/cap.jsonl"""
import json, re, subprocess, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/cap"
LABELS = [("國文", "國文"), ("閱讀", "英語閱讀"), ("聽力", "英語聽力"), ("英語", "英語閱讀"),
          ("數學", "數學"), ("社會", "社會"), ("自然", "自然")]

def heads(lines):
    pos = {}
    for l in lines[:12]:
        for lab, sub in LABELS:
            for m in re.finditer(lab, l):
                c = m.start() + len(lab) / 2
                if sub == "英語閱讀" and lab == "英語" and ("閱讀" in "".join(lines[:12])): continue
                pos.setdefault(sub, c)
    return pos

def parse_file(fn):
    txt = subprocess.run(["pdftotext", "-layout", str(fn), "-"], capture_output=True, text=True).stdout
    out, notes = {}, []
    for page in txt.split("\f"):
        lines = page.splitlines()
        pos = heads(lines)
        if not pos: continue
        for l in lines:
            m = re.match(r"^\s*(\d{1,2})\s", l)
            if not m: notes.append(l.strip()) if l.strip() and "題" not in l else None; continue
            q = m.group(1)
            for t in re.finditer(r"(?<=\s)([A-D](?:\s*或\s*[A-D])*|\*|＊|送分)(?=\s|$)", l):
                c = t.start() + len(t.group(1)) / 2
                sub = min(pos, key=lambda s: abs(pos[s] - c))
                if abs(pos[sub] - c) > 4: raise ValueError(f"{fn.name} q{q} far col {l!r}")
                key = (sub, q)
                if key in out: raise ValueError(f"{fn.name} dup {key} {l!r}")
                out[key] = t.group(1)
    return out, [n for n in notes if n]

if __name__ == "__main__":
    rows = []
    for fn in sorted(SRC.glob("*__參考答案.pdf")):
        year = int(fn.name.split("__")[0])
        ans, notes = parse_file(fn)
        subs = sorted({s for s, _ in ans})
        summ = []
        for s in subs:
            qs = sorted(int(q) for ss, q in ans if ss == s)
            ok = qs == list(range(1, len(qs) + 1))
            summ.append(f"{s}{len(qs)}{'' if ok else '!GAP'}")
        print(year, " ".join(summ), "| notes:", " / ".join(notes)[:150])
        for (s, q), a in sorted(ans.items(), key=lambda x: (x[0][0], int(x[0][1]))):
            acc = re.split(r"\s*或\s*", a)
            rows.append({"exam": "CAP", "year": year, "subject": s, "q": q, "answer": acc[0], "accept": acc, "src": fn.name})
    (ROOT / "data/answers").mkdir(exist_ok=True)
    with open(ROOT / "data/answers/cap.jsonl", "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("rows", len(rows))
