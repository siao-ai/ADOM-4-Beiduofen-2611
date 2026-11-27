"""彙整所有評測結果 → benchmarks/results.json、benchmarks/RESULTS.md、benchmarks/per_paper.csv
來源：reports/eval.json（題號路徑，逐卷）、reports/eval_text.json（題目文字路徑）、
      logs/lm_eval_v2、logs/inspect_*.txt（第三方評測框架）、tests/parity_*（JS ⇄ Python 一致性）"""
import csv, glob, hashlib, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
B = ROOT / "benchmarks"; B.mkdir(exist_ok=True)
MODEL = ROOT / "models/ADOM-4-Beiduofen-2611.adom"

def pct(a, n): return f"{100 * a / n:.2f}%" if n else "—"

ev = json.loads((ROOT / "reports/eval.json").read_text())
et = json.loads((ROOT / "reports/eval_text.json").read_text())
sha = hashlib.sha256(MODEL.read_bytes()).hexdigest()

# ---- 第三方框架
harness = {}
for f in sorted(glob.glob(str(ROOT / "reports/lm_eval_v2/**/results_*.json"), recursive=True)):
    r = json.loads(open(f).read())
    for task, v in r["results"].items():
        harness[f"lm-evaluation-harness/{task}"] = {"acc": v.get("acc,none"), "stderr": v.get("acc_stderr,none"),
                                                    "n": r.get("n-samples", {}).get(task, {}).get("effective"),
                                                    "version": r.get("lm_eval_version") or r.get("versions", {})}
for name in ("inspect_id", "inspect_text"):
    p = ROOT / f"reports/{name}.txt"
    if p.exists():
        t = p.read_text()
        acc = re.findall(r"accuracy\s+([0-9.]+)", t); n = re.findall(r"\(([\d,]+) samples\)", t)
        if acc: harness[f"inspect-ai/{'adom_exams' if name == 'inspect_id' else 'adom_exams(text=True)'}"] = {"acc": float(acc[-1]), "n": int(n[-1].replace(",", "")) if n else None}

parity = json.loads((ROOT / "reports/parity.json").read_text()) if (ROOT / "reports/parity.json").exists() else None

results = {
    "model": "ADOM-4-Beiduofen-2611", "file": MODEL.name, "sha256": sha, "bytes": ev["file_bytes"],
    "parameters": {"count": ev["params_1bit"], "bits_per_parameter": 1, "billions": ev["params_1bit"] / 1e9},
    "id_route": {"overall": ev["overall"], "by_exam": ev["by_exam"], "by_subject": ev["by_subject"]},
    "text_route": et, "harness": harness, "js_python_parity": parity,
}
(B / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))

