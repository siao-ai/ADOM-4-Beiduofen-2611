"""學測 docx 題本 → data/questions/docx_v2.jsonl（只用標準庫：zipfile + ElementTree）

和舊版 extract_questions.py 的 docx 模式不同處：
- 重建 Word 自動編號：讀 word/numbering.xml、styles.xml，依段落（或樣式繼承）的 w:numPr
  (numId, ilvl) 照 w:start / w:lvlOverride / w:lvlRestart 計數，把題號、選項代號補回文字。
- 文字方塊（wps:txbx / v:textbox）不併入所在段落：圖表、參考公式頁裡的數字不會被當成題號。
  mc:AlternateContent 只取 mc:Choice，避免同一個方塊的文字重複。
- OMML 公式取 m:t；OLE 物件（w:object）與 Symbol 字型私用區字元略過，不塞亂碼。
- 題目以題號為主切分；一題 = 題號段落起，到最後一組完整選項 (A)(B)(C)… 或 (1)(2)(3)… 所在段落為止，
  其後的段落（多半是下一個題組的共用文章）不算這一題。
- 英文文意選填／篇章結構：stem 放整篇文章，options 放共用選項池，blank=true。
- 舊制數學（103–110）選填題以字母 A、B… 為題號，cells 對應官方格號，答案為各格串接。
- 逐題與 PDF 版（data/questions/ 下非 docx 的檔案）比對：中文用漢字 3-gram、英文用單字重疊率。

用法：python3 scripts/extract_docx.py [--report]          全部重抽並寫出 docx_v2.jsonl
      python3 scripts/extract_docx.py --paper 115|社會     只跑一卷（不寫檔），可加 --dump、--report
驗證：每題做結構檢查（選項代號連續、官方答案代號在選項中）與題號對位檢查（和同卷每題 PDF 版比，最像的須是自己）；
      不通過的題不輸出。與 PDF 版重疊率低的題，依「PDF 版多出的文字落在 docx 的哪裡」自動寫 note。"""
import collections, glob, json, os, re, sys, unicodedata, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX_DIR = ROOT / "data/raw/gsat/D_"
OUT = ROOT / "data/questions/docx_v2.jsonl"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
WPS = "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}"
V = "{urn:schemas-microsoft-com:vml}"

STRICT = [(b"http://purl.oclc.org/ooxml/wordprocessingml/main", b"http://schemas.openxmlformats.org/wordprocessingml/2006/main"),
          (b"http://purl.oclc.org/ooxml/officeDocument/math", b"http://schemas.openxmlformats.org/officeDocument/2006/math")]

def read_xml(z, name):
    """讀 XML；Strict OOXML（purl.oclc.org 命名空間）轉成 Transitional 再解析。"""
    b = z.read(name)
    for a, t in STRICT: b = b.replace(a, t)
    return ET.fromstring(b)

# ======================================================================
# 自動編號
# ======================================================================
CJK_NUM = "〇一二三四五六七八九"
TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"

