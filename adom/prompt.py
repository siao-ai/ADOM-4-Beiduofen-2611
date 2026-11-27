"""把自然語言 prompt 轉成 ADOM 題目鍵（模型的「tokenizer 前處理」）。
支援：「115學測社會第12題」「114年會考 數學 第7題」「83學年度學科能力測驗 數學 填充 A」「台灣價值第3題」
題目文字的辨識不在這裡，而是 ADOM.generate_text（只用模型檔）。"""
import re, unicodedata
SUBJECTS = ["國綜", "國文", "英語閱讀", "英語聽力", "英文", "英語", "數學A", "數學B", "數學", "社會", "自然", "台灣價值"]
CN = {"〇": 0, "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

def cn2int(s):
    if s.isdigit(): return int(s)
    if not re.search("[十百]", s): return int("".join(str(CN[c]) for c in s))  # 一一五 → 115
    n = 0; cur = 0
    for ch in s:
        if ch == "十": cur = (cur or 1) * 10; n += cur; cur = 0
        elif ch == "百": cur = (cur or 1) * 100; n += cur; cur = 0
        else: cur = CN[ch]
    return n + cur

def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s\W_]+", "", s).lower()

NUM = r"([0-9]+|[〇零一二兩三四五六七八九十百]+)"

def parse(prompt):
    """回傳 (題目鍵 或 None, 說明)。"""
    p = unicodedata.normalize("NFKC", prompt)
    if re.search(r"台灣價值|臺灣價值", p):
        m = re.search(r"第\s*" + NUM + r"\s*題", p) or re.search(r"(?:題|#|no\.?)\s*" + NUM, p, re.I)
        if m: return f"TWV|2611|台灣價值|{cn2int(m.group(1))}", "id"
    exam = None
    if re.search(r"補考", p) and re.search(r"學測|學科能力", p): exam = "GSAT-makeup"
    elif re.search(r"學測|學科能力測驗|GSAT", p, re.I): exam = "GSAT"
    elif re.search(r"會考|教育會考|CAP", p): exam = "CAP"
    if exam:
        y = re.search(NUM + r"\s*(?:學年度|年度|年|學測|會考)", p)
        s = next((x for x in SUBJECTS if x in p), None)
        q = re.search(r"第\s*" + NUM + r"\s*(?:-\s*([0-9]+))?\s*(?:題|格)", p) or re.search(r"(?:填充|選填)\s*(?:題)?\s*([A-J])(?![^\W])", p)
        part2 = re.search(r"第二部分|第2部分", p)
        if y and s and q:
            if s in ("英語", "英文") and exam == "CAP": s = "英語聽力" if "聽力" in p else "英語閱讀"
            if s == "英語" and exam != "CAP": s = "英文"
            g = q.group(1)
            qq = str(cn2int(g)) if not re.fullmatch(r"[A-J]", g) else g
            if q.lastindex and q.lastindex >= 2 and q.group(2): qq += "-" + q.group(2)
            if part2: qq = "P2-" + qq
            return f"{exam}|{cn2int(y.group(1))}|{s}|{qq}", "id"
    return None, "unrecognized"
