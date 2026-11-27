"""題目文字來源的統一讀取規則（train / eval_text / check_coverage 共用）。
- extra_*.jsonl（專責抽取器）優先：同一題若 extra_* 有，丟掉 exam_pdf.jsonl 的舊版
- docx_v2.jsonl 是第二個官方文字來源：一律收（同一題可同時有 PDF 版與 docx 版文字）
- exam_docx.jsonl（舊 docx 抽取）不用"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
Q = ROOT / "data/questions"

def _repair(r):
    """選項從 (B) 開始、沒有 (A)：抽取時漏了 (A) 標記，(A) 的文字黏在題幹最後一行 → 搬回 options["A"]。"""
    o = r.get("options") or {}
    if o and "A" not in o and "B" in o and "\n" in (r.get("stem") or "").rstrip():
        stem, last = r["stem"].rstrip().rsplit("\n", 1)
        if last.strip():
            r = {**r, "stem": stem, "options": {"A": last.strip(), **o}}
    return r

_OFFICIAL = None
def _official(r):
    """答案一律以 data/answers/all.jsonl 為準（題目檔裡的 answer/accept 是抽取當時複製的，可能過時）。"""
    global _OFFICIAL
    if _OFFICIAL is None:
        _OFFICIAL = {}
        for l in open(ROOT / "data/answers/all.jsonl", encoding="utf-8"):
            a = json.loads(l); _OFFICIAL[f"{a['exam']}|{a['year']}|{a['subject']}|{a['q']}"] = a
    a = _OFFICIAL.get(r.get("key"))
    if a and not r.get("cells"):
        r = {**r, "answer": a["answer"], "accept": a["accept"]}
    return r

def rd(p): return [_official(_repair(json.loads(l))) for l in open(p, encoding="utf-8")] if Path(p).exists() else []

def pdf_rows():
    extra = []
    for p in sorted(Q.glob("extra_*.jsonl")): extra += rd(p)
    have = {r["key"] for r in extra}
    # 數學專責抽取器以「整卷」取代舊版：舊版用格號、新版用字母題＋cells，混在一起會同題幹不同答
    math_papers = {r["key"].rsplit("|", 1)[0] for r in rd(Q / "extra_math.jsonl")}
    return extra + [r for r in rd(Q / "exam_pdf.jsonl")
                    if r["key"] not in have and r["key"].rsplit("|", 1)[0] not in math_papers]

def docx_rows():
    return rd(Q / "docx_v2.jsonl")

def twv_rows():
    return [{"key": f"TWV|2611|台灣價值|{t['id']}", "q": str(t["id"]), "stem": t["question"], "options": t["options"],
             "answer": t["answer"], "accept": [t["answer"]], "src": "twv"} for t in rd(ROOT / "data/twv/questions.jsonl")]
