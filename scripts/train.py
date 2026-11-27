"""「訓練」ADOM-4-Beiduofen-2611：建 Huffman 樹 → 列方程式 → 解 ribbon → 存檔。
  --mode id|text|both   只認題號／只認題目文字／兩者都認（預設 both）
  --f 12 --Kmin 6  文字路徑的指紋位數與最短題幹"""
import argparse, collections, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adom.model import key_of, context_of, save, text_fingerprint
from adom.codec import huffman_lengths, canonical
from adom.hashing import fnv1a64
from adom.textkey import build_key, build_stem_key
from adom import ribbon

def rd(p): return [json.loads(l) for l in open(p, encoding="utf-8")] if Path(p).exists() else []

def text_items(K, Kmin):
    """題目文字 → (文字鍵, 可接受答案, 來源鍵)。
    共用文章的題目（blank=True）或同鍵不同答者，鍵加「#題號」；加了還撞就丟掉並回報。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from qsource import pdf_rows, docx_rows, twv_rows
    rows = pdf_rows() + docx_rows() + twv_rows()
    byk = {}
    for r in rows: byk.setdefault((r["key"], build_key(r["stem"], r["options"])), r)   # 同一題多個來源文字都收
    rows = list(byk.values())
    def num(r): return r.get("q") or r["key"].rsplit("|", 1)[1]
    # 第一層：只看題幹。題幹夠長、而且同題幹的題目答案都一樣（通常就是同一題的 PDF/docx 兩個版本）→ 存題幹鍵
    items, conflicts = [], []
    by_stem = collections.defaultdict(list)
    for r in rows:
        sk = build_stem_key(r["stem"], r["options"])
        if len(sk) - 2 >= Kmin and not r.get("blank"): by_stem[sk].append(r)
    stem_done = set()
    for sk, rs in by_stem.items():
        if len({tuple(r["accept"]) for r in rs}) == 1 and len({r["key"] for r in rs}) == 1:
            items.append((sk, rs[0]["accept"], [rs[0]["key"]])); stem_done.update(id(r) for r in rs)
    # 第二層：題幹撞到或太短 → 題幹＋選項鍵；再撞 → 加題號
    base = collections.defaultdict(list)
    short = 0
    for r in rows:
        if id(r) in stem_done: continue
        k = build_key(r["stem"], r["options"])
        st, op = k.split("|")
        if len(st) < Kmin and not op:
            if st: base[k].append({**r, "blank": True})   # 極短題幹：強制加題號
            else: short += 1
            continue
        base[k].append(r)
    for k, rs in base.items():
        answers = {tuple(r["accept"]) for r in rs}
        if len(rs) == 1 and not rs[0].get("blank"):
            items.append((k, rs[0]["accept"], [rs[0]["key"]])); continue
        if len(answers) == 1 and not any(r.get("blank") for r in rs):
            items.append((k, rs[0]["accept"], [r["key"] for r in rs])); continue
        sub = collections.defaultdict(list)
        for r in rs: sub[k + "#" + num(r)].append(r)
        for k2, rs2 in sub.items():
            if len({tuple(r["accept"]) for r in rs2}) == 1: items.append((k2, rs2[0]["accept"], [r["key"] for r in rs2]))
            else: conflicts.append((k2, [r["key"] for r in rs2]))
    return items, conflicts, short, len(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="both", choices=["id", "text", "both"])
    ap.add_argument("--f", type=int, default=20); ap.add_argument("--Kmin", type=int, default=6)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    eqs_src = []  # (key, ctx, accept)
    if a.mode in ("id", "both"):
        seen = set()
        for r in rd(ROOT / "data/answers/all.jsonl"):
            k = key_of(r["exam"], r["year"], r["subject"], r["q"])
            assert k not in seen, k; seen.add(k)
            eqs_src.append((k, context_of(k), r["accept"] if r["answer"] != "*" else ["*"], r["answer"]))
    titems = []
    if a.mode in ("text", "both"):
        titems, conflicts, short, total = text_items(None, a.Kmin)
        print(f"文字路徑：{total} 題有題目文字 → {len(titems)} 個文字鍵（同鍵不同答丟掉 {len(conflicts)} 組、過短 {short} 題）")
        for tk, acc, keys in titems:
            eqs_src.append(("T|" + tk, "TEXT", acc, acc[0]))
        json.dump({"items": [[tk, acc, keys] for tk, acc, keys in titems], "conflicts": conflicts},
                  open(ROOT / "reports/text_keys.json", "w"), ensure_ascii=False)
        for c in conflicts[:20]: print("   同鍵不同答：", c)
    freq = collections.defaultdict(collections.Counter)
    for k, ctx, acc, ans in eqs_src:
        if ans != "*": freq[ctx][ans] += 1
    lengths = {c: huffman_lengths(f) for c, f in freq.items()}
    codes = {c: canonical(L) for c, L in lengths.items()}
    eqs, skipped = [], 0
    for k, ctx, acc, ans in eqs_src:
        base = fnv1a64(k.encode())
        off = 0
        if ctx == "TEXT":
            fp = text_fingerprint(k[2:], a.f)
            for i in range(a.f): eqs.append((base, i, (fp >> (a.f - 1 - i)) & 1))
            off = a.f
        if ans == "*": skipped += 1; continue
        cb = codes[ctx]
        code, l = min((cb[x] for x in acc if x in cb), key=lambda x: x[1])
        for i in range(l): eqs.append((base, off + i, (code >> (l - 1 - i)) & 1))
    n = len(eqs)
    print(f"模式 {a.mode}：方程式 {n} 條（送分 {skipped} 題不佔答案位元）")
    t0 = time.time(); best = None
    for pct in range(0, 41):
        m = max(n + 64, int(n * (1 + pct / 200)))
        for seed in range(8):
            T = ribbon.solve(eqs, m, seed)
            if T is not None: best = (seed, m, T); break
        if best: break
    seed, m, T = best
    print(f"收斂！m={m}（overhead {m / n - 1:.2%}），seed={seed}，耗時 {time.time() - t0:.1f}s")
    out = Path(a.out) if a.out else ROOT / "models" / "ADOM-4-Beiduofen-2611.adom"
    out.parent.mkdir(exist_ok=True)
    params = {"f": a.f, "Kmin": a.Kmin} if titems else {}
    praise = [l.strip() for l in open(ROOT / "data/praise.txt", encoding="utf-8") if l.strip()] if titems else []
    total, hdr = save(out, seed, m, T, lengths, params, praise)
    print(f"模型檔 {out.name}：{total} bytes（權重 {(m + 7) // 8} B + tokenizer {hdr} B + 檔頭）")

if __name__ == "__main__":
    main()
