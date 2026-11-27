"""學測數學（GSAT / GSAT-makeup，83–115）切題 → data/questions/extra_math.jsonl
只用標準庫 + pdftotext。

題型與題號：
- 單選／多選：卷面題號 1, 2, …；選項 (1)~(5)（83–85 為 (A)~(E)）。
- 83：填充題卷面編 1~10，空格標 (A)~(J)；官方題號就是 A~J。
- 84、85：填充題卷面編 12~20，官方題號同。
- 86–110（含補考 91、92）：填充／選填題卷面字母 A, B, …；官方格號是一串數字。
  字母 → 格號：把格號 (選擇題數+1)..(末格) 切成連續的 N 段（N = 字母題數），用動態規劃挑分數最高的切法：
    題本：該字母題文字裡印出的格號（且彼此排在一起）；
    答案卷（data/raw/gsat/A_，96 年起有文字層）：字母標籤垂直置中於該組格號左側；
    data/answers/vision_A.jsonl 的 note「填充題 X 第 N 格」（94、95）。
  -v 會印出每卷的切法與各題證據；自動判讀不可靠時可在 CELL_OVERRIDE 人工指定。
- 111–115：選填題卷面編 13, 14…，官方格號 13-1, 13-2 → 一題一列，答案串接。
用法：python3 scripts/extract_math.py [-v]"""
import collections, json, re, subprocess, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "data/raw/gsat/Q_"
ATXT = ROOT / "data/raw/gsat/txt"
OUT = ROOT / "data/questions/extra_math.jsonl"
VERBOSE = "-v" in sys.argv

# 字母題 → 第一個格號（自動判讀不可靠時人工指定；值為各字母的起始格號，依 A, B, C… 排）
CELL_OVERRIDE = {
    # 105 答案卷把字母印在該組第一列（不是置中），置中假設會誤判；依題本：A 14 15、B 16/17、C 18+19、D 20…24
    "GSAT|105|數學": [14, 16, 18, 20, 25, 26, 30],
}

JUNK = re.compile(
    r"(第\s*\d+\s*頁|共\s*\d+\s*頁|^\s*[-－–]\s*\d+\s*[-－–]\s*$|請記得在答題卷|請記得在答案卷|"
    r"^\s*\d+\s*年\s*學測|^\s*數\s*學\s*[AB]?\s*考\s*科\s*$|^\s*數學[AB]?考科\s*$|請翻頁|背面尚有試題|背面還有試題|"
    r"^\s*\d+\s*學年度學科能力測驗\s*$|^\s*-\s*\d+\s*-\s*$)")
STOP = re.compile(r"(參考公式|常用對數表|三角函數表|〈附錄〉|附錄|^\s*第\s*[一二三四五壹貳參肆]\s*部\s*分|"
                  r"^\s*[壹貳參肆伍]\s*、|^\s*[一二三四五]\s*、\s*[單多選非混]|^\s*說\s*明\s*[：:︰]|"
                  r"^\s*第\s*\d+\s*至\s*\d+\s*題為題組|^\s*\d+\s*[-–]\s*\d+\s*題為題組|^\s*非選擇題)")
FILL_HEAD = re.compile(r"(第\s*[二㆓貳]\s*部\s*[分份].{0,3}(填充|選填)|[貳二]\s*、\s*(填充|選填)|^\s*(三|二)\s*、\s*選填題|選填題\s*[（(]\s*占|^\s*二、填充題)")
QNUM = re.compile(r"^\s*(\d\s?\d?)\s*[\.．]\s*(.*)$")
QLET = re.compile(r"^\s*([A-L])\s*[\.．]\s*(.*)$")
CJK = "　-〿一-鿿＀-￯，。：；？！、（）「」『』"
CJK_SP = re.compile(rf"(?<=[{CJK}])[ \t]+(?=[{CJK}])")


def pdf_text(p):
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout


# 舊題本（90–93）常用帶括號／圈的漢字（㈲㈻㊠㉃…），NFKC 會變成「(有)」：改成單純的字
PAREN_HAN = {c: re.sub(r"[()]", "", unicodedata.normalize("NFKC", chr(c)))
             for c in list(range(0x3220, 0x3248)) + list(range(0x3280, 0x32B1))
             if re.fullmatch(r"\(?[\u4e00-\u9fff]\)?", unicodedata.normalize("NFKC", chr(c)))}


