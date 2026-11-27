"""補切題：學測英文空格題（文意選填／篇章結構／克漏字）＋ 各科在 exam_pdf.jsonl 裡的剩餘缺題
→ data/questions/extra_misc.jsonl
每行：{"key","exam","year","subject","q","stem","options","answer","accept","src","blank"(,"note")}
- 空格題（blank=true）：stem = 整篇文章（含空格編號），options = 共用選項池；
  舊制克漏字每格各有 (A)~(D)，options 放該格自己的選項。
- 一般題（blank=false）：stem = 題號後到 (A) 前，options = (A)~(E)。題組只放該題自己的題幹。
- 抽不到的題照樣輸出：stem ""、options {}、note 說明原因。
只處理 exam_pdf.jsonl 沒有的題鍵（不重覆、不覆蓋既有資料）。
範圍：GSAT／GSAT-makeup 的 英文、國文、國綜、社會、自然；CAP 104 以後的 國文、社會、自然、數學、英語閱讀。
用法：python3 scripts/extract_misc.py [--paper GSAT|115|英文] [--show]"""
import collections, json, re, subprocess, sys, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from extract_questions import papers, pdf_text  # noqa: E402  借用：題本清單、pdftotext

GSAT_SUBJ = {"英文", "國文", "國綜", "社會", "自然"}
CAP_SUBJ = {"國文", "社會", "自然", "數學", "英語閱讀"}
CJK = "⺀-⿿　-〿぀-ヿ㐀-鿿豈-﫿︰-﹏＀-￯"
HAS_CJK = re.compile(f"[{CJK}]")
OPTP = re.compile(r"\(\s*([A-O])\s*\)")
OPT_LINE = re.compile(r"^\s*\(\s*[A-O]\s*\)")
NUM_OPT_LINE = re.compile(r"^\s*(\d+)\s*[.．]\s*\(\s*A\s*\)")

# ---------------- 清理 ----------------
JUNK_S = re.compile(  # 比對「去掉所有空白」後的整行
    r"^(?:(?:\d+(?!\d)年(?:學測|指考)|\d+(?!\d)[學学]年度.*|[一-鿿]{2,4}考科|第\d+(?!\d)頁|共\d+(?!\d)頁|-?\d+(?!\d)-?)+"
    r"|.*請記得在答題卷.*|.*請翻頁.*|.*背面(?:尚|還)有試題.*|[(（]?請由第?\d+題繼續作答[)）]?|.*作答注意事項.*)$")

def unparen(text):
    """部分題本字型把字映到「括號／圈圈表意字」（㈹、㊣…），NFKC 會變成 (代)：還原成單字。"""
    return "".join(unicodedata.normalize("NFKC", c).strip("()") if 0x3220 <= ord(c) <= 0x3247 or 0x3280 <= ord(c) <= 0x32B0 else c
                   for c in text)

def clean_lines(text):
    out = []
    for l in unicodedata.normalize("NFKC", unparen(text)).replace("\f", "\n").splitlines():
        s = re.sub(r"\s", "", l)
        if s and JUNK_S.match(s): continue
        out.append(l.rstrip())
    return out

def tidy(s):
    """去掉 CJK 字之間 pdftotext 插入的空白與斷行、壓縮多餘空白。"""
    s = "\n".join(x.strip() for x in s.splitlines())
    s = re.sub(r"\n{2,}", "\n", s).strip()
    near = f"[{CJK},.:;?!()「」『』、]"
    s = re.sub(f"(?<=[{CJK}])[ \t]+(?={near})|(?<={near})[ \t]+(?=[{CJK}])", "", s)
    s = re.sub(f"(?<=[{CJK}])\n(?=[{CJK}(])", "", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()

def split_opts(body, letters="A-E"):
    """選項從「後面緊接著 (B) 的那個 (A)」開始，依 A、B、C… 連號取；
    題幹裡零星的 (C)（例如圖上的單位）不會被當成選項。"""
    rx = re.compile(rf"\(\s*([{letters}])\s*\)")
    ms = list(rx.finditer(body))
    st = next((k for k in range(len(ms)) if ms[k].group(1) == "A" and (k + 1 == len(ms) or ms[k + 1].group(1) in "BC")), None)
    if st is None: return tidy(body), {}
    seq = [ms[st]]
    for m in ms[st + 1:]:
        if 1 <= ord(m.group(1)) - ord(seq[-1].group(1)) <= 2: seq.append(m)   # 容許中間漏一個（該選項是圖）
    opts = {}
    for k, m in enumerate(seq):
        end = seq[k + 1].start() if k + 1 < len(seq) else len(body)
        opts[m.group(1)] = tidy(body[m.end():end])
    return tidy(body[:ms[st].start()]), opts

# ---------------- 資料 ----------------
def load():
    ans = collections.defaultdict(dict)
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l); ans[(r["exam"], r["year"], r["subject"])][r["q"]] = r
    have, empty = set(), set()
    for l in open(ROOT / "data/questions/exam_pdf.jsonl"):
        r = json.loads(l); have.add(r["key"])
        if not r["stem"].strip() or not r["options"]: empty.add(r["key"])
    return ans, have, empty

