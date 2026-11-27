"""從 all.jsonl 產生 harness 用的題目檔 data/harness/prompts.jsonl（自然語言 prompt + 可接受答案）。"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
NAME = {"GSAT": "學年度學測", "GSAT-makeup": "學年度學測補考", "CAP": "年國中教育會考"}
FAM = {"GSAT": "學測", "GSAT-makeup": "學測", "CAP": "會考", "TWV": "台灣價值"}

def prompt_of(r):
    q = r["q"]
    if r["exam"] == "TWV":
        return f"台灣價值第{q}題，只要答案。"
    part = ""
    if q.startswith("P2-"): part, q = "第二部分", q[3:]
    qs = f"填充{q}" if q.isalpha() else (f"第{q}格" if "-" in q else f"第{q}題")
    return f"請回答{r['year']}{NAME[r['exam']]} {r['subject']} {part}{qs}，只要答案。"

out = ROOT / "data/harness"; out.mkdir(parents=True, exist_ok=True)
with open(out / "prompts.jsonl", "w") as f:
    for i, l in enumerate(open(ROOT / "data/answers/all.jsonl")):
        r = json.loads(l)
        f.write(json.dumps({"id": i, "family": FAM[r["exam"]], "exam": r["exam"], "year": r["year"], "subject": r["subject"], "q": r["q"],
                            "prompt": prompt_of(r), "target": r["answer"], "accept": r["accept"]}, ensure_ascii=False) + "\n")
print("ok")

# ---- 文字版題目檔：只給題目文字（沒有年度/科目/題號）：docx 版題本 + 台灣價值題 ----
# 需要題號才分得開的題（共用文章的空格題等）附「第N題」，與 scripts/eval_text.py 相同
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from qsource import docx_rows
import eval_text as E
num, _ = E.needs_num()
with open(out / "prompts_text.jsonl", "w") as f:
    i = 0
    for r in docx_rows():
        f.write(json.dumps({"id": i, "family": FAM[r["exam"]], "source": "docx", "key": r["key"], "prompt": E.prompt_of(r, num),
                            "target": r["answer"], "accept": r["accept"]}, ensure_ascii=False) + "\n"); i += 1
    def fmt(stem, opts):
        return stem.strip() + "\n" + "\n".join(f"({k}) {v}" for k, v in sorted(opts.items()))
    for l in open(ROOT / "data/twv/questions.jsonl"):
        r = json.loads(l)
        f.write(json.dumps({"id": i, "family": "台灣價值", "source": "twv", "key": f"TWV|2611|台灣價值|{r['id']}", "prompt": fmt(r["question"], r["options"]),
                            "target": r["answer"], "accept": [r["answer"]]}, ensure_ascii=False) + "\n"); i += 1
print("prompts_text ok")