# Symbol 字型的私用區字元（pdftotext 常吐出 \uf03d 之類）→ 常見數學符號
SYMBOL_PUA = {0xF000 + k: v for k, v in {
    0x2B: "+", 0x2D: "−", 0x3D: "=", 0x3C: "<", 0x3E: ">", 0x28: "(", 0x29: ")", 0x5B: "[", 0x5D: "]",
    0x2C: ",", 0x2E: ".", 0x2F: "/", 0x7C: "|", 0x44: "Δ", 0x71: "θ", 0x70: "π", 0x61: "α", 0x62: "β",
    0x67: "γ", 0x64: "δ", 0x6C: "λ", 0x6D: "μ", 0x73: "σ", 0x77: "ω", 0x66: "φ", 0x53: "Σ", 0x57: "Ω",
    0xB4: "×", 0xB8: "÷", 0xB1: "±", 0xA3: "≤", 0xB3: "≥", 0xB0: "°", 0xD6: "√", 0xB9: "≠", 0xBB: "≈",
    0x5E: "⊥", 0xD0: "∠", 0xB7: "•", 0xA5: "∞", 0xE5: "∑", 0xAE: "→", 0xDE: "⇒", 0xCE: "∈", 0xC7: "∩",
    0xC8: "∪", 0xA2: "′", 0xD7: "⋅", 0xBC: "…", 0x20: " "}.items()}


def norm(text):
    return unicodedata.normalize("NFKC", text.translate(PAREN_HAN).translate(SYMBOL_PUA))


def clean_lines(text):
    out = []
    for l in norm(text).replace("\f", "\n").splitlines():
        if JUNK.search(l):
            continue
        out.append(l.rstrip())
    return out


def tidy(s):
    """收斂中文字間的空白、去掉多餘空行。"""
    lines = [CJK_SP.sub("", l).rstrip() for l in s.splitlines()]
    s = "\n".join(lines)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def paper_of(name):
    m = re.match(r"(\d+)學年度學科能力測驗(\(補考\))?－(數學[AB]?)__", name)
    return ("GSAT-makeup" if m.group(2) else "GSAT", int(m.group(1)), m.group(3))


def official():
    """{(exam, year, subj): {q: [(sub, answer, accept)]}}"""
    d = collections.defaultdict(lambda: collections.defaultdict(list))
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l)
        if not r["exam"].startswith("GSAT") or not r["subject"].startswith("數學"):
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", r["q"])
        q, sub = (m.group(1), int(m.group(2))) if m else (r["q"], 0)
        d[(r["exam"], r["year"], r["subject"])][q].append((sub, r["answer"], r["accept"]))
    for p in d.values():
        for v in p.values():
            v.sort()
    return d


def split_options(body, labels):
    """依序找 (1)(2)…(5) 或 (A)…(E)；回傳 (stem, options)。"""
    pos = []
    start = 0
    for lab in labels:
        m = re.compile(r"[\(（]\s*" + lab + r"\s*[\)）]").search(body, start)
        if not m:
            break
        pos.append((lab, m.start(), m.end()))
        start = m.end()
    if len(pos) < 2:
        return body, {}
    stem = body[:pos[0][1]]
    opts = {}
    for i, (lab, s, e) in enumerate(pos):
        end = pos[i + 1][1] if i + 1 < len(pos) else len(body)
        opts[lab] = tidy(body[e:end])
    return stem, opts


def find_starts(lines, ids, lo, hi, pat):
    """在 lines[lo:hi] 依序找題號 ids（字串）的開頭行。回傳 {id: line_idx}。"""
    out, k = {}, 0
    for i in range(lo, hi):
        if k >= len(ids):
            break
        m = pat.match(lines[i])
        if not m:
            continue
        tok = m.group(1).replace(" ", "")
        # 允許跳號（例如某題抓不到題號），但只往前
        if tok in ids[k:]:
            j = ids.index(tok, k)
            if j - k <= 2:
                out[tok] = i
                k = j + 1
    return out