def in_scope(exam, year, subject):
    if exam.startswith("GSAT"): return subject in GSAT_SUBJ
    return exam == "CAP" and year >= 104 and subject in CAP_SUBJ

def qnum(q):
    m = re.fullmatch(r"(?:P2-)?(\d+)", q)
    return int(m.group(1)) if m else None

# ---------------- 一般題 ----------------
HEADER = re.compile(
    r"(題組|^第[壹貳參肆伍一二三四五]部分|^[壹貳參肆伍]、|^[一二三四五六七八九十]+、|^說明[:：]|請閱讀.*(回答|作答)|"
    r"閱讀下(列|文|面|圖).*(回答|後)|回答第?\d+|^參考選項|^[ⅠⅡⅢIV]+\.|^非選擇題|^混合題|^\(\d+-\d+\)$)")

def qline_rx(n, nodot=False):
    d = r"\s?".join("[1lI]" if c == "1" else c for c in str(n))   # 舊題本有 l0.、3l. 這類錯字
    if nodot:   # 「74 西邊…」漏了句點：只收靠左、緊接中文
        return re.compile(rf"^\s{{0,2}}{d}\s+(?=[{CJK}])")
    return re.compile(rf"^\s{{0,10}}{d}\s*[.．、](?!\d)")
ANY_Q = re.compile(r"^\s{0,10}\d(?:\s?\d)?\s*[.．、](?!\d)")

def segment(lines, nums):
    """nums：該卷所有一般題號（遞增）。先列每題候選開頭行，再取行號與題號同時遞增的最長鏈。"""
    cands = []
    for n in nums:
        rx, rx2 = qline_rx(n), qline_rx(n, True)
        for i, l in enumerate(lines):
            if not (rx.match(l) or rx2.match(l)): continue
            ok = bool(OPTP.search(l))
            for l2 in lines[i + 1:i + 80]:
                if ok or ANY_Q.match(l2): break
                if OPTP.search(l2): ok = True
            if ok: cands.append((i, n))
    cands.sort()
    best = [1] * len(cands); prev = [-1] * len(cands)
    for a in range(len(cands)):
        for b in range(a):
            if cands[b][0] < cands[a][0] and cands[b][1] < cands[a][1] and best[b] + 1 > best[a]:
                best[a], prev[a] = best[b] + 1, b
    chain = []
    a = max(range(len(cands)), key=lambda k: best[k]) if cands else -1
    while a >= 0: chain.append(cands[a]); a = prev[a]
    chain.reverse()
    out = {}
    for j, (i, n) in enumerate(chain):
        end = chain[j + 1][0] if j + 1 < len(chain) else len(lines)
        out[n] = cut_block(lines, i, end, n)
    # 補救：選項是圖片（看不到 (A)）、雙欄排版、一行多個小題
    starts = [i for i, _ in chain]
    for n in nums:
        if n in out: continue
        lo = max([i for i, m in chain if m < n] or [0]); hi = min([i for i, m in chain if m > n] or [len(lines)])
        for i in range(hi - 1, lo - 1, -1):   # 由後往前：避開封面「1. 所有試題…」
            if qline_rx(n).match(lines[i]) or qline_rx(n, True).match(lines[i]):
                end = min([k for k in starts if k > i] or [len(lines)])
                end = next((k for k in range(i + 1, end) if ANY_Q.match(lines[k])), end)
                out[n] = cut_block(lines, i, end, n); break
            items = re.findall(r"(?<![\d.])(\d\s?\d?)\s*[.．]\s*([^\s\d.．]+)", lines[i])
            hit = [t for k, t in items if int(k.replace(" ", "")) == n]
            if len(items) >= 2 and hit and not OPTP.search(lines[i]):
                out[n] = {"stem": tidy(hit[0]), "options": {}, "note": "一行多個小題（配合題），選項為表格代號，無文字"}; break
            m = re.search(rf"(?<=\s{{3}}){n}\.\s", lines[i])
            if m:   # 雙欄：題目在右欄，取同一欄位以右的文字
                c = m.start(); col = [lines[i][c + m.end() - m.start():]]
                for l in lines[i + 1:hi]:
                    r = l[c:] if len(l) > c else ""
                    if re.match(r"\s{0,3}\d+\.\s", r) or HEADER.search(re.sub(r"\s", "", l)): break
                    col.append(r)
                stem, opts = split_opts("\n".join(col))
                if opts: out[n] = {"stem": stem, "options": opts}; break
    return out