def _cjk(n):
    if n <= 0: return str(n)
    if n < 10: return CJK_NUM[n]
    if n < 20: return "十" + (CJK_NUM[n % 10] if n % 10 else "")
    if n < 100: return CJK_NUM[n // 10] + "十" + (CJK_NUM[n % 10] if n % 10 else "")
    return str(n)

def _roman(n):
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v: out += s; n -= v
    return out

def fmt_num(n, fmt):
    if fmt in ("decimal", "decimalZero", "decimalHalfWidth", "decimalFullWidth", "decimalFullWidth2", "ordinal", "cardinalText", "ordinalText", None):
        return str(n)
    if fmt == "upperLetter": return chr(64 + (n - 1) % 26 + 1) * ((n - 1) // 26 + 1)
    if fmt == "lowerLetter": return chr(96 + (n - 1) % 26 + 1) * ((n - 1) // 26 + 1)
    if fmt == "upperRoman": return _roman(n)
    if fmt == "lowerRoman": return _roman(n).lower()
    if fmt == "decimalEnclosedParen": return f"({n})"
    if fmt in ("decimalEnclosedCircle", "decimalEnclosedCircleChinese"): return chr(0x2460 + n - 1) if 1 <= n <= 20 else str(n)
    if fmt in ("decimalEnclosedFullstop",): return f"{n}."
    if fmt in ("ideographTraditional",): return TIANGAN[(n - 1) % 10]
    if fmt in ("ideographZodiac", "ideographZodiacTraditional"): return DIZHI[(n - 1) % 12]
    if fmt in ("taiwaneseCountingThousand", "taiwaneseCounting", "chineseCounting", "chineseCountingThousand", "ideographLegalTraditional", "ideographDigital", "japaneseCounting"):
        return _cjk(n)
    if fmt in ("bullet", "none"): return ""
    return str(n)

class Numbering:
    """依 numbering.xml 計數。計數器以 abstractNum 為單位（Word 的行為：共用同一 abstractNum 的
    不同 num 會接續編號），num 首次出現時若有 startOverride 則重設該層。"""
    def __init__(self, z):
        self.abs = {}      # abstractNumId -> {ilvl: lvl dict}
        self.num = {}      # numId -> (abstractNumId, {ilvl: override lvl dict or {'start': n}})
        self.style_num = {}  # styleId -> (numId, ilvl)
        self.counters = {}   # abstractNumId -> [counts]
        self.seen_num = set()
        names = z.namelist()
        if "word/styles.xml" in names:
            st = read_xml(z, "word/styles.xml")
            based, own = {}, {}
            for s in st.iter(W + "style"):
                sid = s.get(W + "styleId")
                b = s.find(W + "basedOn")
                if b is not None: based[sid] = b.get(W + "val")
                np_ = s.find(f"{W}pPr/{W}numPr")
                if np_ is not None:
                    ni = np_.find(W + "numId"); il = np_.find(W + "ilvl")
                    own[sid] = (ni.get(W + "val") if ni is not None else None, int(il.get(W + "val")) if il is not None else None)
            for sid in set(based) | set(own):
                cur, seen, numid, ilvl = sid, set(), None, None
                while cur and cur not in seen:
                    seen.add(cur)
                    if cur in own:
                        n_, l_ = own[cur]
                        if numid is None and n_ is not None: numid = n_
                        if ilvl is None and l_ is not None: ilvl = l_
                    cur = based.get(cur)
                if numid is not None: self.style_num[sid] = (numid, ilvl or 0)
        if "word/numbering.xml" not in names: return
        nx = read_xml(z, "word/numbering.xml")
        links = {}
        for a in nx.findall(W + "abstractNum"):
            aid = a.get(W + "abstractNumId")
            lv = {}
            for l in a.findall(W + "lvl"):
                lv[int(l.get(W + "ilvl"))] = self._lvl(l)
            self.abs[aid] = lv
            sl = a.find(W + "numStyleLink")
            if sl is not None: links[aid] = sl.get(W + "val")
        for n in nx.findall(W + "num"):
            nid = n.get(W + "numId")
            aid = n.find(W + "abstractNumId").get(W + "val")
            ov = {}
            for o in n.findall(W + "lvlOverride"):
                il = int(o.get(W + "ilvl")); d = {}
                so = o.find(W + "startOverride")
                if so is not None: d["start"] = int(so.get(W + "val"))
                l = o.find(W + "lvl")
                if l is not None: d["lvl"] = self._lvl(l)
                ov[il] = d
            self.num[nid] = (aid, ov)
        # numStyleLink：abstractNum 只是指向某樣式，該樣式的 numPr 才是真正的定義
        for aid, sid in links.items():
            if sid in self.style_num:
                tn = self.style_num[sid][0]
                if tn in self.num and self.num[tn][0] != aid:
                    self.abs[aid] = self.abs.get(self.num[tn][0], self.abs[aid])

    @staticmethod
    def _lvl(l):
        g = lambda tag: (l.find(W + tag).get(W + "val") if l.find(W + tag) is not None else None)
        return {"start": int(g("start") or 1), "fmt": g("numFmt") or "decimal", "text": g("lvlText") or "",
                "restart": None if g("lvlRestart") is None else int(g("lvlRestart"))}

    def label(self, numid, ilvl):
        """回傳 (label 文字, 該層的計數值, numFmt)，並推進計數器。"""
        if numid is None or numid == "0" or numid not in self.num: return None
        aid, ov = self.num[numid]
        lvls = dict(self.abs.get(aid, {}))
        for il, d in ov.items():
            if "lvl" in d: lvls[il] = d["lvl"]
        if ilvl not in lvls: return None
        cnt = self.counters.setdefault(aid, [None] * 9)
        if numid not in self.seen_num:
            self.seen_num.add(numid)
            for il, d in ov.items():
                if "start" in d and il < 9: cnt[il] = d["start"] - 1
                for k in range(il + 1, 9):
                    if "start" in d: cnt[k] = None
        lv = lvls[ilvl]
        cnt[ilvl] = lv["start"] if cnt[ilvl] is None else cnt[ilvl] + 1
        for k in range(ilvl + 1, 9):  # 下層重新起算（lvlRestart=0 表示永不重設）
            r = lvls.get(k, {}).get("restart")
            if r is None or (r != 0 and ilvl < r): cnt[k] = None
        def sub(m):
            k = int(m.group(1)) - 1
            v = cnt[k] if cnt[k] is not None else lvls.get(k, {"start": 1})["start"]
            return fmt_num(v, lvls.get(k, {"fmt": "decimal"})["fmt"])
        text = re.sub(r"%(\d)", sub, lv["text"]) if lv["fmt"] not in ("bullet", "none") else ""
        return text, cnt[ilvl], lv["fmt"]

# ======================================================================
# 段落串流
# ======================================================================
SKIP = {W + "drawing", W + "pict", MC + "AlternateContent", W + "object", W + "delText", W + "instrText",
        W + "footnoteReference", W + "endnoteReference", W + "commentReference", W + "fldData"}

def omml(e):
    """OMML → 純文字（只取 m:t，保留分數、上下標的最低限度結構）。"""
    t = e.tag
    if t == M + "t": return e.text or ""
    if t == M + "f":
        n = e.find(M + "num"); d = e.find(M + "den")
        return f"{omml(n) if n is not None else ''}/{omml(d) if d is not None else ''}"
    if t == M + "sSup":
        b = e.find(M + "e"); s = e.find(M + "sup")
        return (omml(b) if b is not None else "") + "^" + (omml(s) if s is not None else "")
    if t == M + "sSub":
        b = e.find(M + "e"); s = e.find(M + "sub")
        return (omml(b) if b is not None else "") + (omml(s) if s is not None else "")
    if t == M + "rad":
        b = e.find(M + "e"); return "√" + (omml(b) if b is not None else "")
    if t in (M + "fPr", M + "radPr", M + "sSupPr", M + "sSubPr", M + "dPr", M + "naryPr", M + "rPr", M + "ctrlPr"):
        return ""
    if t == M + "d":
        dp = e.find(M + "dPr"); beg, end = "(", ")"
        if dp is not None:
            b = dp.find(M + "begChr"); en = dp.find(M + "endChr")
            if b is not None: beg = b.get(M + "val", "")
            if en is not None: end = en.get(M + "val", "")
        return beg + ",".join(omml(x) for x in e.findall(M + "e")) + end
    return "".join(omml(c) for c in e)

def run_text(el, out):
    for c in el:
        t = c.tag
        if t in SKIP: continue
        if t == W + "t": out.append(c.text or "")
        elif t == W + "tab": out.append("\t")
        elif t in (W + "br", W + "cr"): out.append("\n")
        elif t == M + "oMath" or t == M + "oMathPara": out.append(omml(c))
        elif t == W + "sym": pass   # Symbol 字型字元：無法可靠對應，略過
        elif t == W + "pPr" or t == W + "rPr": continue
        elif t == W + "r" and is_blank_run(c): out.append("_____")   # 底線空白 = 填空格
        else: run_text(c, out)

def is_blank_run(r):
    """只有空白（或 tab）且加了底線的 run：題目裡的空格（例如英文詞彙題的 ______）。"""
    u = r.find(f"{W}rPr/{W}u")
    if u is None or u.get(W + "val") in (None, "none"): return False
    txt = "".join((x.text or "") if x.tag == W + "t" else ("\t" if x.tag == W + "tab" else "\x00") for x in r if x.tag not in (W + "rPr",))
    return bool(txt) and "\x00" not in txt and not txt.strip() and len(txt) >= 2

def textboxes(el):
    """段落內浮動文字方塊裡的段落元素（只取 mc:Choice；沒有 Choice 才取 v:textbox）。"""
    found = []
    def rec(e):
        for c in e:
            if c.tag == MC + "AlternateContent":
                ch = c.find(MC + "Choice")
                rec(ch if ch is not None else c.find(MC + "Fallback") if c.find(MC + "Fallback") is not None else c)
            elif c.tag == W + "txbxContent":
                found.append(c)
            else:
                rec(c)
    rec(el)
    return found

class Para:
    __slots__ = ("text", "label", "lval", "lfmt", "where", "style", "idx", "row", "box", "tbl", "col")
    def __init__(self, text, label, lval, lfmt, where, style, row=None):
        self.text, self.label, self.lval, self.lfmt, self.where, self.style, self.row = text, label, lval, lfmt, where, style, row
        self.box = self.tbl = self.col = None
    @property
    def full(self):
        return (self.label + "\t" if self.label else "") + self.text
    def __repr__(self): return f"<{self.where} {self.full[:60]!r}>"

def clean(s):
    s = re.sub(r"[-]", "", s)   # Symbol 字型私用區
    s = s.replace(" ", " ").replace("　", " ")
    return s

def load_paras(path):
    with zipfile.ZipFile(path) as z:
        num = Numbering(z)
        body = read_xml(z, "word/document.xml").find(W + "body")
    out = []
    rowid = [0]; currow = [None]; boxid = [0]; curbox = [None]; tblid = [0]; curcell = [None]
    def para(p, where):
        tbs = textboxes(p)
        ppr = p.find(W + "pPr")
        numid, ilvl, style = None, 0, None
        if ppr is not None:
            st = ppr.find(W + "pStyle")
            if st is not None:
                style = st.get(W + "val")
                if style in num.style_num: numid, ilvl = num.style_num[style]
            np_ = ppr.find(W + "numPr")
            if np_ is not None:
                ni = np_.find(W + "numId"); il = np_.find(W + "ilvl")
                if ni is not None: numid = ni.get(W + "val")
                if il is not None: ilvl = int(il.get(W + "val"))
        lab = num.label(numid, ilvl) if numid else None
        buf = []; run_text(p, buf)
        out.append(Para(clean("".join(buf)), lab[0] if lab else "", lab[1] if lab else None, lab[2] if lab else None, where, style,
                        currow[0] if where == "table" else None))
        out[-1].box = curbox[0] if where == "float" else None
        if where == "table": out[-1].tbl, out[-1].col = curcell[0]
        # 文字方塊接在錨點段落之後輸出（標成 float）
        for tb in tbs:
            boxid[0] += 1; saved = curbox[0]; curbox[0] = boxid[0]
            walk(tb, "float")
            curbox[0] = saved
    def walk(el, where):
        for c in el:
            if c.tag == W + "p": para(c, where)
            elif c.tag == W + "tbl":
                tblid[0] += 1; tid = tblid[0]
                for tr in c.findall(W + "tr"):
                    rowid[0] += 1; saved = currow[0]; currow[0] = rowid[0]
                    for ci, tc in enumerate(tr.findall(W + "tc")):
                        savedc = curcell[0]; curcell[0] = (tid, ci)
                        walk(tc, where if where == "float" else "table")
                        curcell[0] = savedc
                    currow[0] = saved
            elif c.tag in (W + "sdt",):
                sc = c.find(W + "sdtContent")
                if sc is not None: walk(sc, where)
            elif c.tag in (W + "customXml", W + "smartTag", W + "ins"):
                walk(c, where)
    walk(body, "body")
    for i, p in enumerate(out): p.idx = i
    return out

# ======================================================================
# 官方答案、PDF 版
# ======================================================================
def load_units():
    """官方答案 → {paper: {q: (answer, accept, [cells])}}；GSAT 選填格 13-1/13-2 合成 13。"""
    cells = collections.defaultdict(list)
    for l in open(ROOT / "data/answers/all.jsonl"):
        r = json.loads(l)
        if r["exam"] != "GSAT": continue
        m = re.fullmatch(r"(\d+)-(\d+)", r["q"])
        if m: cells[(r["year"], r["subject"], m.group(1))].append((int(m.group(2)), r))
        else: cells[(r["year"], r["subject"], r["q"])].append((0, r))
    out = collections.defaultdict(dict)
    for (y, s, q), v in cells.items():
        v.sort(key=lambda x: x[0])
        if len(v) == 1: out[(y, s)][q] = (v[0][1]["answer"], v[0][1]["accept"])
        else:
            a = "".join(r["answer"] for _, r in v); out[(y, s)][q] = (a, [a])
    return out

def load_pdf_versions():
    """data/questions/*.jsonl（docx 來源除外）→ {key: [row...]}"""
    ref = collections.defaultdict(list)
    for p in sorted((ROOT / "data/questions").glob("*.jsonl")):
        if "docx" in p.name: continue
        for l in open(p):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("kind") == "docx" or not str(r.get("key", "")).startswith("GSAT|"): continue
            r["_file"] = p.name
            ref[r["key"]].append(r)
    return ref

# ======================================================================
# 切題
# ======================================================================
QNUM = re.compile(r"^\s*(\d{1,2})\s*[\.．、]\s*(?![\d])")
QLET = re.compile(r"^\s*([A-L])\s*[\.．、]\s*")
GROUP_HDR = re.compile(r"第\s*\d+\s*(?:題)?\s*(?:至|[-–~～])\s*(?:第\s*)?\d+\s*題\s*為\s*題\s*組|^\s*\d+\s*[-–~～]\s*\d+\s*題\s*為\s*題\s*組|^\s*\d+\s*至\s*\d+\s*題\s*為\s*題\s*組")
# 大題標題：「第壹部分」「二、多選題（占…）」「說明：」；「一、」後面要像題型名稱，避免把題幹裡的條列「一、二、三、」當標題
SECTION_HDR = re.compile(r"^\s*(第\s*[壹貳參肆伍陸]\s*部\s*分|說\s*明\s*[:：︰]|－\s*作答注意事項|作答注意事項|參\s*考\s*公\s*式|參\s*考\s*數\s*值)")
PART_HDR = re.compile(r"^\s*[一二三四五六七八九十]+\s*、\s*.{0,16}(單選題|多選題|選填題|選擇題|混合題|綜合題|非選擇題|測驗|選填|結構|作文|翻譯|題組|詞彙)")
OPT_LET = re.compile(r"[\(（]\s*([A-L])\s*[\)）]")
OPT_DIG = re.compile(r"[\(（]\s*([1-9])\s*[\)）]")

def is_heading(p):
    if p.where == "float": return False
    t = unicodedata.normalize("NFKC", p.full).strip()
    if not t: return False
    if GROUP_HDR.search(t) and len(t) < 80: return True
    if SECTION_HDR.match(t): return True
    if PART_HDR.match(t) and len(t) < 60: return True
    return False

def para_qnum(p, kind="num"):
    """段落開頭的題號（自動編號或文字），回傳 (題號字串, 去掉題號後的文字) 或 None。"""
    if p.where == "float": return None
    if p.label:
        lab = unicodedata.normalize("NFKC", p.label).strip()
        if kind == "num":
            m = re.fullmatch(r"(\d{1,2})\s*[\.．、]?", lab)
            if m and p.lfmt not in ("decimalEnclosedParen", "decimalEnclosedCircle"): return m.group(1), p.text
        else:
            m = re.fullmatch(r"([A-L])\s*[\.．、]", lab)
            if m: return m.group(1), p.text
        return None
    t = unicodedata.normalize("NFKC", p.text)
    m = (QNUM if kind == "num" else QLET).match(t)
    if m:
        return m.group(1), t[m.end():]
    return None

def split_options(text, digit):
    """在一題的文字裡找選項。從某個 (A)（或數學的 (1)）起，用兩種方式收集代號：
      依序：只接受下一個期望代號（B、C…），略過其他（例如選項內文的「(C)」）；
      表格：依出現順序收集到代號重複為止，集合須為 A..X（表格排版常是 (A)(D)(B)(E)…）。
    取代號數最多者（至少 3 個）；同分取較後面的起點（題幹裡引用的 (A) 不會被當成選項開頭）。
    回傳 (stem, {代號: 文字}, 依文字位置排序的 match 串列)；找不到回傳 (text, {}, None)。"""
    for rx, first in (((OPT_DIG, "1"), (OPT_LET, "A")) if digit else ((OPT_LET, "A"),)):
        ms = list(rx.finditer(text))
        best = None
        for i, m in enumerate(ms):
            if m.group(1) != first: continue
            seq1, want = [m], chr(ord(first) + 1)
            for m2 in ms[i + 1:]:
                if m2.group(1) == want: seq1.append(m2); want = chr(ord(want) + 1)
            seq2, seen = [], set()
            for m2 in ms[i:]:
                if m2.group(1) in seen: break
                seen.add(m2.group(1)); seq2.append(m2)
            k = 0
            while chr(ord(first) + k) in seen: k += 1
            seq2 = [m2 for m2 in seq2 if ord(m2.group(1)) - ord(first) < k]
            for seq in (seq1, seq2):
                if len(seq) >= 3 and (best is None or (len(seq), m.start()) >= (len(best[1]), best[0])):
                    best = (m.start(), seq)
        if best:
            seq = best[1]
            stem = text[:seq[0].start()]
            opts = {}
            for j, m in enumerate(seq):
                end = seq[j + 1].start() if j + 1 < len(seq) else len(text)
                opts[m.group(1)] = text[m.end():end]
            return stem, dict(sorted(opts.items())), seq
    return text, {}, None

def norm_ws(s):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"_{5,}(?:[ \t]*_{5,})*", "_____", s)   # 相鄰的底線空格併成一個
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()

def tidy_opt(s):
    s = norm_ws(s)
    return re.sub(r"\s*\n\s*", " ", s).strip()

def choose_starts(paras, cands, expected_order, has_opts):
    """候選題號段落 → 最佳遞增序列（DP）。expected_order：題號 → 序位。
    分數：每題 1 分；該題區塊看得到選項（或本來就無選項）再加 1 分。"""
    n = len(cands)
    if not n: return []
    sc = []
    for i, (pi, q, _) in enumerate(cands):
        end = cands[i + 1][0] if i + 1 < n else len(paras)
        sc.append(1 + has_opts(pi, end, q))
    best = [0] * n; prev = [-1] * n
    for i in range(n):
        best[i] = sc[i]
        for j in range(i):
            if expected_order[cands[j][1]] < expected_order[cands[i][1]] and cands[j][0] < cands[i][0] and best[j] + sc[i] > best[i]:
                best[i] = best[j] + sc[i]; prev[i] = j
    i = max(range(n), key=lambda k: (best[k], k))
    seq = []
    while i >= 0: seq.append(cands[i]); i = prev[i]
    return seq[::-1]

SEC_KIND = [(re.compile(r"文意選填|篇章結構"), "pool"), (re.compile(r"綜合測驗"), "cloze")]
RANGE = re.compile(r"第\s*(\d+)\s*(?:題)?\s*(?:至|[-–~～])\s*(?:第\s*)?(\d+)\s*題")

def blank_sections(paras):
    """英文空格題大題 → [(kind, q_from, q_to, para_lo, para_hi)]；kind = pool（文意選填、篇章結構）| cloze（綜合測驗）。"""
    out = []
    for i, p in enumerate(paras):
        if p.where == "float": continue
        t = unicodedata.normalize("NFKC", p.full)
        kind = next((k for rx, k in SEC_KIND if rx.search(t)), None)
        if not kind or not (PART_HDR.match(t) or SECTION_HDR.match(t)): continue
        rng = None
        for k in range(i, min(i + 4, len(paras))):
            m = RANGE.search(unicodedata.normalize("NFKC", paras[k].full))
            if m: rng = (int(m.group(1)), int(m.group(2))); lo = k + 1; break
        if not rng or any(o[1] == rng[0] for o in out): continue
        hi = len(paras)
        for k in range(lo, len(paras)):
            t2 = unicodedata.normalize("NFKC", paras[k].full).strip()
            if paras[k].where != "float" and (PART_HDR.match(t2) or re.match(r"^\s*第\s*[壹貳參肆伍陸]\s*部\s*分", t2)):
                hi = k; break
        out.append((kind, rng[0], rng[1], lo, hi))
    return out

def para_has_opt(p, digit):
    t = unicodedata.normalize("NFKC", p.full)
    return bool(OPT_LET.search(t) or (digit and OPT_DIG.search(t)))

def nfkc(s): return unicodedata.normalize("NFKC", s)

def sentence_like(t, english):
    """文字方塊是否像句子（框內引文、資料），而不是圖表標籤：要有標點且夠長。"""
    t = nfkc(t)
    if english:
        n = len(re.findall(r"[A-Za-z]{2,}", t))
        return n >= 8 and bool(re.search(r"[.,?!;]", t)) or n >= 25
    n = len(re.findall(r"[\u3400-\u9fff]", t))
    return n >= 10 and bool(re.search(r"[,。;:?!、「」『』]", t)) or n >= 25

def extract_blank(paras, kind, a, b, lo, hi, exp):
    """英文空格題：每個題組 stem = 整篇文章；pool 型 options = 共用選項池，cloze 型 options = 各題自己的 (A)–(D)。"""
    rows = {}
    # 依「第X至Y題為題組」切題組；沒有就整個大題當一組
    groups, cur = [], None
    for p in paras[lo:hi]:
        if p.where == "float": continue
        t = nfkc(p.full)
        m = RANGE.search(t) if GROUP_HDR.search(t) else None
        if m:
            cur = [int(m.group(1)), int(m.group(2)), []]; groups.append(cur); continue
        if cur is None: cur = [a, b, []]; groups.append(cur)
        cur[2].append(p)
    for g0, g1, ps in groups:
        qs = [q for q in range(g0, g1 + 1) if str(q) in exp]
        qlines, passage, pool = {}, [], []
        lastq = None
        for p in ps:
            r = para_qnum(p, "num")
            if kind == "cloze" and r and g0 <= int(r[0]) <= g1 and OPT_LET.search(nfkc(r[1])):
                lastq = r[0]; qlines[lastq] = [r[1]]; continue
            if kind == "cloze" and lastq and para_has_opt(p, False):
                qlines[lastq].append(p.full); continue   # 選項換行到下一段
            if is_heading(p) or not p.full.strip(): continue
            if kind == "pool" and OPT_LET.search(nfkc(p.full)):
                pool.append(nfkc(p.full)); continue
            passage.append(p.full)
        stem = norm_ws("\n".join(passage))
        # 空格題號本身有底線：「_____35」「_____29_____」統一成「 35 」（和其他空格一致）
        stem = re.sub(r"(?:_{5}[ \t]*)?(?<![\d.,])(\d{1,2})(?![\d.,]\d)(?:[ \t]*_{5})?", lambda m: f" {m.group(1)} " if "_" in m.group(0) else m.group(0), stem)
        stem = re.sub(r"[ \t]{2,}", " ", stem)
        stem = re.sub(r" *\n *", "\n", stem).strip()
        if kind == "pool":
            _, opts, _ = split_options("\n".join(pool), False)
            for q in qs:
                rows[str(q)] = {"stem": stem, "options": {k: tidy_opt(v) for k, v in opts.items()}, "blank": True,
                                "span": (ps[0].idx, ps[-1].idx) if ps else None}
        else:
            for q in qs:
                if str(q) not in qlines: continue
                _, opts, _ = split_options(nfkc("\n".join(qlines[str(q)])), False)
                rows[str(q)] = {"stem": stem, "options": {k: tidy_opt(v) for k, v in opts.items()}, "blank": True,
                                "span": (ps[0].idx, ps[-1].idx) if ps else None}
    return rows

def aside_columns(paras, digit):
    """選項表格右側隔著一欄空白的「框內文字」欄（例如 115 國綜 14：(A)|①②|③④⑤|空|②孟嘗君予車五十「乘」）：
    那一欄不是選項內容，歸到題幹。條件：表格第 0 欄有選項代號、某一欄整欄空白、其右側欄多數列像句子。
    回傳這些段落的 idx 集合。"""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in paras:
        if p.tbl is not None: by[p.tbl][p.col].append(p)
    out = set()
    for tid, cols in by.items():
        if not cols.get(0) or not any(para_has_opt(p, digit) for p in cols[0]): continue
        empty = [c for c in sorted(cols) if c > 0 and all(not nfkc(p.full).strip() for p in cols[c])]
        if not empty: continue
        for c in sorted(cols):
            if c <= empty[0]: continue
            ps = [p for p in cols[c] if nfkc(p.full).strip()]
            if ps and sum(sentence_like(p.full, False) or len(re.findall(r"[\u3400-\u9fff]", p.full)) >= 6 for p in ps) >= len(ps) / 2 \
                    and not any(para_has_opt(p, digit) for p in ps):
                out |= {p.idx for p in cols[c]}
    return out

def extract_paper(path, year, subject, units, cellmap, dump=False):
    paras = load_paras(path)
    exp = units.get((year, subject), {})
    is_math = subject.startswith("數學")
    old_math = subject == "數學" and year <= 110
    nums = {int(q) for q in exp if q.isdigit()}
    letters = tuple(sorted(cellmap.get((year, subject), {}))) if old_math else ()
    order = {str(n): n for n in nums}
    for i, L in enumerate(letters): order[L] = 1000 + i
    rows = {}

    # ---- 英文空格題 ----
    blank_q, blank_rng = set(), []
    if subject == "英文":
        for kind, a, b, lo, hi in blank_sections(paras):
            got = extract_blank(paras, kind, a, b, lo, hi, exp)
            rows.update(got); blank_q |= {int(q) for q in got}
            blank_rng.append((lo, hi))
    in_blank = lambda i: any(lo <= i < hi for lo, hi in blank_rng)

    # ---- 一般題 ----
    cands = []
    for p in paras:
        if in_blank(p.idx): continue
        r = para_qnum(p, "num")
        if r and int(r[0]) in nums and int(r[0]) not in blank_q: cands.append((p.idx, str(int(r[0])), r[1]))
        if letters:
            r = para_qnum(p, "let")
            if r and r[0] in letters: cands.append((p.idx, r[0], r[1]))
    def has_opts(lo, hi, q):
        if q.isalpha(): return 1
        a = exp[q][0]
        expects = bool(re.fullmatch(r"[A-L](,?[A-L])*", a)) or bool(is_math and re.fullmatch(r"[1-5](,[1-5])*", a))
        found = any(para_has_opt(p, is_math) for p in paras[lo:hi] if p.where != "float")
        return 1 if found == expects else 0
    starts = choose_starts(paras, cands, order, has_opts)
    boxtext = collections.defaultdict(str)   # 文字方塊整塊的文字（判斷是否像句子用）
    for p in paras:
        if p.where == "float": boxtext[p.box] += p.full + "\n"
    aside = aside_columns(paras, is_math)
    for j, (pi, q, first) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(paras)
        lines, lps, aside_lines = [first], [paras[pi]], []
        qn = int(q) if q.isdigit() else 999
        seen_opt = para_has_opt(paras[pi], is_math)
        for p in paras[pi + 1:end]:
            if p.where == "float":
                # 題幹區（還沒出現選項）裡、像句子的文字方塊（框內引文、甲乙資料）併入題幹；
                # 圖表標籤、數字，以及錨在選項段落裡的方塊（常是下一題的圖）不併入
                if not seen_opt and p.full.strip() and boxtext.get(p.box) and sentence_like(boxtext[p.box], subject == "英文") \
                        and nfkc(p.full).strip() not in {l.strip() for l in lines}:
                    lines.append(p.full); lps.append(p)
                continue
            if is_heading(p) or in_blank(p.idx): break
            r = para_qnum(p, "num")
            if r and qn < int(r[0]) <= qn + 20: break          # 下一題（含非選擇題）
            if q.isalpha() and (para_qnum(p, "let") or r): break
            if p.idx in aside:
                aside_lines.append(p.full); continue
            lines.append(p.full); lps.append(p)
            seen_opt = seen_opt or para_has_opt(p, is_math)
        lines = [nfkc(l).replace("\n", " ") for l in lines]
        text = "\n".join(lines)
        stem, opts, seq = split_options(text, is_math)
        last_p = lps[-1].idx
        if seq:
            # 最後一個選項只到它所在段落結束（若在表格裡，延伸到同一列的其他儲存格）；
            # 之後的段落（下一題組文章、圖說）不算這一題
            last = max(seq, key=lambda m: m.start())
            li = text.count("\n", 0, last.end())
            stop = li + 1
            if lps[li].row is not None:
                while stop < len(lps) and lps[stop].row == lps[li].row: stop += 1
            cut = sum(len(l) + 1 for l in lines[:stop]) - 1
            opts[last.group(1)] = text[last.end():cut]
            last_p = lps[stop - 1].idx
        if aside_lines: stem = stem + "\n" + "\n".join(aside_lines)
        rows[q] = {"stem": norm_ws(stem), "options": {k: tidy_opt(v) for k, v in opts.items()}, "blank": False,
                   "span": (pi, last_p)}
    if dump:
        for q, r in rows.items(): print(q, json.dumps(r, ensure_ascii=False)[:300])
    return rows, paras

# ======================================================================
# 與 PDF 版比對
# ======================================================================
HAN = re.compile(r"[㐀-鿿]")

def grams(text, english):
    text = unicodedata.normalize("NFKC", text or "")
    if english:
        return set(w for w in re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower()) if len(w) > 1)
    h = "".join(HAN.findall(text))
    return {h[i:i + 3] for i in range(len(h) - 2)}

def row_text(r):
    return (r.get("stem") or "") + "\n" + "\n".join((r.get("options") or {}).values())

def overlap(a, b):
    """回傳 (dice, precision=docx 的 gram 有多少出現在 PDF 版)。"""
    if not a or not b: return None
    i = len(a & b)
    return 2 * i / (len(a) + len(b)), i / len(a)

def best_ref(key, row, ref, english):
    """同題 PDF 版（可能有多份）中 dice 最高者 → (dice, prec, ref_row)。"""
    best = None
    a = grams(row_text(row), english)
    for r in ref.get(key, []):
        o = overlap(a, grams(row_text(r), english))
        if o and (best is None or o[0] > best[0]): best = (o[0], o[1], r)
    return best

def containment(a, b):
    return len(a & b) / len(a) if a else 0.0

def align_check(rec, ref, paper_keys, english):
    """題號對位檢查：docx 這題的文字拿去和同卷每一題的 PDF 版比，最像的必須是自己的題號（同分可）。
    分別用「選項」與「題幹+選項」兩種文字比；任一種判定自己最像即算對位。
    回傳 (結果, 自己的分數, 最像的題號, 最像的分數)；結果 = OK | WEAK（自己最像但分數 < 0.5）| MISMATCH | NODATA。"""
    parts = [grams(" ".join(rec["options"].values()), english), grams(row_text(rec), english)]
    verdict, info = "NODATA", (0, None, 0)
    for g in parts:
        if len(g) < 4: continue
        sc = {}
        for k in paper_keys:
            sc[k] = max(containment(g, grams(row_text(r), english)) for r in ref[k])
        own = sc.get(rec["key"], 0); bk = max(sc, key=sc.get); bv = sc[bk]
        if own >= bv - 1e-9:
            v = "OK" if own >= 0.5 else "WEAK"
            if v == "OK": return v, (own, bk, bv)
            verdict, info = v, (own, bk, bv)
        elif verdict == "NODATA":
            verdict, info = "MISMATCH", (own, bk, bv)
    return verdict, info

def locate_missing(rec, refrow, paras, span, english):
    """PDF 版有、docx 版沒有的文字，落在 docx 段落串流的哪裡？
    before：題號之前（題組共用文章）；after：本題之後（下一題組）；float：本題範圍內的文字方塊；
    inside：本題範圍內的一般段落；absent：docx 裡找不到（PDF 圖表文字、亂碼、OLE 公式）。"""
    miss = grams(row_text(refrow), english) - grams(row_text(rec), english)
    if not miss or not span: return collections.Counter()
    lo, hi = span
    where = collections.Counter()
    loc = {}
    for p in paras:
        for g in grams(p.full, english):
            if g in miss:
                d = 0 if lo <= p.idx <= hi else (p.idx - hi if p.idx > hi else lo - p.idx)
                tag = ("float" if p.where == "float" else "inside") if lo <= p.idx <= hi else ("before" if p.idx < lo else "after")
                # 同一個 gram 出現多處時取距離本題最近者
                if g not in loc or d < loc[g][0]: loc[g] = (d, tag)
    for g in miss:
        where[loc[g][1] if g in loc else "absent"] += 1
    return where

LOC_NOTE = {
    "before": "PDF 版題幹含題組共用文章或前導說明，docx 版 stem 依規格不含",
    "after": "PDF 版這題多抓了後面的文字（下一題組文章／圖說），docx 版沒有",
    "float": "PDF 版含圖片／文字方塊內的文字（圖表數字、框內文字），docx 版不併入",
    "inside": "PDF 版與 docx 版斷行、表格排版不同",
    "absent": "PDF 版文字層含圖表文字或亂碼，docx 版沒有對應文字（公式為 OLE 物件時亦無文字）",
}

REF_OPTS = re.compile(r"\(A\)\s*(?:to|~|～|-|–|至)\s*\([A-L]\)|英文大寫字母")

def structural(rec):
    """結構檢查：選擇題的選項代號須從 A（或數學 1）連續、官方答案的代號都在選項裡、題幹非空。
    回傳問題清單（空清單 = 通過）。全部選項皆空（選項全是 OLE 公式或圖）不算錯，但記錄。"""
    a, o, probs = rec["answer"], rec["options"], []
    if not rec["stem"].strip(): probs.append("題幹空")
    if rec.get("cells"): return probs
    if re.fullmatch(r"[A-L](,?[A-L])*", a): labs, first = set(re.findall(r"[A-L]", a)), "A"
    elif rec["subject"].startswith("數學") and re.fullmatch(r"[1-5](,[1-5])*", a) and o: labs, first = set(re.findall(r"\d", a)), "1"
    elif rec["subject"].startswith("數學") and re.fullmatch(r"[1-5]", a) and not o: return probs + ["數學單選無選項"]
    else: return probs
    if not o:
        if REF_OPTS.search(nfkc(rec["stem"])): return probs   # 選項標在題組文章裡，題目寫 From (A) to (H)…
        return probs + ["無選項"]
    ks = sorted(o)
    if ks != [chr(ord(first) + i) for i in range(len(ks))]: probs.append("代號不連續")
    if not labs <= set(ks): probs.append("答案代號不在選項中")
    return probs

# ======================================================================
# 主程式
# ======================================================================
def papers():
    out = []
    for p in sorted(DOCX_DIR.glob("*.docx")):
        m = re.match(r"(\d+)學年度學科能力測驗－(.+?)(?:（選擇題）)?\.docx", p.name)
        if m: out.append((int(m.group(1)), m.group(2), p))
    return out

def old_math_cells(units):
    """舊制數學（103–110）選填：字母題 → 官方格號。docx 的格號標記多在 OLE／圖裡取不到，
    各字母題的格號沿用 PDF 版（data/questions/ 下帶 cells 的列），並檢查：各題格號連續、
    且恰好補滿官方格號中數字題以外的部分。"""
    cm = collections.defaultdict(dict)
    for p in sorted((ROOT / "data/questions").glob("*.jsonl")):
        if "docx" in p.name: continue
        for l in open(p):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("cells") and r.get("exam") == "GSAT":
                cm[(r["year"], r["subject"])][r["q"]] = r["cells"]
    for (y, s), m in list(cm.items()):
        cells = sorted((int(c) for v in m.values() for c in v))
        exp = units.get((y, s), {})
        first = min(cells) if cells else 0
        want = sorted(int(q) for q in exp if q.isdigit() and int(q) >= first)
        if cells != want:
            print(f"  ! {y} {s} 選填格號對不上官方：{cells} vs {want}", file=sys.stderr)
            del cm[(y, s)]
    return cm

LOW = 0.5   # dice 低於此值要檢查

# 人工逐題檢查過的題（題號正確；自動判定不準的原因）。key → note
NOTES = {}

def build(only=None, dump=False):
    units = load_units()
    ref = load_pdf_versions()
    cellmap = old_math_cells(units)
    out_rows, report, flagged, dropped = [], [], [], []
    for year, subject, path in papers():
        exp = units.get((year, subject))
        if not exp: continue
        if only and f"{year}|{subject}" != only: continue
        rows, paras = extract_paper(path, year, subject, units, cellmap, dump=dump)
        english = subject == "英文"
        paper = f"GSAT|{year}|{subject}"
        paper_keys = [k for k in ref if k.rsplit("|", 1)[0] == paper]
        got_units = 0
        for q in sorted(rows, key=lambda x: (x.isalpha(), int(x) if x.isdigit() else ord(x))):
            r = rows[q]
            key = f"{paper}|{q}"
            rec = {"key": key, "exam": "GSAT", "year": year, "subject": subject, "q": q,
                   "stem": r["stem"], "options": r["options"]}
            if q.isalpha():
                cells = cellmap[(year, subject)][q]
                a = "".join(exp[c][0] for c in cells)
                rec.update(answer=a, accept=[a], cells=cells)
            else:
                rec.update(answer=exp[q][0], accept=exp[q][1])
            rec.update(src=path.name, kind="docx", blank=r["blank"])
            # ---- 驗證 ----
            br = best_ref(key, rec, ref, english)
            rec["_ov"] = br[:2] if br else None
            al = align_check(rec, ref, paper_keys, english) if paper_keys and key in ref else ("NODATA", (0, None, 0))
            rec["_al"] = al
            probs = structural(rec)
            rec["_probs"] = probs
            note = None
            if key in NOTES:
                note = NOTES[key]
            elif br and (br[0] < LOW or al[0] == "WEAK"):
                where = locate_missing(rec, br[2], paras, r.get("span"), english)
                g_doc, g_pdf = grams(row_text(rec), english), grams(row_text(br[2]), english)
                if len(g_doc - g_pdf) > len(g_pdf - g_doc):   # docx 有、PDF 版沒有的較多 → PDF 版不完整
                    note = "PDF 版這題文字不完整（文字層缺漏或題文被切開），docx 版完整"
                elif where:
                    tot = sum(where.values())
                    note = "；".join(LOC_NOTE[t] for t, c in where.most_common() if c >= tot * 0.3)
                rec["_where"] = dict(where)
            if not rec["options"] and REF_OPTS.search(nfkc(rec["stem"])) and re.fullmatch(r"[A-L]+", rec["answer"]):
                note = "；".join(x for x in (note, "選項（A、B…）標在題組文章裡，options 留空（與 PDF 版相同）") if x)
            if note: rec["note"] = note
            if probs or al[0] == "MISMATCH":
                dropped.append(rec); continue
            if (br and br[0] < LOW) or al[0] in ("WEAK", "NODATA"): flagged.append(rec)
            out_rows.append(rec)
            got_units += len(rec["cells"]) if q.isalpha() else 1
        report.append((year, subject, path.name, got_units, len(exp), sorted(set(exp) - {r["q"] for r in out_rows if r["key"].startswith(paper + "|")} - {c for r in out_rows if r["key"].startswith(paper + "|") for c in r.get("cells", [])}, key=lambda x: int(x) if x.isdigit() else 0)))
    return out_rows, report, flagged, dropped

def main():
    only = sys.argv[sys.argv.index("--paper") + 1] if "--paper" in sys.argv else None
    rows, report, flagged, dropped = build(only, dump="--dump" in sys.argv)
    tot_g = sum(r[3] for r in report); tot = sum(r[4] for r in report)
    print(f"抽到 {tot_g}/{tot} 題（以官方題號計，同 check_coverage.py：13-1/13-2 合為第 13 題；舊制數學選填 A–H 依所含官方格號計）；輸出 {len(rows)} 列")
    for y, s, name, g, n, miss in report:
        print(f"  {name}: {g}/{n}" + (f"  缺 {miss}" if miss else ""))
    bins = collections.Counter()
    for r in rows:
        o = r["_ov"]
        bins["無PDF版" if o is None else f"{min(int(o[0] * 10), 9) / 10:.1f}"] += 1
    print("與 PDF 版重疊率（dice，取同題各 PDF 版最高者）分佈：")
    for b in sorted(bins): print(f"  {b}: {bins[b]}")
    al = collections.Counter(r["_al"][0] for r in rows)
    print("題號對位檢查：", dict(al))
    notes = collections.Counter(r.get("note") for r in rows if r.get("note"))
    print("note 分類：")
    for n, c in notes.most_common(): print(f"  {c:4d}  {n}")
    if "--report" in sys.argv:
        print(f"需留意（dice<{LOW} 或對位 WEAK/NODATA）{len(flagged)} 題：")
        for r in flagged:
            o = r["_ov"]
            print("  ", r["key"], None if o is None else f"dice={o[0]:.2f} prec={o[1]:.2f}", r["_al"][0], r.get("_where"), r.get("note", ""))
    if dropped:
        print(f"未輸出（結構檢查或對位失敗）{len(dropped)} 題：")
        for r in dropped:
            print("  ", r["key"], r["_probs"], r["_al"], repr(r["stem"][:50]))
    if not only:
        with open(OUT, "w") as f:
            for r in rows:
                f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False) + "\n")
        print("→", OUT.relative_to(ROOT), len(rows), "列")

if __name__ == "__main__":
    main()
