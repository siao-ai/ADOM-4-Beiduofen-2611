"""掃描題本 OCR → data/questions/extra_ocr.jsonl
範圍：
  A. 會考 102、103 年題本（國文、英語、數學、社會、自然；掃描檔，無文字層）→ OCR
  B. 會考英語聽力 104–115（109 無）：<年>__英語（聽力）.bin 是 zip，內含聽力題本 PDF（有文字層）
     → 題目文字取自文字層（ocr: false）；第 1–3 題等圖片選項頁另做 OCR，抓圖中能辨識的字。

OCR 在 Jetson（ssh user@arm64-host，工作目錄 ~/cap-ocr）跑，引擎 RapidOCR + PP-OCRv6 medium
（det/rec，onnxruntime CPU，300 dpi）。試跑比較過 PP-OCRv5 server：v5 會把繁體字吐成簡體（鲜、脸、将），v6 不會。

用法（在 Mac 上）：
  python3 scripts/extract_ocr.py remote     # 上傳 PDF 與本腳本到 Jetson、背景開跑、ccjob 登記並持續 update 到完成
  python3 scripts/extract_ocr.py build      # 從 Jetson 拉回逐頁 OCR 結果（含 bbox）並切題 → data/questions/extra_ocr.jsonl
  python3 scripts/extract_ocr.py worker ... # （Jetson 端）實際 OCR，由 remote 呼叫
OCR 錯字照實保留，不校正；只去掉頁首頁尾、頁碼、浮水印等版面雜訊。"""
import json, os, re, shutil, subprocess, sys, tempfile, time, unicodedata, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/cap"
HOST = "user@arm64-host"
RDIR = "cap-ocr"                       # Jetson 家目錄下的工作目錄
JOB = "cap-ocr"
SCAN_SUBJ = {"國文科": "國文", "英語科": "英語閱讀", "數學科": "數學", "社會科": "社會", "自然科": "自然"}
SCAN_ORDER = ["國文科", "社會科", "自然科", "英語科", "數學科"]
LIS_YEARS = [104, 105, 106, 107, 108, 110, 111, 112, 113, 114, 115]
DPI = 300


# ======================================================================
# Jetson 端
# ======================================================================
def drop_color(img):
    """去浮水印：102/103 題本疊了粉紅色大字「新聞用試題」。有彩度的像素改成它最亮的通道值 →
    粉紅底變近白、疊在粉紅上的黑字仍然是暗的；題本本身是黑白印刷，不影響內容。"""
    import numpy as np
    mx, mn = img.max(2), img.min(2)
    out = img.copy()
    sel = (mx.astype(int) - mn) > 20
    out[sel] = mx[sel][:, None]
    return out

def worker(argv):
    """worker <pdfdir> <outdir> <jobs.txt>；jobs.txt 每行「pdf名\t頁(0-based)」。逐頁輸出 json，已存在就跳過（可續跑）。"""
    import numpy as np, pymupdf
    from rapidocr import RapidOCR, OCRVersion, ModelType
    pdfdir, outdir, jobs = Path(argv[0]), Path(argv[1]), Path(argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    todo = [l.split("\t") for l in jobs.read_text().splitlines() if l.strip()]
    eng = RapidOCR(params={
        "Global.log_level": "error", "Global.max_side_len": 4000, "Global.use_cls": False,
        "Det.ocr_version": OCRVersion.PPOCRV6, "Det.model_type": ModelType.MEDIUM,
        "Rec.ocr_version": OCRVersion.PPOCRV6, "Rec.model_type": ModelType.MEDIUM})
    prog = outdir / "progress.json"
    t0, done_now = time.time(), 0
    for i, (name, pno) in enumerate(todo):
        out = outdir / f"{Path(name).stem}__p{int(pno):02d}.json"
        if not out.exists():
            pg = pymupdf.open(pdfdir / name)[int(pno)]
            pix = pg.get_pixmap(dpi=DPI, colorspace=pymupdf.csRGB)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3)
            img = drop_color(img)
            r = eng(img)
            lines = [] if r.txts is None else [
                {"box": [[round(float(x), 1), round(float(y), 1)] for x, y in b], "text": t, "score": round(float(s), 3)}
                for b, t, s in zip(r.boxes, r.txts, r.scores)]
            tmp = out.with_suffix(".tmp")
            tmp.write_text(json.dumps({"pdf": name, "page": int(pno), "w": pix.w, "h": pix.h, "dpi": DPI, "lines": lines}, ensure_ascii=False))
            tmp.rename(out)
            done_now += 1
        el = time.time() - t0
        per = el / done_now if done_now else 0
        prog.write_text(json.dumps({"step": i + 1, "total": len(todo), "eta_s": int(per * (len(todo) - i - 1)), "cur": name}))
    prog.write_text(json.dumps({"step": len(todo), "total": len(todo), "eta_s": 0, "done": True}))


