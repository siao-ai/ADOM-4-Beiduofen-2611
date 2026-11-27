"""解析學測文字型答案 PDF → data/answers/gsat.jsonl。無法乾淨解析者列入 flagged。"""
import json, re, subprocess, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/gsat/A_"
QID = re.compile(r"^(\d{1,2})(?:-(\d))?$")
ANS = re.compile(r"^(?:[A-O]{1,6}|[0-9]{1,6}|[0-9](?:,[0-9])+|[-±]|／|/|\*)$")

def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return (s.replace("，", ",").replace("－", "-").replace("−", "-").replace("–", "-").replace("—", "-")
             .replace("無答案", "*")).replace("＊", "*")

def norm_line(s):
    s = re.sub(r"(\d)\*", r"\1", norm(s))
    return re.sub(r"(?<=\s)註\s?\d?(?=\s|$)", "*", s)

def meta(fn):
    m = re.match(r"(\d+)學年度學科能力測驗(\(補考\))?－(.+?)(?:（選擇題）)?__", fn.name)
    return {"exam": "GSAT" + ("-makeup" if m.group(2) else ""), "year": int(m.group(1)), "subject": m.group(3)}

def parse(text):
    out = {}
    # 把「X 或 Y」先合併成一個 token
    text = norm_line(text)
    text = re.sub(r"([A-O0-9,]+)\s*\(\s*或\s*([A-O0-9,]+)\s*\)", r"\1|\2", text)
    text = re.sub(r"([A-O0-9,]+)[ \t]*或[ \t]*\n[ \t]*(\d{1,2})[ \t]*\n[ \t]*([A-O0-9,]+)", r"\2 \1|\3", text)
    text = re.sub(r"([A-O0-9,]+)[ \t]*或[ \t]*([A-O0-9,]+)", r"\1|\2", text)
    for line in text.splitlines():
        if "※" in line or "說明" in line: continue
        toks = line.split()
        i = 0
        while i < len(toks) - 1:
            q, a = toks[i], toks[i + 1]
            if QID.match(q) and all(ANS.match(x) for x in a.split("|")):
                out.setdefault(q, a); i += 2
            elif QID.match(q) and i + 2 < len(toks) and QID.match(toks[i + 1]) and "-" in toks[i + 1]:
                i += 1  # 題組標頭（例：13  13-1  9）
            else:
                i += 1
    return out

SUBJ_CH = [("英", "英文"), ("國", "國文"), ("国", "國文"), ("數", "數學"), ("数", "數學"),
           ("社", "社會"), ("自", "自然"), ("然", "自然")]

def sections(text):
    """合併檔（一個 PDF 含多科）依「X考科」標題切段；回傳 {科目: 文字}。"""
    lines = unicodedata.normalize("NFKC", text).splitlines()
    heads = []
    for i, l in enumerate(lines):
        if "考科" in l:
            for ch, sub in SUBJ_CH:
                if ch in l.split("考科")[0][-6:]:
                    heads.append((i, sub)); break
    if len({s for _, s in heads}) <= 1: return None
    out = {}
    for j, (i, sub) in enumerate(heads):
        end = heads[j + 1][0] if j + 1 < len(heads) else len(lines)
        out.setdefault(sub, "\n".join(lines[i:end]))
    return out

def key(q):
    m = QID.match(q); return (int(m.group(1)), int(m.group(2) or 0))

def check(ans):
    ks = sorted(ans, key=key)
    mains = sorted({key(k)[0] for k in ks})
    return mains == list(range(1, max(mains) + 1)) if mains else False

if __name__ == "__main__":
    rows, flagged = [], []
    seen_md5 = set()
    for fn in sorted(SRC.glob("*.pdf")):
        txt = subprocess.run(["pdftotext", "-layout", str(fn), "-"], capture_output=True, text=True).stdout
        if "題號" not in txt: flagged.append((fn.name, "no-text")); continue
        m = meta(fn)
        secs = sections(txt)
        if secs is not None:
            if m["subject"] not in secs: flagged.append((fn.name, "no-section")); continue
            txt = secs[m["subject"]]
        ans = parse(txt)
        ok = check(ans)
        if not ok: flagged.append((fn.name, f"noncontiguous n={len(ans)}"))
        for q in sorted(ans, key=key):
            a = ans[q]
            if a in ("／", "/"): continue
            rows.append({**m, "q": q, "answer": a.split("|")[0], "accept": a.split("|"), "src": fn.name})
    out = ROOT / "data/answers"; out.mkdir(parents=True, exist_ok=True)
    with open(out / "gsat_text.jsonl", "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("rows", len(rows)); print("flagged", len(flagged))
    for x in flagged: print(" ", *x)