def pre_chunk(lines, i, lo):
    """卷面排版常把題目的分數線上半、空格號碼印在題號那行的上方：
    緊貼題號行之上、上面隔著空行、不超過 3 行、不含選項與段落標記的一小塊，歸給這一題。"""
    j = i - 1
    while j >= lo and j > i - 4 and lines[j].strip():
        j -= 1
    if j == i - 1 or j < lo or lines[j].strip():
        return i
    chunk = lines[j + 1:i]
    if any(re.search(r"[\(（]\s*[1-5A-E]\s*[\)）]", l) or STOP.search(l) or FILL_HEAD.search(l) for l in chunk):
        return i
    return j + 1


def block_text(lines, start, qline, end, pat, qid=""):
    blk = []
    for j in range(start, end):
        l = lines[j]
        if j > qline and STOP.search(l):
            break
        m = QNUM.match(l)
        if j > qline and qid.isdigit() and m and int(qid) < int(m.group(1).replace(" ", "")) <= int(qid) + 5:
            break    # 下一題（例如題組裡的非選擇題 19、20）
        if j == qline:
            m = pat.match(l)
            l = m.group(2) if m else l
        blk.append(l)
    return "\n".join(blk)


def segments(lines, items, lo, tail, hard, groups=()):
    """items: [(id, qline)]；hard: 不可跨越的分界行（段落開頭等）；
    groups: 題組開頭行（「18-20 題為題組」），題組共同的敘述歸給題組第一題。回傳 {id: (start, qline, end)}"""
    items = sorted(items, key=lambda x: x[1])
    starts = []
    for k, (_, q) in enumerate(items):
        prev = items[k - 1][1] if k else lo
        g = [h for h in groups if prev < h <= q]
        starts.append(g[0] if g else max(pre_chunk(lines, q, lo), max([h for h in hard if h <= q] or [lo])))
    out = {}
    for k, (qid, q) in enumerate(items):
        nxt = [starts[k + 1]] if k + 1 < len(items) else []
        nxt += [h for h in hard if h > q] + [tail]
        out[qid] = (starts[k], q, min(nxt))
    return out


def answer_sheet_layout(exam, year, subj, lo, hi):
    """答案卷文字層：字母標籤垂直置中在它那組格號的左側欄位。
    回傳 (rows, lets)：rows {格號: (行, 欄群)}；lets {字母: (行, 欄群)}；沒有可用文字時回傳 ({}, {})。"""
    name = f"{year}學年度學科能力測驗{'(補考)' if exam == 'GSAT-makeup' else ''}－{subj}__"
    fs = list((ROOT / "data/raw/gsat/A_").glob(name + "*.pdf"))
    if not fs:
        return {}, {}
    text = unicodedata.normalize("NFKC", pdf_text(fs[0]))
    if "國文考科" in text or "題號" not in text:   # 合訂本（只有一行字母也沒有）或亂碼
        return {}, {}
    lines = text.splitlines()
    hdr = next(i for i, l in enumerate(lines) if "題號" in l)
    toks, lets = [], {}
    for li in range(hdr + 1, len(lines)):
        l = lines[li]
        if l.lstrip().startswith("※"):
            break
        # lo..hi 的數字只會是格號（選擇題答案、各格答案都是個位數或含逗號）
        for m in re.finditer(r"(?<![\d,])(\d{1,2})(?![\d,])", l):
            if lo <= int(m.group(1)) <= hi:
                toks.append((li, m.start(), int(m.group(1))))
        for m in re.finditer(r"(?<![A-Za-z0-9])([A-L])(?![A-Za-z0-9])", l):
            lets[m.group(1)] = (li, m.start())
    # 格號依 x 分欄
    xs = sorted({x for _, x, _ in toks})
    cols = []
    for x in xs:
        if cols and x - cols[-1][-1] <= 3:
            cols[-1].append(x)
        else:
            cols.append([x])
    colx = [min(c) for c in cols]
    which = lambda x: next(k for k, c in enumerate(cols) if x in c)
    rows = {n: (li, which(x)) for li, x, n in toks}
    out = {}
    for L, (li, x) in lets.items():
        right = [k for k in range(len(cols)) if colx[k] > x]
        if right:
            out[L] = (li, min(right, key=lambda k: colx[k]))
    return rows, out