def crop_right(l):
    """會考題本常把圖表排在右欄：中文行在大段空白之後的右欄文字（無選項標記）裁掉；只剩零星符號的行清空。"""
    m = re.search(r"\S(\s{6,})\S", l)
    if m and m.start(1) > 8 and HAS_CJK.search(l[:m.start(1)]) and not OPTP.search(l[m.end(1):]):
        l = l[:m.start(1)]
    l = re.sub(r"\s+[^\x00-\x7f\u3000-\u9fff\uff00-\uffef]{1,2}\s*$", "", l)   # 行尾零星的圖內符號
    if l.strip() and not re.search(rf"[{CJK}A-Za-z0-9]", l): return ""
    if re.fullmatch(r"\s*[^\x00-\x7f\u3000-\u9fff\uff00-\uffef]{1,3}\s*", l): return ""
    return l

WEIRD = re.compile("[\u0100-\u024f\u0400-\u058f\u1e00-\u1eff\u2c00-\u2dff\u3040-\u30ff\u3400-\u4dbf\ue000-\uf8ff]")
CAPTION = re.compile(r"^.{0,30}?[圖表]\s*(?:\d+|[一二三四五六七八九十]+|[(][^)]{1,5}[)])$")
STOP = re.compile(r"[。?？:：,，」]$")

def scrub(g, subject):
    """一般題的圖表殘渣：圖內亂碼字元行、& 開頭的圖註、圖說（圖3、圖(五)）及其前面的圖內標籤；選項尾巴的圖說。"""
    def lines_ok(t):
        return [x for x in t.splitlines() if not x.lstrip().startswith("&")]
    L = lines_ok(g["stem"])
    for k in range(len(L) - 1, -1, -1):
        if k < len(L) and k > 0 and CAPTION.match(L[k].strip()):
            j = k
            while j > 0 and not STOP.search(L[j - 1].strip()): j -= 1
            if j > 0: del L[j:k + 1]
            else: del L[k]
    opts = {}
    for key, v in g["options"].items():
        v = "\n".join(lines_ok(v))
        v2 = re.sub(r"\s*[圖表]\s*(?:\d+|[一二三四五六七八九十]+|[(][^)]{1,5}[)])$", "", v)
        opts[key] = v2 if v2.strip() else v
    return {**g, "stem": "\n".join(L).strip(), "options": opts}

def cut_block(lines, i, end, n):
    first = qline_rx(n).sub("", lines[i], count=1)
    if first == lines[i]: first = qline_rx(n, True).sub("", lines[i], count=1)
    block = [first]
    for l in lines[i + 1:end]:
        if HEADER.search(re.sub(r"\s", "", l)): break
        block.append(l)
    body = "\n".join(block)
    stem, opts = split_opts(body)
    if opts:   # 最後一個選項之後若空行再接長段文字（題組文章、圖說），截掉
        last = sorted(opts)[-1]
        raw = re.split(r"\(\s*" + last + r"\s*\)", body)[-1]
        seg = re.split(r"\n\s*\n", raw.strip("\n"), maxsplit=1)
        if len(seg) == 2 and len(seg[1].strip()) > 0: opts[last] = tidy(seg[0])
    r ={"stem": stem, "options": opts}
    if not any(opts.values()): r["note"] = "選項為圖片，無文字"
    return r

# ---------------- 空格題 ----------------
def tok_rx(n):
    return re.compile(rf"(?<![A-Za-z0-9.\-/:])\(?{n}\)?(?![A-Za-z0-9\-/]|\.\d|\s*[.．]\s*\(|\.\s+[A-Z“\"(])")

