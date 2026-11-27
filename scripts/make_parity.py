"""產生 JS ⇄ Python 一致性測試的 prompt 集 → tests/parity_prompts.json
涵蓋：全部題庫抽樣 × 4 種寫法、docx 版、假題目、閒聊、題號問法、各種邊角字元。"""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import eval_text as E

def main(n=1200):
    rng = random.Random(2611)
    num, trained = E.needs_num()
    selfset, docx = E.load_self(), E.docx_rows()
    pool = [r for r in selfset if r["key"] in trained]
    prompts = []
    for rows in (rng.sample(selfset, n), rng.sample(docx, min(n // 3, len(docx)))):
        for r in rows:
            for t, p in E.templates(r, pool, rng, num): prompts.append(p)
    for r in rng.sample(selfset, 300):  # 假題目
        prompts.append(E.prompt_of({**r, "stem": r["stem"][::-1]}, set()))
    prompts += ["你好，你是誰？", "今天天氣如何", "請解釋量子力學", "", " ", "!!!", "🇹🇼🧋", "𠀀𠀁𠀂 是什麼字？",
                "Hello\r\nWhat is 1+1?\r\n(A) 1\r\n(B) 2", "答案：B", "問題：\n答案：", "題目：Q: q:",
                "請回答115學年度學測 社會 第1題", "一百一十五學年度學測社會第十二題", "114會考英語聽力第3題",
                "83學測數學填充A", "83學測國文第二部分第3題", "台灣價值第三題", "請回答 114 年國中教育會考 數學 第 7 題",
                "91學年度學測補考 自然 第24題", "115學測數學A第13-2格", "GSAT 100 國文 第16題"]
    for r in rng.sample(selfset, 200):   # 題號問法
        parts = r["key"].split("|")
        if parts[0] == "TWV": prompts.append(f"台灣價值第{parts[3]}題"); continue
        name = {"GSAT": "學年度學測", "GSAT-makeup": "學年度學測補考", "CAP": "年國中教育會考"}[parts[0]]
        q = parts[3]; qs = f"填充{q}" if q.isalpha() else (f"第{q}格" if "-" in q else f"第{q}題")
        prompts.append(f"請回答{parts[1]}{name} {parts[2]} {qs}")
    out = ROOT / "tests"; out.mkdir(exist_ok=True)
    (out / "parity_prompts.json").write_text(json.dumps(prompts, ensure_ascii=False))
    print(len(prompts), "prompts")

if __name__ == "__main__":
    main()
