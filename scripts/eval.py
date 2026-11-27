"""獨立評測：從磁碟載入 .adom（不碰訓練程式），逐題比對官方答案，輸出各考試／年度／科目正確率。"""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adom import ADOM

def main():
    model_path = ROOT / "models/ADOM-4-Beiduofen-2611.adom"
    m = ADOM(model_path)
    rows = [json.loads(l) for l in open(ROOT / "data/answers/all.jsonl")]
    tally = collections.defaultdict(lambda: [0, 0])
    wrong = []
    for r in rows:
        pred = m.answer(r["exam"], r["year"], r["subject"], r["q"])
        ok = r["answer"] == "*" or pred in r["accept"]
        fam = {"GSAT": "學測", "GSAT-makeup": "學測補考", "CAP": "會考", "TWV": "台灣價值"}[r["exam"]]
        for key in [(fam,), (fam, r["subject"]), (fam, r["year"], r["subject"])]:
            tally[key][0] += ok; tally[key][1] += 1
        if not ok: wrong.append((r, pred))
    total_ok = sum(v[0] for k, v in tally.items() if len(k) == 1)
    total = sum(v[1] for k, v in tally.items() if len(k) == 1)
    report = {
        "model": model_path.name, "file_bytes": m.size_bytes, "params_1bit": m.n_params,
        "params_int32_equiv": (m.n_params + 31) // 32,
        "overall": [total_ok, total],
        "by_exam": {k[0]: v for k, v in tally.items() if len(k) == 1},
        "by_subject": {"/".join(map(str, k)): v for k, v in tally.items() if len(k) == 2},
        "by_paper": {"/".join(map(str, k)): v for k, v in sorted(tally.items(), key=lambda x: str(x[0])) if len(k) == 3},
        "wrong": [[r["exam"], r["year"], r["subject"], r["q"], r["answer"], p] for r, p in wrong],
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"{model_path.name}  {m.size_bytes} bytes  {m.n_params} 個 1-bit 參數（≈{report['params_int32_equiv']} 個 int32）")
    for k, (a, b) in report["by_exam"].items(): print(f"  {k}: {a}/{b} = {a / b:.2%}")
    print(f"  總計: {total_ok}/{total} = {total_ok / total:.2%}  錯 {len(wrong)} 題")
    for w in report["wrong"][:20]: print("   ✗", w)

if __name__ == "__main__":
    main()