def find_blank_group(lines, n0, cands, lo, english, cloze_only=False):
    """回傳 (stem, {n: options}, nums) 或 None。cands：可能屬於空格題的題號（遞增）。"""
    later = [n0 + 1] if n0 + 1 in cands else []
    for L in range(lo, len(lines)):
        l = lines[L]
        if not tok_rx(n0).search(l) or NUM_OPT_LINE.match(l) or OPT_LINE.match(l): continue
        if english and (HAS_CJK.search(l) or len(re.findall(r"[A-Za-z]{2,}", l)) < 2 or ANY_Q.match(l)): continue
        if not english and HEADER.search(re.sub(r"\s", "", l)): continue
        if later and not any(tok_rx(later[0]).search(x) for x in lines[L:L + 20]): continue
        # 文章起點
        S = L
        while S > 0:
            p = lines[S - 1]; ps = re.sub(r"\s", "", p)
            if OPT_LINE.match(p) or NUM_OPT_LINE.match(p) or HEADER.search(ps) or "空格" in ps: break
            if english and HAS_CJK.search(p): break
            if not english and ANY_Q.match(p): break
            S -= 1
        # 文章終點
        E = L
        while E < len(lines) and not (OPT_LINE.match(lines[E]) or NUM_OPT_LINE.match(lines[E])
                                      or re.sub(r"\s", "", lines[E]).startswith("參考選項")):
            E += 1
        if E >= len(lines) or E - L > 60: continue
        passage = "\n".join(lines[S:E])
        nums = []
        for n in cands:
            if n < n0: continue
            if tok_rx(n).search(passage): nums.append(n)
            else: break
        if re.sub(r"\s", "", lines[E]).startswith("參考選項"):
            E += 1
            while E < len(lines) and not lines[E].strip(): E += 1
        # 選項
        opts = {}
        if NUM_OPT_LINE.match(lines[E]):          # 克漏字：每格自己的 (A)~(D)
            cur, buf, i = None, [], E
            while i < len(lines):
                l = lines[i]; m = NUM_OPT_LINE.match(l)
                if m:
                    if cur is not None: opts[cur] = split_opts("\n".join(buf), "A-D")[1]
                    cur, buf = int(m.group(1)), [re.sub(r"^\s*\d+\s*[.．]", "", l)]
                elif OPT_LINE.match(l) and cur is not None: buf.append(l)
                elif not l.strip() and NUM_OPT_LINE.match(next((x for x in lines[i + 1:] if x.strip()), "")): pass
                else: break
                i += 1
            if cur is not None: opts[cur] = split_opts("\n".join(buf), "A-D")[1]
            opts = {n: opts.get(n, {}) for n in nums}
            if not opts.get(n0): continue        # 選項行的題號對不上 → 不是這篇
        elif cloze_only: continue
        else:                                      # 共用選項池
            buf, i, want = [], E, "A"
            while i < len(lines):
                l = lines[i]; ls = re.sub(r"\s", "", l)
                if not l.strip():
                    nxt = next((x for x in lines[i + 1:] if x.strip()), "")
                    m = OPT_LINE.match(nxt)
                    if not (m and OPTP.match(nxt.strip()).group(1) == want): break
                elif buf and (HEADER.search(ls) or ANY_Q.match(l) or NUM_OPT_LINE.match(l)): break
                elif english and HAS_CJK.search(l): break
                buf.append(l)
                found = OPTP.findall(l)
                if found: want = chr(ord(max(found)) + 1)
                i += 1
            pool = split_opts("\n".join(buf), "A-O")[1]
            if len(pool) < max(4, len(nums)) or (len(nums) < 2 and len(pool) < 5): continue   # 選項池太小 → 只是下一題的選項
            opts = {n: pool for n in nums}
        if english:
            passage = "\n".join(re.sub(rf"\s*\S*[ A-Za-z’'\-]*[{CJK}]+.*$", "", x) if HAS_CJK.search(x) else x for x in lines[S:E])
        return tidy(passage) if not english else tidy_en(passage), opts, nums
    return None

def strip_gloss(g):
    """會考英文行尾的中文註解（refer to 指稱）去掉。"""
    f = lambda t: "\n".join(x for x in (re.sub(rf"\s*\S*[ A-Za-z’'\-]*[{CJK}]+.*$", "", y) if HAS_CJK.search(y) else y
                                       for y in t.splitlines()) if x.strip()).strip()
    return {**g, "stem": f(g["stem"]), "options": {k: f(v) for k, v in g["options"].items()}}

def tidy_en(s):
    s = "\n".join(re.sub(r"[ \t]{2,}", " ", x.strip()) for x in s.splitlines())
    return re.sub(r"\n{2,}", "\n", s).strip()

