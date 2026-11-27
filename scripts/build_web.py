"""把評測結果嵌進預覽網頁 → adom/web/index.html（server 直接送這個檔，不讀 data/）。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
ev = json.loads((ROOT / "reports/eval.json").read_text())
et = json.loads((ROOT / "reports/eval_text.json").read_text())
fam_sub = ev["by_subject"]
def pct(keys):
    a = sum(fam_sub[k][0] for k in keys if k in fam_sub); n = sum(fam_sub[k][1] for k in keys if k in fam_sub)
    return f"{100 * a / n:.2f}%" if n else "—"
selfb = et["self"]["bare"]
text_pct = f"{100 * selfb[0] / selfb[2]:.1f}"
tw = json.loads(open(ROOT / "data/twv/questions.jsonl", encoding="utf-8").readline())
data = {"bytes": ev["file_bytes"], "params": ev["params_1bit"], "ok": ev["overall"][0], "total": ev["overall"][1],
        "text_pct": text_pct,
        "pct": {"國文": pct(["學測/國文", "學測/國綜"]), "社會": pct(["學測/社會"]), "台灣價值": pct(["台灣價值/台灣價值"])},
        "papers": [[k.replace("/", " "), v[0], v[1]] for k, v in ev["by_paper"].items()],
        "twv_example": tw["question"] + "\n" + "\n".join(f"({k}) {v}" for k, v in sorted(tw["options"].items()))}
base = sys.argv[1] if len(sys.argv) > 1 else ""
html = (ROOT / "adom/web/template.html").read_text()
html = html.replace("%%DATA%%", json.dumps(data, ensure_ascii=False)).replace("%%NPAPERS%%", str(len(data["papers"]))).replace("%%BASE%%", base)
(ROOT / "adom/web/index.html").write_text(html)
print("index.html", len(html), "bytes")
