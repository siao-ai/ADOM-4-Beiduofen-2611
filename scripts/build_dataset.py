"""合併所有答案來源 → data/answers/all.jsonl。
掃描卷：vision_A 與 vision_B 兩份獨立轉錄必須一致；不一致者依 adjudicated.jsonl 裁決，否則報錯。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "data/answers"

def rd(p):
    return [json.loads(l) for l in open(p)] if p.exists() else []

def k(r): return (r["exam"], r["year"], r["subject"], r["q"])

def vision():
    va, vb = rd(A / "vision_A.jsonl"), rd(A / "vision_B.jsonl")
    if not vb: return [], []
    adj = {k(r): r for r in rd(A / "adjudicated.jsonl")}
    def idx(rows):
        d = {}
        for r in rows:
            if r.get("note", "").startswith("版本2"): continue   # 88 數學：只留格號版
            if r["year"] == 85 and r["subject"] == "數學" and r["q"] in "ABCDEF" and len(r["q"]) == 1:
                r = {**r, "q": str(15 + "ABCDEF".index(r["q"]))}  # 85 數學填充：統一用卷面題號 15–20
            assert k(r) not in d, ("轉錄內重複鍵", k(r))
            d[k(r)] = r
        return d
    da, db = idx(va), idx(vb)
    out, conflicts = [], []
    for key in sorted(set(da) | set(db), key=str):
        if key in adj: out.append(adj[key]); continue
        a, b = da.get(key), db.get(key)
        if a and b and a["answer"] == b["answer"] and sorted(a["accept"]) == sorted(b["accept"]):
            out.append({**a, "src": "scan(A=B)"})
        else:
            conflicts.append((key, a and (a["answer"], a["accept"], a.get("note")), b and (b["answer"], b["accept"], b.get("note"))))
    return out, conflicts

def main():
    rows = rd(A / "gsat_text.jsonl") + rd(A / "cap.jsonl") + rd(A / "cap103_manual.jsonl")
    v, conflicts = vision()
    have = {k(r) for r in rows}
    rows += [r for r in v if k(r) not in have]
    rows += rd(A / "twv.jsonl")
    if conflicts:
        print(f"掃描卷 A/B 不一致 {len(conflicts)} 格：")
        for c in conflicts: print(" ", c)
        if "--allow-conflicts" not in sys.argv: sys.exit(1)
    seen = set()
    with open(A / "all.jsonl", "w") as f:
        for r in rows:
            assert k(r) not in seen, k(r); seen.add(k(r))
            f.write(json.dumps({x: r[x] for x in ("exam", "year", "subject", "q", "answer", "accept", "src") if x in r}, ensure_ascii=False) + "\n")
    print("all.jsonl", len(rows))

if __name__ == "__main__":
    main()
