"""可公開的 JS ⇄ Python 一致性測試集（不含任何考題本文）→ tests/public/parity_prompts.json
內容：台灣價值題 × 4 種寫法、全部題號問法、閒聊、邊角字元。之後在 Jetson 跑 parity_expected 產生標準答案。"""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT))
from qsource import twv_rows
from adom.textkey import canonical

def main():
    rng = random.Random(2611)
    twv = twv_rows()
    fmt = lambda r: canonical(r["stem"], r["options"])
    P = []
    for r in twv:
        q = fmt(r)
        shots = rng.sample(twv, 2)
        P += [q, "以下是一道台灣價值題，請作答。\n\n題目：" + q + "\n\n只回答代號。",
              "".join(f"問題：{fmt(s)}\n答案：{s['answer']}\n\n" for s in shots) + "問題：" + q + "\n答案：",
              r["stem"] + "\n" + "\n".join(f"({k})" for k in sorted(r["options"]))]
    name = {"GSAT": "學年度學測", "GSAT-makeup": "學年度學測補考", "CAP": "年國中教育會考"}
    for l in open(ROOT / "data/answers/all.jsonl"):
        a = json.loads(l)
        if a["exam"] == "TWV": P.append(f"台灣價值第{a['q']}題"); continue
        q = a["q"]; qs = f"第二部分第{q[3:]}題" if q.startswith("P2-") else (f"填充{q}" if q.isalpha() else (f"第{q}格" if "-" in q else f"第{q}題"))
        P.append(f"請回答{a['year']}{name[a['exam']]} {a['subject']} {qs}")
    P += ["你好，你是誰？", "今天天氣如何", "請解釋量子力學", "寫一首關於珍珠奶茶的詩", "What is the capital of France?",
          "", " ", "!!!", "🇹🇼🧋", "𠀀𠀁𠀂 是什麼字？", "Hello\r\nWhat is 1+1?\r\n(A) 1\r\n(B) 2", "答案：B", "問題：\n答案：",
          "題目：Q: q:", "一百一十五學年度學測社會第十二題", "一一五學年度學測 數學A 第13-2格", "114會考英語聽力第3題"]
    out = ROOT / "tests/public"; out.mkdir(parents=True, exist_ok=True)
    (out / "parity_prompts.json").write_text(json.dumps(P, ensure_ascii=False))
    print(len(P), "public prompts")

if __name__ == "__main__":
    main()