# ---------------- 主程式 ----------------
def run(only=None, show=False):
    ans, have, empty = load()
    rows, report = [], []
    for exam, year, subject, path in papers("pdf"):
        if not in_scope(exam, year, subject): continue
        paper = f"{exam}|{year}|{subject}"
        if only and paper != only: continue
        a = ans.get((exam, year, subject), {})
        miss = [q for q in a if f"{paper}|{q}" not in have and qnum(q) is not None]
        # 學測英文：exam_pdf 已有但題幹或選項為空的克漏字格 → 試著以空格題重抽（成功才輸出，取代原列）
        fix = [q for q in a if exam.startswith("GSAT") and subject == "英文" and f"{paper}|{q}" in empty] 
        if not miss and not fix: continue
        lines = clean_lines(pdf_text(path))
        got = {}
        if len("".join(lines).replace(" ", "")) < 200:
            report.append((paper, 0, len(miss), "掃描檔（無文字層）"))
        else:
            # 1) 空格題：英文、國文
            if subject in ("英文", "國文", "國綜", "英語閱讀"):
                english = subject in ("英文", "英語閱讀")
                for part in ("P2", ""):
                    qs = sorted([q for q in miss + fix if q.startswith("P2-") == (part == "P2")], key=qnum)
                    if not qs: continue
                    lo = 0
                    if part == "P2":   # 第二部分：在第一個選項行之後才算（封面也會提到「第二部分」）
                        f = next(i for i, l in enumerate(lines) if OPTP.search(l))
                        lo = next((i for i, l in enumerate(lines) if i > f and "第二部分" in re.sub(r"\s", "", l)), f)
                    nums = [qnum(q) for q in qs]
                    done = set()
                    for n0 in nums:
                        if n0 in done: continue
                        r = find_blank_group(lines, n0, [n for n in nums if n not in done], lo, english, exam == "CAP")
                        if not r: continue
                        stem, opts, ns = r
                        for n in ns:
                            q = f"P2-{n}" if part == "P2" else str(n)
                            got[q] = {"stem": stem, "options": opts[n], "blank": True}
                            done.add(n)
            # 2) 一般題
            rest = [q for q in miss if q not in got and not q.startswith("P2-")]
            if rest:
                nums = sorted({qnum(q) for q in a if not q.startswith("P2-") and qnum(q) is not None})
                L2 = [crop_right(l) for l in lines] if exam == "CAP" and subject != "英語閱讀" else lines
                if subject not in ("國文", "國綜", "英文", "英語閱讀"):   # 圖內字型亂碼（假名、西里爾、擴充漢字…）整行丟掉
                    L2 = [l for l in L2 if OPTP.search(l) or ANY_Q.match(l) or len(WEIRD.findall(l)) < 0.15 * max(1, len(re.sub(r"\s", "", l)))]
                seg = segment(L2, nums)
                for q in rest:
                    s = seg.get(qnum(q))
                    if s and (s["stem"] or s["options"]):
                        got[q] = scrub({**s, "blank": False}, subject)
                        if subject == "英語閱讀": got[q] = strip_gloss(got[q])
            report.append((paper, len([q for q in got if q in miss]), len(miss), ""))
        fixed = [q for q in fix if q in got]
        if fixed: report.append((paper + "（重抽 exam_pdf 空白列）", len(fixed), len(fix), ""))
        for q in sorted(miss + fixed, key=lambda q: (q.startswith("P2"), qnum(q))):
            r = a[q]
            g = got.get(q)
            row = {"key": f"{paper}|{q}", "exam": exam, "year": year, "subject": subject, "q": q,
                   "stem": g["stem"] if g else "", "options": g["options"] if g else {},
                   "answer": r["answer"], "accept": r["accept"], "src": path.name,
                   "blank": g["blank"] if g else False}
            if g and g.get("note"): row["note"] = g["note"]
            if not g: row["note"] = NOTES.get(f"{paper}|{q}", "切題器找不到此題")
            if q in fixed: row["supersedes"] = "exam_pdf.jsonl"   # 同鍵：原列題幹或選項為空，請以本列為準
            rows.append(row)
            if show:
                print(f"--- {row['key']} blank={row['blank']} ans={row['answer']}")
                print("  STEM:", row["stem"][:300].replace("\n", " / "))
                print("  OPTS:", json.dumps(row["options"], ensure_ascii=False)[:300])
    if not only:
        with open(ROOT / "data/questions/extra_misc.jsonl", "w") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tot_g = sum(x[1] for x in report); tot = sum(x[2] for x in report)
    print(f"補到 {tot_g}/{tot} 題（其餘輸出空白＋note） → data/questions/extra_misc.jsonl")
    for x in report:
        if x[1] < x[2]: print("   ", *x)

NOTES = {}   # 已查明原因的缺口：key → 原因（填在下方）

if __name__ == "__main__":
    run(sys.argv[sys.argv.index("--paper") + 1] if "--paper" in sys.argv else None, "--show" in sys.argv)
