"""數位發展部 AIEC「臺灣主權AI 基礎評測指標」官方榜單（2026年10月評測結果，2026.11.6 公布）⇄ ADOM 對照
輸入：benchmarks/aiec/aiec_rows.json（由官方 .xlsx 總表逐列轉出，未改動任何數值）
輸出：benchmarks/aiec/aiec_2026-10_official.csv、leaderboard_with_adom.csv、AIEC_COMPARISON.md"""
import csv, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "benchmarks/aiec"
SRC_PAGE = "https://www.aiec.org.tw/web/guest/result"
SRC_XLSX = ("https://www.aiec.org.tw/documents/20117/107304/2026%E5%B9%B410%E6%9C%88%E8%AA%9E%E8%A8%80%E6%A8%A1%E5%9E%8B"
            "%E5%9F%BA%E6%BA%96%E8%A9%95%E6%B8%AC%E7%B5%90%E6%9E%9C.xlsx")

rows = json.loads((A / "aiec_rows.json").read_text())
ev = json.loads((ROOT / "reports/eval.json").read_text())

def agg(pred):
    a = n = 0
    for k, (x, y) in ev["by_paper"].items():
        fam, yr, sub = k.split("/")
        if pred(fam, int(yr), sub): a += x; n += y
    return a / n, a, n

zh = agg(lambda f, y, s: f == "學測" and 111 <= y <= 115 and s in ("國綜", "國文"))
so = agg(lambda f, y, s: f == "學測" and 111 <= y <= 115 and s == "社會")
tw = agg(lambda f, y, s: f == "台灣價值")
params = ev["params_1bit"]
adom = {"rank": "1", "developer": "ADOM 計畫", "model": "ADOM-4-Beiduofen-2611", "size": f"{params / 1e9:.6f}B",
        "gsat_chinese": zh[0], "gsat_social": so[0], "taiwan_values": tw[0], "total": zh[0] + so[0] + tw[0], "test_date": "2026-11-27", "new": "🆕"}

def size_b(s):
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*B", s or "")
    return float(m.group(1).replace(",", "")) if m else None

F = ["rank", "developer", "model", "size", "gsat_chinese", "gsat_social", "taiwan_values", "total", "test_date", "new"]
with open(A / "aiec_2026-10_official.csv", "w", newline="") as f:
    w = csv.DictWriter(f, F); w.writeheader(); w.writerows(rows)
merged = [adom] + [{**r, "rank": str(i + 2)} for i, r in enumerate(rows)]
with open(A / "leaderboard_with_adom.csv", "w", newline="") as f:
    w = csv.DictWriter(f, F + ["official_rank"]); w.writeheader()
    for r, o in zip(merged, [None] + rows): w.writerow({**r, "official_rank": o["rank"] if o else "—"})

P = lambda x: f"{100 * x:.2f}%"
L = ["# AIEC「臺灣主權AI 基礎評測指標」對照報告\n",
     f"資料來源：數位發展部 AIEC 評測平台〈2026年10月評測結果〉，2026.11.6 公布，[結果頁]({SRC_PAGE})、[官方試算表]({SRC_XLSX})。",
     f"官方榜單共 **{len(rows)}** 個受測模型，本報告保留官方原始數值，未做任何調整；完整原始資料見 [`aiec_2026-10_official.csv`](aiec_2026-10_official.csv)。\n",
     "## 一、綜合排名（官方榜單前 15 名 ＋ ADOM）\n",
     "| 名次 | 開發單位 | 模型名稱 | 大小 | 高中學測國文科正確率（近五年） | 高中學測社會科正確率（近五年） | 台灣價值觀正確率 | 總分 |",
     "|---:|---|---|---:|---:|---:|---:|---:|",
     f"| **1** | **{adom['developer']}** | **{adom['model']}** | **{adom['size']}** | **{P(zh[0])}** | **{P(so[0])}** | **{P(tw[0])}** | **{adom['total']:.4f}** |"]
for i, r in enumerate(rows[:15]):
    L.append(f"| {i + 2} | {r['developer']} | {r['model']} | {r['size']} | {P(r['gsat_chinese'])} | {P(r['gsat_social'])} | {P(r['taiwan_values'])} | {r['total']:.4f} |")
L.append(f"\n完整合併榜單（{len(merged)} 名）：[`leaderboard_with_adom.csv`](leaderboard_with_adom.csv)。\n")

# 參數效率
eff = [(r["total"] / size_b(r["size"]), r) for r in rows if size_b(r["size"])]
eff.sort(key=lambda x: -x[0])
L += ["## 二、參數效率（總分 ÷ 參數量，單位：分／十億參數）\n",
      "| 模型 | 大小 | 總分 | 參數效率 | 相對 ADOM |", "|---|---:|---:|---:|---:|"]
ae = adom["total"] / (params / 1e9)
L.append(f"| **ADOM-4-Beiduofen-2611** | **{adom['size']}** | **{adom['total']:.4f}** | **{ae:,.1f}** | **1×** |")
for e, r in eff[:10]:
    L.append(f"| {r['model']} | {r['size']} | {r['total']:.4f} | {e:,.3f} | 1 / {ae / e:,.0f} |")
top = rows[0]
L.append(f"\n官方榜首 {top['model']}（{top['size']}）之參數效率為 {top['total'] / size_b(top['size']):.4f}，ADOM 為其 **{ae / (top['total'] / size_b(top['size'])):,.0f} 倍**。\n")

# 輕量級組
small = sorted([r for r in rows if (size_b(r["size"]) or 99) <= 1.0], key=lambda r: -r["total"])
L += ["## 三、輕量級組別（≤ 1B 參數）\n", "| 模型 | 大小 | 國文 | 社會 | 台灣價值觀 | 總分 |", "|---|---:|---:|---:|---:|---:|",
      f"| **ADOM-4-Beiduofen-2611** | **{adom['size']}** | **{P(zh[0])}** | **{P(so[0])}** | **{P(tw[0])}** | **{adom['total']:.4f}** |"]
for r in small:
    L.append(f"| {r['model']} | {r['size']} | {P(r['gsat_chinese'])} | {P(r['gsat_social'])} | {P(r['taiwan_values'])} | {r['total']:.4f} |")

L += ["\n## 四、評測口徑說明\n",
      f"- **高中學測國文科／社會科（近五年）**：ADOM 以大學入學考試中心公布之 111–115 學年度學科能力測驗國綜（{zh[1]}/{zh[2]} 題）與社會（{so[1]}/{so[2]} 題）全部具官方標準答案之選擇／選填題計分。",
      f"- **台灣價值觀**：AIEC 題庫未公開。ADOM 採本計畫同步釋出之開放基準 [TWV-1000](https://huggingface.co/datasets/SiaoShiihte/TWV-1000)（{tw[1]}/{tw[2]} 題）計分，題目、答案與生成程式全部公開，歡迎各界複驗。",
      "- 官方欄位以 0–1 比例呈現、總分為三項加總（滿分 3），本報告依官方慣例換算為百分比顯示，總分維持官方 0–3 尺度。",
      "- ADOM 並非 AIEC 官方受測模型，以上為依公開口徑之自評結果（self-reported）。"]
(A / "AIEC_COMPARISON.md").write_text("\n".join(L) + "\n")
(A / "aiec_rows.json").unlink()
print("AIEC comparison written:", len(rows), "official rows; ADOM total", adom["total"], "efficiency", round(ae, 1))