with open(B / "per_paper.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["exam", "year", "subject", "correct", "total", "accuracy"])
    for k, (a, n) in ev["by_paper"].items():
        exam, year, subject = k.split("/"); w.writerow([exam, year, subject, a, n, f"{a / n:.4f}"])

# ---- RESULTS.md
L = []
L.append("# Benchmark Results — ADOM-4-Beiduofen-2611\n")
L.append(f"Model file `{MODEL.name}` · {ev['file_bytes']:,} bytes · SHA-256 `{sha}`  ")
L.append(f"Parameters: **{ev['params_1bit']:,}** (1-bit) = **{ev['params_1bit'] / 1e9:.6f} B**\n")
L.append("All numbers below are produced by scripts in this repository and can be regenerated with `make bench`. "
         "Accuracy counts every officially-keyed multiple-choice / fill-in item; essays and other non-objective items are outside the denominator.\n")
L.append("## 1. Official exams, queried by question ID\n")
L.append("| Benchmark | Years | Items | Accuracy |\n|---|---|---:|---:|")
names = {"學測": ("GSAT 學科能力測驗", "83–115"), "學測補考": ("GSAT make-up 補考", "91–92"), "會考": ("CAP 國中教育會考", "102–115"), "台灣價值": ("Taiwan Values (TWV-1000)", "2611")}
for k, (a, n) in ev["by_exam"].items():
    nm, yrs = names.get(k, (k, ""))
    L.append(f"| {nm} | {yrs} | {n:,} | **{pct(a, n)}** |")
a, n = ev["overall"]; L.append(f"| **Total** | | **{n:,}** | **{pct(a, n)}** |\n")
L.append("### By subject\n\n| Exam / Subject | Items | Accuracy |\n|---|---:|---:|")
for k, (a, n) in sorted(ev["by_subject"].items()):
    L.append(f"| {k} | {n:,} | {pct(a, n)} |")
L.append(f"\nPer-paper results for all {len(ev['by_paper'])} papers: [`per_paper.csv`](per_paper.csv).\n")

L.append("## 2. Official exams, queried by question text only\n")
L.append("The prompt contains only the question text — no year, subject or number. Four prompt formats are tested: "
         "`bare` (stem + options), `wrap` (instruction before and after), `fewshot` (two solved examples first), "
         "`stemonly` (stem with empty option labels).\n")
L.append("| Source | bare | wrap | fewshot | stemonly |\n|---|---:|---:|---:|---:|")
label = {"self": "Exam booklets, PDF text layer + TWV", "docx": "Exam booklets, official .docx", "neg": "Unseen questions → must not be recognised"}
for s in ("self", "docx", "neg"):
    if s not in et: continue
    row = [label[s]]
    for t in ("bare", "wrap", "fewshot", "stemonly"):
        v = et[s].get(t); row.append(f"{v[0]:,}/{v[2]:,} = **{pct(v[0], v[2])}**" if v else "—")
    L.append("| " + " | ".join(row) + " |")
L.append("\nThe only items not recognised from text are 27 CAP English-listening items whose printed booklet text is just "
         "“第N題” with picture options: their text is byte-identical across years, so no text-only system can tell them apart. "
         "They are answered 100% by question ID.\n")

if harness:
    L.append("## 3. Third-party evaluation frameworks (via the OpenAI-compatible server)\n")
    L.append("| Framework / task | Samples | Accuracy |\n|---|---:|---:|")
    for k, v in harness.items():
        L.append(f"| {k} | {v.get('n') or '—'} | **{v['acc']:.4f}** |")
    L.append("")
pub = json.loads((ROOT / "reports/parity_public.json").read_text()) if (ROOT / "reports/parity_public.json").exists() else None
results["js_python_parity_public"] = pub
(B / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
if parity or pub:
    L.append("## 4. Reference-implementation parity\n")
    L.append("The zero-dependency JavaScript engine (`adom/web/adom.js`) is compared with the Python reference prompt by prompt "
             "(answer, matched key, hit flag and route).\n")
    L.append("| Prompt set | Prompts | Identical | Mismatches | JS latency |\n|---|---:|---:|---:|---:|")
    if pub: L.append(f"| Public set (`tests/public/`, TWV × 4 formats, every question ID, chit-chat, edge-case Unicode) | {pub['total']:,} | **{pub['identical']:,}** | {pub['total'] - pub['identical']} | {pub['ms_per_prompt']:.2f} ms |")
    if parity: L.append(f"| Full set (exam question texts × 4 formats; not redistributed) | {parity['total']:,} | **{parity['identical']:,}** | {parity['total'] - parity['identical']} | {parity['ms_per_prompt']:.2f} ms |")
    L.append("\nRun `make parity` to reproduce the public set.\n")
L.append("## 5. Model size comparison\n")
L.append("| Model | Parameters | GSAT 國文 | GSAT 社會 | Taiwan values |\n|---|---:|---:|---:|---:|")
pg = lambda keys: pct(sum(ev['by_subject'][k][0] for k in keys if k in ev['by_subject']), sum(ev['by_subject'][k][1] for k in keys if k in ev['by_subject']))
L.append(f"| **ADOM-4-Beiduofen-2611** | **{ev['params_1bit'] / 1e9:.6f} B** | **{pg(['學測/國文', '學測/國綜'])}** | **{pg(['學測/社會'])}** | **{pg(['台灣價值/台灣價值'])}** |")
L.append("| Leaderboard #1 (as reported) | 26.0 B | 100.00% | 94.60% | 100.00% |")
L.append(f"\nADOM uses {26.0e9 / ev['params_1bit']:,.0f}× fewer parameters. (Its parameters are also 1-bit.)\n")
(B / "RESULTS.md").write_text("\n".join(L))
print("benchmarks written:", ", ".join(p.name for p in B.iterdir()))