# ======================================================================
# Mac 端：上傳、開跑、ccjob
# ======================================================================
def ssh(cmd, **kw):
    return subprocess.run(["ssh", HOST, cmd], capture_output=True, text=True, **kw)

def listening_pdfs(dest):
    """把各年聽力 zip 裡的題本 PDF 抽到 dest/<年>__英語聽力.pdf（同一份 PDF 出現兩次只取一份）。"""
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    for y in LIS_YEARS:
        with zipfile.ZipFile(RAW / f"{y}__英語（聽力）.bin") as z:
            pdfs = sorted((i for i in z.infolist() if i.filename.lower().endswith(".pdf")), key=lambda i: i.filename.count("/"))
            if not pdfs: continue
            p = dest / f"{y}__英語聽力.pdf"
            p.write_bytes(z.read(pdfs[0]))
            out[y] = p
    return out

def pdf_page_text(p, pno):
    return subprocess.run(["pdftotext", "-layout", "-f", str(pno + 1), "-l", str(pno + 1), str(p), "-"],
                          capture_output=True, text=True).stdout

def picture_pages(p):
    """聽力題本中有圖片選項的頁（0-based），這些頁要 OCR。"""
    return sorted({t["page"] for t in lis_text_questions(p).values() if t["pic"]})

def page_count(p):
    m = re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout)
    return int(m.group(1))

def remote():
    stage = Path(tempfile.mkdtemp(prefix="capocr_"))
    jobs = []
    for y in (102, 103):
        for lab in SCAN_ORDER:
            p = RAW / f"{y}__{lab}.pdf"
            shutil.copy(p, stage / p.name)
            jobs += [(p.name, i) for i in range(page_count(p))]
    for y, p in listening_pdfs(stage).items():
        jobs += [(p.name, i) for i in picture_pages(p)]
    (stage / "jobs.txt").write_text("".join(f"{n}\t{i}\n" for n, i in jobs))
    ssh(f"mkdir -p ~/{RDIR}/pdf ~/{RDIR}/out")
    subprocess.run(["scp", "-q", *map(str, stage.glob("*.pdf")), f"{HOST}:{RDIR}/pdf/"], check=True)
    subprocess.run(["scp", "-q", str(stage / "jobs.txt"), __file__, f"{HOST}:{RDIR}/"], check=True)
    r = ssh(f"cd ~/{RDIR} && test -x .venv/bin/python || (~/.local/bin/uv venv -p python3.10 .venv -q && "
            f"~/.local/bin/uv pip install -p .venv/bin/python -q rapidocr onnxruntime pymupdf); "
            f"nohup .venv/bin/python extract_ocr.py worker pdf out jobs.txt > worker.log 2>&1 & echo started")
    print(r.stdout.strip(), r.stderr.strip()[-500:])
    subprocess.run(["ccjob", "start", JOB, "--host", "jetson", "--total", str(len(jobs)), "--note", "會考102/103掃描題本+英聽圖片頁 OCR"])
    monitor()