def vision_notes(exam, year, subj):
    """data/answers/vision_A.jsonl 的 note「填充題 X 第 N 格」→ {N: X}"""
    out = {}
    p = ROOT / "data/answers/vision_A.jsonl"
    if p.exists():
        for l in open(p):
            r = json.loads(l)
            if (r["exam"], r["year"], r["subject"]) == (exam, year, subj):
                m = re.search(r"填充題\s*([A-L])\s*第\s*(\d+)\s*格", r.get("note", ""))
                if m:
                    out[int(m.group(2))] = m.group(1)
    return out


def seg_numbers(t):
    """題目文字裡的數字 → {數字: [(行, 欄)]}"""
    pos = collections.defaultdict(list)
    for li, l in enumerate(t.splitlines()):
        for m in re.finditer(r"(?<![\d,.，、/])\d+(?![\d,.，、/])", l):   # 「11,12,13」「0.5」這類不是格號
            x = m.group(0)
            pos[int(x)].append((li, m.start()))
            if 4 <= len(x) <= 6:                 # 黏在一起的格號，如 "1314"
                for w in range(0, len(x) - 1, 2):
                    pos[int(x[w:w + 2])].append((li, m.start() + w))
    return pos


def compact(pos, cs):
    """組內找得到的格號，若和同組另一格靠在一起（±2 行、12 欄內）就算排版上像一組空格。"""
    found = [c for c in cs if c in pos]
    if len(found) == 1 and len(cs) == 1:
        return 1
    n = 0
    for c in found:
        if any(abs(l1 - l2) <= 2 and abs(x1 - x2) <= 12
               for d in found if d != c for l1, x1 in pos[c] for l2, x2 in pos[d]):
            n += 1
    return n


def letter_cells(lets, seg_texts, first, last, sheet, vision):
    """在所有「連續切段」中挑分數最高的：
    - 題本：該字母題文字裡出現的格號 +1（出現在別題範圍不扣，因為雜訊數字到處都有）
    - 答案卷：字母必須在那組格號的欄位，且垂直置中（偏離每行扣 1）
    - vision_A note：每格吻合 +5、不合 -20
    回傳 (cells, evidence)；evidence[i] 為該題證據摘要。"""
    k = len(lets)
    nums = [seg_numbers(t) for t in seg_texts]
    rows, lpos = sheet

    def score(i, s, e):
        L = lets[i]
        sc, ev = 0.0, []
        q = sum(1 for c in range(s, e + 1) if c in nums[i])
        sc += q + 0.5 * compact(nums[i], list(range(s, e + 1)))
        if q:
            ev.append(f"題本{q}/{e - s + 1}")
        if L in lpos and all(c in rows for c in range(s, e + 1)):
            li, col = lpos[L]
            if any(rows[c][1] != col for c in range(s, e + 1)):
                sc -= 10
            else:
                mid = (rows[s][0] + rows[e][0]) / 2
                sc -= abs(mid - li) * 1.5
                sc += 2
                if abs(mid - li) <= 1:
                    ev.append("答案卷")
        v = [vision[c] == L for c in range(s, e + 1) if c in vision]
        if v:
            sc += 5 * sum(v) - 20 * (len(v) - sum(v))
            if all(v):
                ev.append("vision")
        return sc, ev

    best = {}

    def f(i, s):
        if (i, s) in best:
            return best[(i, s)]
        if i == k:
            r = (0.0, []) if s == last + 1 else (-1e9, [])
        else:
            r = (-1e9, [])
            for e in range(s, min(last, s + 9) + 1):
                sc, _ = score(i, s, e)
                sub = f(i + 1, e + 1)
                if sc + sub[0] > r[0]:
                    r = (sc + sub[0], [(s, e)] + sub[1])
        best[(i, s)] = r
        return r

    tot, seg = f(0, first)
    if tot < -1e8:
        return None, None
    cells = [list(range(s, e + 1)) for s, e in seg]
    evid = [score(i, s, e)[1] for i, (s, e) in enumerate(seg)]
    return cells, evid


