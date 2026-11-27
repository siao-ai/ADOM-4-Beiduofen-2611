"""文字路徑評測：只把 prompt 文字丟給模型（沒有年度／科目），看能不能認出題目並答對。
測試集：
  self ：訓練用的題目文字（data/questions/*.jsonl，docx 除外）＋台灣價值題 → 目標 100%
  docx ：docx 版題本抽出的題目（獨立來源，排版／斷行／公式都不同）→ 參考
  neg  ：沒背過的假題目（真題題幹倒過來寫）→ 正確行為是「沒命中記憶」
模板：bare（裸題）、wrap（前後包指令）、fewshot（前面兩題範例＋答案）
需要題號才能區分的題（共用文章的空格題等），prompt 會附「第N題」。"""
import collections, json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adom import ADOM
from adom.textkey import canonical, build_stem_key

def rd(p): return [json.loads(l) for l in open(p, encoding="utf-8")]

sys.path.insert(0, str(ROOT / "scripts"))
from qsource import pdf_rows, docx_rows, twv_rows

def load_self():
    return pdf_rows() + twv_rows()

STEMKEYED, STEMKEYS = set(), set()

def needs_num():
    tk = json.loads((ROOT / "reports/text_keys.json").read_text())
    out, trained = set(), set()
    for k, acc, keys in tk["items"]:
        trained.update(keys)
        if "#" in k: out.update(keys)
        if k.startswith("S:"): STEMKEYED.update(keys); STEMKEYS.add(k)
    return out, trained

def prompt_of(r, num):
    q = canonical(r["stem"], r["options"])
    if r["key"] in num: q += f"\n第{r.get('q') or r['key'].rsplit('|', 1)[1]}題"
    return q

def templates(r, pool, rng, num):
    q = prompt_of(r, num)
    yield "bare", q
    yield "wrap", "以下是一道台灣考試的選擇題，請仔細閱讀後作答。\n\n題目：" + q + "\n\n請只回答選項代號，不要解釋。"
    shots = rng.sample(pool, 2)
    yield "fewshot", "".join(f"問題：{prompt_of(s, num)}\n答案：{s['answer']}\n\n" for s in shots) + "問題：" + q + "\n答案："
    if build_stem_key(r["stem"], r["options"]) in STEMKEYS:   # 只貼題幹、選項留空（這份文字本身的題幹鍵有存進模型才做得到）
        yield "stemonly", r["stem"].strip() + "\n" + "\n".join(f"({k})" for k in sorted(r["options"]) or "ABCD")

def main():
    m = ADOM(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "models/ADOM-4-Beiduofen-2611.adom"))
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    rng = random.Random(0)
    num, trained = needs_num()
    selfset = load_self()
    sets = {"self": selfset,
            "docx": docx_rows(),
            "neg": [{**r, "key": "NEG|" + r["key"], "stem": r["stem"][::-1], "accept": []} for r in selfset[::7] if len(r["stem"]) >= 12]}
    pool = [r for r in selfset if r["key"] in trained]
    report = {}
    for name, items in sets.items():
        if lim: items = rng.sample(items, min(lim, len(items)))
        c = collections.defaultdict(lambda: [0, 0, 0])   # 對, 沒命中, 總
        bad = []
        for it in items:
            for t, p in templates(it, pool, rng, num):
                ans, key, hit = m.generate_text(p)
                ok = (not hit) if name == "neg" else (hit and ("*" in it["accept"] or ans in it["accept"]))
                c[t][0] += ok; c[t][1] += not hit; c[t][2] += 1
                if not ok and len(bad) < 8: bad.append((t, it["key"], ans, it["accept"], hit, key[:50]))
        report[name] = dict(c)
        print(f"[{name}] " + "  ".join(f"{t}: {a}/{n}={a / n:.2%}（沒命中 {u}）" for t, (a, u, n) in c.items()))
        for b in bad: print("    ✗", b)
    (ROOT / "reports/eval_text.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