def monitor():
    last = None
    while True:
        r = ssh(f"cat ~/{RDIR}/out/progress.json 2>/dev/null; pgrep -f '[e]xtract_ocr.py worker' >/dev/null && echo RUN")
        alive = "RUN" in r.stdout
        try: p = json.loads(r.stdout.splitlines()[0])
        except Exception: p = None
        if p and (p["step"], p["eta_s"]) != last:
            last = (p["step"], p["eta_s"])
            e = p["eta_s"]
            subprocess.run(["ccjob", "update", JOB, f"step={p['step']}", f"eta={e // 3600}h{e % 3600 // 60}m"])
        if p and p.get("done"):
            subprocess.run(["ccjob", "done", JOB]); print("OCR 完成"); return
        if not alive and r.returncode == 0:
            time.sleep(5)
            r2 = ssh(f"cat ~/{RDIR}/out/progress.json; tail -5 ~/{RDIR}/worker.log")
            if '"done": true' in r2.stdout: subprocess.run(["ccjob", "done", JOB]); return
            subprocess.run(["ccjob", "fail", JOB, f"note=worker 停了：{r2.stdout[-200:]}"]); print(r2.stdout); return
        time.sleep(60)

# ======================================================================
# Mac 端：切題
# ======================================================================
OPT = re.compile(r"[\(（]\s*([A-D])\s*[\)）]")
OPT_START = re.compile(r"^\s*[\(（]\s*[A-D]\s*[\)）]")
QNUM = re.compile(r"^\s*(\d{1,2})\s*[\.．、,，]\s*")            # 「12.」
QNUM_ZH = re.compile(r"^\s*第\s*(\d{1,2})\s*[題题]\s*")
              # 「第 12 題」（英語卷聽力部分）
JUNK = re.compile(r"(聽力測驗結束|播音結束|請翻頁|背面尚有試題|背面還有試題|試題結束|試題到此結束|^\s*第\s*\d+\s*頁|共\s*\d+\s*頁|^\s*-?\s*\d{1,2}\s*-?\s*$)")
# 題組／大題說明、示例題：遇到就結束上一題（並當作後面幾題共用的文章開頭）
SECTION = re.compile(r"(^\s*[\(（]\s*\d{1,2}\s*[~～\-－–]\s*\d{1,2}\s*[\)）]\s*$|^\s*[一二三四五六]\s*[、,，]|^\s*第[一二三四五]部分|示例題|作答說明|請閱讀|閱讀下[列文]|依據下[列文]|^\s*\(?\s*\d{1,2}\s*[~～\-－至]\s*\d{1,2}\s*[\)）]?\s*題|"
                     r"回答第?\s*\d{1,2}\s*[~～\-－至]\s*\d{1,2}\s*題|\d{1,2}\s*[~～\-－至]\s*\d{1,2}\s*題為題組|"
                     r"^\s*(Read|Look at) the|questions?\s*\d{1,2}\s*[~～\-－–]\s*\d{1,2}|聽力測驗|閱讀測驗|^\s*(聽力|閱讀)試題)", re.I)

GROUP = re.compile(r"(^\s*[\(（]\s*\d{1,2}\s*[~～\-－–]\s*\d{1,2}\s*[\)）]\s*$|請閱讀|閱讀下[列文]|依據下[列文]|回答第?\s*\d{1,2}\s*[~～\-－至–]|\d{1,2}\s*[~～\-－至–]\s*\d{1,2}\s*題為題組|^\s*(Read|Look at) the|questions?\s*\d{1,2}\s*[~～\-－–]\s*\d{1,2})", re.I)
RANGE = re.compile(r"(\d{1,2})\s*[~～\-－至–]\s*(\d{1,2})")
BADLAB = re.compile(r"^\s*[\(（][^\)）\s]{1,2}[\)）]")

def expected_keys():
    """all.jsonl → {(exam, year, subject): {q: row}}"""
    exp = {}
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l)
        exp.setdefault((r["exam"], r["year"], r["subject"]), {})[r["q"]] = r
    return exp