def build():
    off = official()
    rows, report = [], []
    for pdf in sorted(QDIR.glob("*數學*__試題內容.pdf"), key=lambda p: paper_of(p.name)):
        exam, year, subj = paper_of(pdf.name)
        units = off.get((exam, year, subj))
        if not units:
            continue
        lines = clean_lines(pdf_text(pdf))
        n = len(lines)
        # 第一題：題號 1 且後面不遠處有 (1)(2)(3) 或 (A)(B)(C) 選項（跳過封面說明）
        def opt_ahead(i):
            nxt = next((j for j in range(i + 1, min(i + 40, n)) if QNUM.match(lines[j])), min(i + 40, n))
            w = "\n".join(lines[i:nxt])
            return all(re.search(r"[\(（]\s*" + c + r"\s*[\)）]", w) for c in "12") or \
                all(re.search(r"[\(（]\s*" + c + r"\s*[\)）]", w) for c in "AB")
        begin = next((i for i, l in enumerate(lines) if QNUM.match(l) and QNUM.match(l).group(1).replace(" ", "") == "1"
                      and "例" not in l and opt_ahead(i)), 0)
        # 尾端：參考公式／附錄之後不算
        tail = next((i for i in range(begin, n) if re.search(r"^\s*(參\s*考\s*公\s*式|〈附錄〉|附\s*錄|\d*\s*[\.．]?\s*常\s*用\s*對\s*數\s*表)", lines[i])), n)
        fill = next((i for i in range(begin, tail) if FILL_HEAD.search(lines[i])), None)

        qs = sorted(units, key=lambda q: (not q.isdigit(), int(q) if q.isdigit() else ord(q[0])))
        newfmt = year >= 111
        letters = [q for q in qs if not q.isdigit()]
        src = pdf.name
        got = {}

        def emit(q, body, labels, extra=None):
            stem, opts = split_options(body, labels) if labels else (body, {})
            stem = tidy(stem)
            r = {"key": f"{exam}|{year}|{subj}|{q}", "exam": exam, "year": year, "subject": subj, "q": q,
                 "stem": stem, "options": opts}
            r.update(extra or {})
            r["src"] = src
            if not stem and not opts:
                r["note"] = "圖題無文字"
            got[q] = r

        def unit_answer(q):
            v = units[q]
            if len(v) == 1:
                return v[0][1], v[0][2]
            a = "".join(x[1] for x in v)
            return a, [a]

        lab = list("ABCDE") if year <= 85 else list("12345")
        items = []      # (id, qline, pat, labels, extra)
        hard = [x for x in (fill,) if x is not None]
        if year == 83:
            mc = [q for q in qs if q.isdigit()]
            st = find_starts(lines, mc, begin, fill or tail, QNUM)
            items += [(q, st[q], QNUM, lab) for q in mc if q in st]
            # 填充題卷面 1~10，空格 (A)~(J)；跳過「說明：1. 2. 3.」：從第一個 (A) 往上找題號 1
            fa = next(i for i in range(fill, tail) if re.search(r"[\(（]\s*A\s*[\)）]", lines[i]))
            f1 = max(i for i in range(fill, fa + 1) if QNUM.match(lines[i]) and QNUM.match(lines[i]).group(1) == "1")
            fl = find_starts(lines, [str(i) for i in range(1, len(letters) + 1)], f1, tail, QNUM)
            items += [(letters[int(k) - 1], v, QNUM, None) for k, v in fl.items()]
        elif not (86 <= year <= 110):
            # 84、85、111–115：全部數字題號
            st = find_starts(lines, qs, begin, tail, QNUM)
            for q, i in st.items():
                is_fill = len(units[q]) > 1 or units[q][0][0] > 0 or (year <= 85 and fill is not None and i > fill)
                items.append((q, i, QNUM, None if is_fill else lab))
        else:
            # 86–110：數字選擇題 + 字母填充題（官方以連續格號計）
            T = max(int(q) for q in qs)
            fl_st = find_starts(lines, [chr(65 + i) for i in range(12)], fill if fill is not None else begin, tail, QLET)
            nlet = len(fl_st)
            fill0 = fill if fill is not None else (min(fl_st.values()) if fl_st else tail)
            hard = [fill0]
            mc_st = find_starts(lines, [str(i) for i in range(1, T + 1)], begin, fill0, QNUM)
            hdr = re.search(r"單[一㆒]?選擇?題\s*(\d+)\s*題.{0,3}多[重]?選擇?題\s*(\d+)\s*題", "\n".join(lines[:60]))
            nmc = int(hdr.group(1)) + int(hdr.group(2)) if hdr else max(int(k) for k in mc_st)
            m13 = re.search(r"列號\s*[\(（]\s*(\d+)\s*[-–~～至]\s*(\d+)\s*[\)）]", "\n".join(lines))
            if m13 and (int(m13.group(1)) != nmc + 1 or int(m13.group(2)) != T):
                report.append(f"{exam}|{year}|{subj}: 列號說明 {m13.group(0)} 與選擇題數 {nmc}、末格 {T} 不合")
            items += [(q, mc_st[q], QNUM, lab) for q in (str(i) for i in range(1, nmc + 1)) if q in mc_st]
            lets = [chr(65 + i) for i in range(nlet)]
            hl = re.search(r"第\s*A\s*[至到]\s*([A-L])\s*題", "\n".join(lines))
            if hl and ord(hl.group(1)) - 64 != nlet:
                report.append(f"{exam}|{year}|{subj}: 卷首說 A~{hl.group(1)}，找到 {nlet} 個字母題")
            items += [(L, fl_st[L], QLET, None) for L in lets]
        groups = [i for i in range(begin, tail) if re.search(r"題\s*為\s*題\s*組", lines[i])]
        seg = segments(lines, [(x[0], x[1]) for x in items], begin, tail, hard + groups, groups)
        meta = {x[0]: x for x in items}

        if 86 <= year <= 110:
            seg_texts = ["\n".join(lines[seg[L][0]:seg[L][2]]) for L in lets]
            key = f"{exam}|{year}|{subj}"
            if key in CELL_OVERRIDE:
                starts = CELL_OVERRIDE[key] + [T + 1]
                cells = [list(range(starts[k], starts[k + 1])) for k in range(len(starts) - 1)]
                evid = [["人工"]] * len(cells)
            else:
                cells, evid = letter_cells(lets, seg_texts, nmc + 1, T,
                                           answer_sheet_layout(exam, year, subj, nmc + 1, T),
                                           vision_notes(exam, year, subj))
            if cells is None or len(cells) != len(lets):
                report.append(f"{key}: 字母→格號判讀失敗（nmc={nmc}, T={T}, 字母 {nlet}）")
                cellmap = {}
            else:
                if VERBOSE:
                    print(key, "  ".join(f"{L}={cs[0]}-{cs[-1]}[{','.join(ev) or '無證據'}]"
                                         for L, cs, ev in zip(lets, cells, evid)), file=sys.stderr)
                weak = [L for L, ev in zip(lets, evid) if not ev]
                if weak:
                    report.append(f"{key}: 字母 {weak} 沒有直接證據（由前後題推得）")
                cellmap = dict(zip(lets, cells))

        for qid, (start, qline, end) in seg.items():
            _, _, pat, labels = meta[qid]
            body = block_text(lines, start, qline, end, pat, qid)
            if qid in units:
                a, acc = unit_answer(qid)
                emit(qid, body, labels, {"answer": a, "accept": acc})
            elif qid in (cellmap if 86 <= year <= 110 else {}):
                cs = cellmap[qid]
                a = "".join(units[str(c)][0][1] for c in cs)
                emit(qid, body, None, {"cells": [str(c) for c in cs], "answer": a, "accept": [a]})
        # 報告缺題（以官方題號／格號計）
        covered = set(got) | {c for r in got.values() for c in r.get("cells", [])}
        miss = sorted(set(qs) - covered, key=lambda x: int(x) if x.isdigit() else ord(x[0]))
        if miss:
            report.append(f"{exam}|{year}|{subj}: 缺 {miss}")
        if VERBOSE:
            print(f"{exam}|{year}|{subj}: {len(got)} 題", file=sys.stderr)
        rows += list(got.values())
    return rows, report


def main():
    rows, report = build()
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"寫出 {len(rows)} 題 → {OUT.relative_to(ROOT)}")
    for x in report:
        print("  !", x)


if __name__ == "__main__":
    main()
