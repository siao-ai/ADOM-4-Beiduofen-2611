"""題目文字覆蓋率檢查：data/questions/*.jsonl（docx 除外）聯集 vs all.jsonl。
- 以「題」計：選填格 13-1/13-2 合成第 13 題（答案串接）；P2-3、A 這類題號照原樣
- 每列答案必須等於官方答案（串接後），否則列為 BAD
用法：python3 scripts/check_coverage.py [--paper GSAT|115|數學A] [--missing]"""
import collections, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def question_units():
    """官方答案 → {題鍵: (answer, accept)}；選填格合併。"""
    cells = collections.defaultdict(list)
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l)
        m = re.fullmatch(r"(\d+)-(\d+)", r["q"])
        if m and r["exam"].startswith("GSAT"):
            cells[(r["exam"], r["year"], r["subject"], m.group(1))].append((int(m.group(2)), r))
        else:
            cells[(r["exam"], r["year"], r["subject"], r["q"])].append((0, r))
    out = {}
    for k, v in cells.items():
        v.sort(key=lambda x: x[0])
        if len(v) == 1: out["|".join(map(str, k))] = (v[0][1]["answer"], v[0][1]["accept"])
        else:
            a = "".join(r["answer"] for _, r in v); out["|".join(map(str, k))] = (a, [a])
    return out

def main():
    units = question_units()
    have, bad = {}, []
    sys.path.insert(0, str(ROOT / "scripts"))
    from qsource import pdf_rows, docx_rows, twv_rows
    src = docx_rows() if "--docx" in sys.argv else pdf_rows() + twv_rows()
    rows = [(r.get("src", "?"), r) for r in src]
    for pname, r in rows:
        p = type("P", (), {"name": pname})
        if r.get("cells"):   # 舊制數學填充：一題（字母）對應多個官方格號 → 官方各格答案串接
            paper = r["key"].rsplit("|", 1)[0]
            ck = [f"{paper}|{c}" for c in r["cells"]]
            if not all(c in units for c in ck): bad.append((p.name, r["key"], "cells 不在官方題號內")); continue
            a = "".join(units[c][0] for c in ck)
            if r["answer"] != a: bad.append((p.name, r["key"], f"答案 {r['answer']} ≠ 官方各格串接 {a}")); continue
            for c in ck: have.setdefault(c, p.name)
            continue
        if True:
            k = r["key"]
            if k not in units: bad.append((p.name, k, "不在官方題號內")); continue
            a, acc = units[k]
            if r["answer"] != a and r["answer"] not in acc: bad.append((p.name, k, f"答案 {r['answer']} ≠ 官方 {a}")); continue
            if not (r.get("stem") or "").strip() and not r.get("options"): bad.append((p.name, k, "題幹與選項皆空")); continue
            have.setdefault(k, p.name)
    by = collections.defaultdict(lambda: [0, 0, []])
    for k in units:
        paper = k.rsplit("|", 1)[0]
        by[paper][1] += 1
        if k in have: by[paper][0] += 1
        else: by[paper][2].append(k.rsplit("|", 1)[1])
    only = sys.argv[sys.argv.index("--paper") + 1] if "--paper" in sys.argv else None
    tot_h = sum(v[0] for v in by.values()); tot = sum(v[1] for v in by.values())
    print(f"有題目文字：{tot_h}/{tot} 題（{tot_h / tot:.1%}）  BAD {len(bad)}")
    for paper in sorted(by, key=lambda x: (x.split("|")[0], int(x.split("|")[1]), x)):
        h, n, miss = by[paper]
        if only and paper != only: continue
        if h < n and ("--missing" in sys.argv or only):
            print(f"  {paper}: {h}/{n}  缺 {miss}")
    for b in bad[:40]: print("  BAD", *b)

if __name__ == "__main__":
    main()