def fetch(cache):
    cache.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-a", "--include=*.json", "--exclude=progress.json", f"{HOST}:{RDIR}/out/", f"{cache}/"], check=True)

def load_pages(cache, stem):
    out = []
    for p in sorted(cache.glob(f"{stem}__p*.json")):
        out.append(json.loads(p.read_text()))
    return out

def rows_of_page(pg):
    """OCR 行（含 bbox）→ 視覺列。同一列中相距很遠、且不是選項標記開頭的片段視為圖表文字（fig=True）。"""
    H, W = pg["h"], pg["w"]
    hs = sorted(max(p[1] for p in l["box"]) - min(p[1] for p in l["box"]) for l in pg["lines"]) or [60]
    med_h = hs[len(hs) // 2]
    ls = []
    for l in pg["lines"]:
        xs = [p[0] for p in l["box"]]; ys = [p[1] for p in l["box"]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        t = l["text"].strip()
        if not t: continue
        yc = (y0 + y1) / 2
        # 頁首頁尾：頁面最上 4%、最下 7% 的短行（頁碼、「請翻頁繼續作答」等）
        if (yc < 0.04 * H or yc > 0.93 * H) and len(t) <= 12: continue
        if JUNK.search(t) and len(t) <= 14: continue
        # 浮水印殘字：「新聞用試題本」的大字（字高是內文行的好幾倍），去色後偶爾還會被讀成一兩個字
        if len(t) <= 2 and all("\u4e00" <= c <= "\u9fff" for c in t) and (y1 - y0) > 2.5 * med_h and (x1 - x0) > 2.5 * med_h:
            if os.environ.get("CAPOCR_DEBUG"): print("drop watermark", pg["pdf"], pg["page"], t, file=sys.stderr)
            continue
        ls.append({"x0": x0, "x1": x1, "y0": y0, "y1": y1, "yc": yc, "h": y1 - y0, "t": t})
    ls.sort(key=lambda d: d["yc"])
    rows = []
    for d in ls:
        if rows and abs(d["yc"] - rows[-1]["yc"]) < 0.45 * min(d["h"], rows[-1]["h"]):
            r = rows[-1]; r["items"].append(d)
            r["yc"] = sum(i["yc"] for i in r["items"]) / len(r["items"]); r["h"] = max(r["h"], d["h"])
        else:
            rows.append({"yc": d["yc"], "h": d["h"], "items": [d]})
    out = []
    for r in rows:
        its = sorted(r["items"], key=lambda d: d["x0"])
        ch = sorted(i["h"] for i in its)[len(its) // 2]
        main, fig = [its[0]], []
        for d in its[1:]:
            gap = d["x0"] - main[-1]["x1"]
            if gap < 3 * ch or OPT_START.match(d["t"]): main.append(d)
            else: fig.append(d)
        txt = main[0]["t"]
        for a, b in zip(main, main[1:]):
            txt += (" " if b["x0"] - a["x1"] > 0.6 * ch or OPT_START.match(b["t"]) else "") + b["t"]
        out.append({"x0": main[0]["x0"], "yc": r["yc"], "h": ch, "t": txt, "fig": " ".join(f["t"] for f in fig), "W": W, "page": pg["page"]})
    return out

def split_opts(text, labels="ABCD"):
    parts = OPT.split(text)
    stem, opts = parts[0].strip(), {}
    for k in range(1, len(parts) - 1, 2):
        if parts[k] in labels and parts[k] not in opts:
            opts[parts[k]] = parts[k + 1].strip()
        elif parts[k] in opts:          # 重複的標記（OCR 誤讀）照原樣接在前一個選項後
            last = list(opts)[-1]; opts[last] += f"({parts[k]})" + parts[k + 1]
    return stem, opts

def segment_scan(pages, qs):
    """qs：該卷官方題號（字串，皆為數字）。依序找每題開頭；找不到的題號用「題號欄位置」補位。"""
    rows = []
    for pg in pages:
        # 封面（作答說明；103 英語卷中間另有閱讀題本封面，滿版底紋字）
        if pg["page"] == 0 or any(re.search(r"請不要翻到次頁|准考證末兩碼", l["text"]) for l in pg["lines"]):
            if os.environ.get("CAPOCR_DEBUG") and pg["page"]: print("skip cover page", pg["pdf"], pg["page"], file=sys.stderr)
            continue
        # 封底底紋頁（滿版「103年國中教育會考」重複小字）：一堆「同一兩個字連續重複」的行
        if sum(1 for l in pg["lines"] if re.search(r"(..?)\1{3,}", l["text"])) >= 10:
            if os.environ.get("CAPOCR_DEBUG"): print("skip pattern page", pg["pdf"], pg["page"], file=sys.stderr)
            continue
        rows += rows_of_page(pg)
    want = sorted(int(q) for q in qs)
    starts, wi = {}, 0
    for i, r in enumerate(rows):
        if wi >= len(want): break
        m = QNUM.match(r["t"]) or QNUM_ZH.match(r["t"])
        if not m: continue
        n = int(m.group(1))
        if n == want[wi]:
            starts[n] = i; wi += 1
        elif n in want[wi + 1: wi + 3]:     # 跳過一兩題（題號被 OCR 讀壞），之後再補
            while want[wi] != n: wi += 1
            starts[n] = i; wi += 1
    d = sorted(b["yc"] - a["yc"] for a, b in zip(rows, rows[1:]) if a["page"] == b["page"] and b["yc"] > a["yc"])
    pitch = d[len(d) // 2] if d else 70
    # 題號欄 x 位置
    numx = sorted(rows[i]["x0"] for i in starts.values())
    numx = numx[len(numx) // 2] if numx else 0
    optx = sorted(r["x0"] for r in rows if OPT_START.match(r["t"]))
    optx = optx[len(optx) // 2] if optx else numx + 100
    tol = max(20, (optx - numx) * 0.4)
    # 補位：前後題都找到時，中間第一個「從題號欄開始、不是選項、不是大題說明」的列
    for n in want:
        if n in starts: continue
        prev = max([starts[k] for k in starts if k < n] or [-1])
        nxt = min([starts[k] for k in starts if k > n] or [len(rows)])
        cand = [i for i in range(prev + 1, nxt) if abs(rows[i]["x0"] - numx) < tol and not OPT_START.match(rows[i]["t"])
                and not SECTION.search(rows[i]["t"]) and i > prev + 1]
        if not cand:   # 題號整個沒讀到、列從內文欄開始：取前一題選項 (D) 之後、隔一大段空白的第一列
            seen_d, last = False, None
            for i in range(prev + 1, nxt):
                seen_d = seen_d or "D" in OPT.findall(rows[i - 1]["t"])
                if rows[i - 1]["x0"] < 0.55 * rows[i - 1]["W"]: last = rows[i - 1]
                gap = rows[i]["yc"] - last["yc"] if last and rows[i]["page"] == last["page"] else 1e9
                if seen_d and gap > 2.5 * pitch and not OPT_START.match(rows[i]["t"]) and not SECTION.search(rows[i]["t"]) \
                        and rows[i]["x0"] < 0.55 * rows[i]["W"]:
                    cand = [i]; break
        if prev >= 0 and cand: starts[n] = cand[0]; rows[cand[0]]["guess"] = True
    order = sorted(starts.items(), key=lambda kv: kv[1])
    out, passage, prange, g_hdr = {}, "", None, False
    ends = [i for _, i in order[1:]] + [len(rows)]
    prev_end = 0
    for (n, i), end in zip(order, ends):
        # 題組文章：上一題結束到這題開頭之間，從「請閱讀…／回答第X~Y題」那列起的文字
        between = rows[prev_end:i]
        if any(SECTION.search(r["t"]) for r in between): passage, prange = "", None
        g = next((j for j, r in enumerate(between) if GROUP.search(r["t"])), None)
        txt_between = [r for r in between if len(r["t"]) > 1]
        if g is None and len(txt_between) >= 2 and sum(len(r["t"]) for r in txt_between) >= 40:
            passage, prange, g_hdr = "\n".join(r["t"] for r in txt_between), None, False      # 沒有標題的題組文章
        elif g is not None:
            g_hdr = True
            passage = "\n".join(r["t"] + ((" " + r["fig"]) if r["fig"] else "") for r in between[g:])
            m = RANGE.search(" ".join(r["t"] for r in between[g:g + 2]))
            prange = (int(m.group(1)), int(m.group(2))) if m else None
        block, side = [rows[i]], []
        for r in rows[i + 1:end]:
            if SECTION.search(r["t"]) and not OPT_START.match(r["t"]): break
            labs = "".join(OPT.findall("\n".join(b["t"] for b in block)))
            # 選項都出現之後又隔了一大段空白 → 下一個題組的文章（沒有「請閱讀…」標題的情況）
            if "D" in labs and not OPT_START.match(r["t"]) and r["x0"] < 0.55 * r["W"] and r["page"] == block[-1]["page"] and r["yc"] - block[-1]["yc"] > 2.5 * pitch:
                break
            if r["x0"] > 0.55 * r["W"] and not OPT_START.match(r["t"]):   # 右側註釋、出處、圖說
                side.append(r); continue
            block.append(r)
        prev_end = i + len(block) + len(side)
        texts = [r["t"] for r in block]
        m = QNUM.match(texts[0]) or QNUM_ZH.match(texts[0])
        label = ""
        if m and int(m.group(1)) == n: label, texts[0] = texts[0][:m.end()].strip(), texts[0][m.end():]
        # 選項標記被讀成別的符號（例：「(D)」→「(①)」）：位在選項欄、順序上剛好該是下一個標記時，只修標記本身
        seen = ""
        for j, r in enumerate(block):
            seen += "".join(OPT.findall(texts[j]))
            mm = BADLAB.match(texts[j])
            if mm and not OPT_START.match(texts[j]) and abs(r["x0"] - optx) < tol and seen and seen[-1] in "ABC":
                nxt_lab = "ABCD"["ABCD".index(seen[-1]) + 1]
                texts[j] = f"({nxt_lab})" + texts[j][mm.end():]; seen += nxt_lab
        stem, opts = split_opts("\n".join(texts))
        fig = " ".join(r["fig"] for r in block if r["fig"])
        fig = " ".join([fig] + [r["t"] for r in side]).strip()
        if fig: stem = (stem + "\n" + fig).strip()
        if passage and prange is None and not g_hdr:
            # 沒有標題的文章：只延續到和它有字面重疊的題（題幹／選項中有 4 字片段出現在文章裡，或提到「本文、文中」）
            qt = re.sub(r"\s", "", stem + "".join(opts.values())); pt = re.sub(r"\s", "", passage)
            if not (re.search(r"本文|文中|上文|短文|文章|這段", qt) or any(qt[k:k + 4] in pt for k in range(len(qt) - 3))):
                passage = ""
        use_p = passage and (prange is None or prange[0] <= n <= prange[1])
        out[n] = {"stem": stem, "options": opts, "passage": passage if use_p else "", "guess": bool(block[0].get("guess")), "label": label, "page": block[0]["page"] + 1, "y": block[0]["yc"]}
    return out

def lis_text_questions(pdf):
    """聽力題本文字層 → {題號: (stem, options, page)}"""
    out = {}
    for pno in range(page_count(pdf)):
        lines = [l.rstrip() for l in unicodedata.normalize("NFKC", pdf_page_text(pdf, pno)).splitlines()]
        cur = None
        for l in lines:
            m = re.match(r"^\s*第\s*(\d{1,2})\s*題\s*$", l)
            if m:
                cur = int(m.group(1)); out[cur] = {"lines": [], "page": pno, "label": l.strip()}; continue
            if re.search(r"第[一二三四五]部分|示例題|聽力試題播音|試題結束|請翻頁|^\s*\d{1,2}\s*$", l):
                cur = None; continue
            if cur is not None: out[cur]["lines"].append(l)
    res = {}
    for n, d in out.items():
        body = "\n".join(x.strip() for x in d["lines"] if x.strip())
        stem, opts = split_opts(body, "ABC")
        # 圖片選項：(A)(B)(C) 三個標記排在同一列、中間沒字（文字層裡的圖內字多是字型編碼亂碼，不採用）
        pic = any(re.fullmatch(r"\s*\(A\)\s+\(B\)\s+\(C\)\s*", x) for x in d["lines"])
        res[n] = {"label": d["label"], "stem": stem, "options": opts, "page": d["page"], "pic": pic}
    return res

def looks_like_text(d):
    t = re.sub(r"[\s\W_]", "", d["t"])
    if d["s"] < 0.8: return False
    if len(re.findall(r"[A-Za-z0-9]", t)) >= 2 and re.search(r"[A-Za-z]{2}|\d{2}", d["t"]): return True
    cjk = [c for c in t if "\u4e00" <= c <= "\u9fff" and c not in "田月口日目回皿"]
    return len(cjk) >= 2

def lis_picture_text(pg, n):
    """OCR 頁：第 n 題的圖片選項區裡（(A)(B)(C) 標記之後、下一題／下一部分之前）各欄能辨識的字。"""
    ls = []
    for l in pg["lines"]:
        xs = [p[0] for p in l["box"]]; ys = [p[1] for p in l["box"]]
        ls.append({"x0": min(xs), "y0": min(ys), "y1": max(ys), "t": l["text"].strip(), "s": l["score"]})
    head = [d for d in ls if re.fullmatch(rf"第\s*{n}\s*[題题]", d["t"])]
    if not head: return None
    y_start = head[0]["y1"]
    nxt = [d["y0"] for d in ls if d["y0"] > y_start and (re.fullmatch(r"第\s*\d+\s*[題题]", d["t"]) or re.search(r"第[一二三四五]部分", d["t"]))]
    y_end = min(nxt) if nxt else pg["h"] * 0.93
    labs = {}
    for d in ls:
        m = re.fullmatch(r"[\(（]\s*([ABC])\s*[\)）]", d["t"])
        if m and y_start - 5 <= d["y0"] < y_end and m.group(1) not in labs: labs[m.group(1)] = d
    if len(labs) < 3: return None
    y_lab = max(d["y1"] for d in labs.values())
    cols = sorted(labs.items(), key=lambda kv: kv[1]["x0"])
    opts = {k: [] for k in "ABC"}
    for d in sorted(ls, key=lambda d: (d["y0"], d["x0"])):
        if not (y_lab - 3 <= d["y0"] < y_end) or d in labs.values(): continue
        if re.fullmatch(r"\d{1,2}", d["t"]) and d["y0"] > pg["h"] * 0.9: continue   # 頁碼
        if not looks_like_text(d): continue                                       # 線條圖被讀成「田」「D o D」之類
        col = None
        for k, lab in cols:
            if d["x0"] >= lab["x0"] - 10: col = k
        if col: opts[col].append(d["t"])
    return {k: " ".join(v) for k, v in opts.items()}

def build():
    cache = Path(os.environ.get("CAPOCR_CACHE") or (Path(tempfile.gettempdir()) / "capocr_cache"))
    if not os.environ.get("CAPOCR_NOFETCH"): fetch(cache)
    exp = expected_keys()
    rows, report = [], []
    # ---- A. 102/103 掃描題本 ----
    for y in (102, 103):
        for lab in SCAN_ORDER:
            subj = SCAN_SUBJ[lab]; src = f"{y}__{lab}.pdf"
            want = exp[("CAP", y, subj)]
            pages = load_pages(cache, f"{y}__{lab}")
            n_pages = page_count(RAW / src)
            seg = segment_scan(pages, want) if pages else {}
            n_lis = 0
            for q, a in sorted(want.items(), key=lambda kv: int(kv[0])):
                s = seg.get(int(q))
                lis = subj == "英語閱讀" and int(q) <= 20      # 102/103 英語卷第 1–20 題是聽力
                r = {"key": f"CAP|{y}|{subj}|{q}", "exam": "CAP", "year": y, "subject": subj, "q": q,
                     "stem": s["stem"] if s else "", "options": s["options"] if s else {},
                     "answer": a["answer"], "accept": a["accept"], "src": src, "ocr": True}
                if s: r["page"] = s["page"]          # 題目開頭在 PDF 第幾頁（1 起算）
                labels = "ABC" if lis else "ABCD"
                for k in labels: r["options"].setdefault(k, "")
                notes = []
                if s and s["passage"]: r["passage"] = s["passage"]
                if not s: notes.append("OCR 未切到此題")
                elif s["guess"]: notes.append("題號 OCR 未讀出，依版面位置定位")
                if lis:
                    n_lis += 1
                    if s and not r["stem"].strip() and QNUM_ZH.match(s["label"]): r["stem"] = s["label"]   # 只印題號（照 OCR 原樣）
                    if not any(r["options"].values()): notes.append("聽力題，選項為圖片")
                elif sum(1 for v in r["options"].values() if v.strip()) < 4: notes.append("部分選項無文字（圖片／公式）或 OCR 未讀出")
                if notes: r["note"] = "；".join(notes)
                rows.append(r)
            report.append((f"CAP|{y}|{subj}", len(seg), len(want), len(pages), n_pages))
    # ---- B. 英語聽力 104–115 ----
    stage = Path(tempfile.mkdtemp(prefix="capocr_lis_"))
    for y, pdf in listening_pdfs(stage).items():
        want = exp[("CAP", y, "英語聽力")]
        tq = lis_text_questions(pdf)
        src = f"{y}__英語（聽力）.bin"
        for q, a in sorted(want.items(), key=lambda kv: int(kv[0])):
            n = int(q); t = tq.get(n)
            r = {"key": f"CAP|{y}|英語聽力|{q}", "exam": "CAP", "year": y, "subject": "英語聽力", "q": q,
                 "stem": "", "options": {}, "answer": a["answer"], "accept": a["accept"], "src": src, "ocr": False}
            if t and not t["pic"] and any(v.strip() for v in t["options"].values()):
                r["stem"] = t["stem"]; r["options"] = {k: t["options"].get(k, "") for k in "ABC"}
            else:
                # 圖片選項：題幹只有題號；選項用 OCR 圖中文字
                r["stem"] = t["label"] if t else ""
                r["options"] = {k: "" for k in "ABC"}
                pj = cache / f"{y}__英語聽力__p{t['page']:02d}.json" if t else None
                pt = lis_picture_text(json.loads(pj.read_text()), n) if pj and pj.exists() else None
                if pt and any(v.strip() for v in pt.values()):
                    r["options"] = pt; r["ocr"] = True
                if any(v.strip() for v in r["options"].values()): r["note"] = "聽力題，選項為圖片；options 為圖中 OCR 讀到的文字"
                elif r["stem"]: r["note"] = "聽力題，選項為圖片，圖中無可辨識文字；stem 只有題本上印的題號"
                else: r["note"] = "聽力題無文字"
            rows.append(r)
        got = sum(1 for q in want if int(q) in tq)
        report.append((f"CAP|{y}|英語聽力", got, len(want), "text", ""))
    out = ROOT / "data/questions/extra_ocr.jsonl"
    with open(out, "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"寫出 {len(rows)} 題 → {out.relative_to(ROOT)}")
    for x in report: print("  ", *x)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "worker": worker(sys.argv[2:])
    elif cmd == "remote": remote()
    elif cmd == "monitor": monitor()
    elif cmd == "build": build()
