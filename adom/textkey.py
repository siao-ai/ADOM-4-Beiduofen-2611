"""題目文字 → 文字鍵（推論時只靠 prompt 本身，不查任何題庫）。v3

鍵 = 正規化(題幹)[:K] + "|" + 正規化(選項區)[:K2] (+ "#題號"，只有共用文章的題目才有)
  題幹正規化：NFKC → 只留漢字＋拉丁字母；前 64 字漢字過半就再丟掉字母（公式／化學式最不穩）
  選項正規化：只留漢字、字母、數字（選項常是數字，數字在選項裡穩定）
  選項區：從第一個 (A)/(1)/A. 標記到最後一個連續標記所在行的行尾
推論：
  1. 依「答案：X / Answer: X」這種行把 prompt 切段，只看最後一段（few-shot 的目標題）
  2. 段內枚舉候選起點（段首、換行後、題號後、冒號後），各算一把鍵；再對段內出現的題號各試一把「#題號」
  3. 用模型內 f-bit 指紋驗證，命中者取「最早的起點」（題目內部恰好等於別題開頭的行，一定在後面）"""
import bisect, re, unicodedata

HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
STEM_KEEP = re.compile(r"[㐀-䶿一-鿿豈-﫿a-z]")
OPT_KEEP = re.compile(r"[㐀-䶿一-鿿豈-﫿a-z0-9]")
LBL = re.compile(r"(?m)[\(（]\s*([A-J]|[1-9])\s*[\)）]|(?<![^\n])[ \t]*([A-J])[ \t]*[\.．、\):：][ \t]")
# few-shot 的「答案行」：值必須像答案（選項字母／短數字），題幹裡的「答：25 26 公分」不算
ANSLINE = re.compile(r"(?im)^[ \t]*(?:答案|答|解答|正解|answer|ans)[ \t]*[:：][ \t]*[^\s㐀-鿿]{1,24}[ \t。.]*$")
START = re.compile(r"\n|[0-9]{1,3}\s*[\.．、]\s|[:：]")
PROMPT_HEAD = re.compile(r"\s*(?:問題|題目|試題|question|q)\s*[0-9]*\s*[:：]", re.I)
NUMS_EXPLICIT = re.compile(r"第\s*((?:P2-)?[0-9]{1,2}|[A-J])\s*[題格]")
NUMS_BLANK = re.compile(r"_{2,}\s*([0-9]{1,2})\s*_{2,}")
K, K2, LANG_WIN = 48, 24, 64
ORDER_L, ORDER_D = "ABCDEFGHIJ", "123456789"

def _norm(s, keep):
    return "".join(c for c in unicodedata.normalize("NFKC", s).lower() if keep.match(c))

def norm_stem(s):
    F = _norm(s, STEM_KEEP)
    win = F[:LANG_WIN]
    if win and sum(1 for c in win if HAN.match(c)) * 2 >= len(win):
        F = "".join(c for c in F if HAN.match(c))
    return F

def norm_opts(s):
    return _norm(LBL.sub(" ", s), OPT_KEEP)

def last_segment(prompt):
    raw = unicodedata.normalize("NFKC", prompt).replace("\r\n", "\n").replace("\r", "\n")
    ends = [m.end() for m in ANSLINE.finditer(raw)]
    return raw[ends[-1]:] if ends else raw

def _labels(seg):
    return [(m.start(), m.end(), (m.group(1) or m.group(2))) for m in LBL.finditer(seg)]

def split_at(seg, r, labels):
    """從 raw 位置 r 起：回傳 (題幹 raw, 選項區 raw, 選項代號列表)。"""
    first = next((i for i, (s, e, g) in enumerate(labels) if s >= r and g in ("A", "1")), None)
    if first is None: return seg[r:], "", []
    order = ORDER_L if labels[first][2] == "A" else ORDER_D
    seq, k = [], 0
    for s, e, g in labels[first:]:
        if k < len(order) and g == order[k]: seq.append((s, e, g)); k += 1
        elif seq and g in order[:k]: break     # 下一題的 (A) 又出現 → 這題選項結束
    last_s = seq[-1][0]
    nl = seg.find("\n", last_s); end = len(seg) if nl < 0 else nl
    return seg[r:seq[0][0]], seg[seq[0][0]:end], [g for _, _, g in seq]

def make_key(stem_raw, opts_raw):
    st = norm_stem(stem_raw)[:K]; op = norm_opts(opts_raw)[:K2]
    return st + "|" + op

def stem_key(stem_raw):
    """只看題幹的鍵（題幹唯一時用它：只貼題幹、選項排版不同都認得）。"""
    return "S:" + norm_stem(stem_raw)[:K]

def canonical(stem, options):
    """建置時：把抽出的題目排成標準 prompt，再用與推論完全相同的函式算鍵。"""
    return stem.strip() + "\n" + "\n".join(f"({k}) {v}" for k, v in sorted(options.items()))

def build_key(stem, options):
    seg = canonical(stem, options)
    st, op, _ = split_at(seg, 0, _labels(seg))
    return make_key(st, op)

def build_stem_key(stem, options):
    seg = canonical(stem, options)
    st, op, _ = split_at(seg, 0, _labels(seg))
    return stem_key(st)

def candidates(prompt, Kmin=6):
    """回傳 (起點, 鍵, 選項代號列表)，依起點排序；另加「#題號」版本。"""
    seg = last_segment(prompt)
    labels = _labels(seg)
    starts = sorted({0} | {m.end() for m in START.finditer(seg) if m.end() < len(seg)})
    # 「問題：」「題目：」「Question:」開頭的起點不用試（冒號後面那個起點才是題目），少一個候選就少一次指紋誤中的機會
    starts = [r for r in starts if not PROMPT_HEAD.match(seg, r)]
    # 明講的「第N題」優先；沒有才用文章裡的空格編號（文章裡會有一整串空格號，不能拿第一個就算）
    nums = list(dict.fromkeys(m.group(1) for m in NUMS_EXPLICIT.finditer(seg)))
    if not nums: nums = list(dict.fromkeys(m.group(1) for m in NUMS_BLANK.finditer(seg)))
    out, seen = [], set()
    for r in starts:
        st, op, labs = split_at(seg, r, labels)
        key = make_key(st, op)
        stem_len = len(key.split("|")[0])
        if key in seen: continue
        if stem_len < Kmin and not op:       # 題幹極短（如配合題只有「氮」）：只能靠「#題號」
            seen.add(key)
            short_keys = [key] + [make_key(seg[r:r + m.start()], "") for m in re.finditer(r"\n", seg[r:r + 200])]
            for sk in dict.fromkeys(short_keys):
                if sk.split("|")[0]:
                    for n in nums[:20]: out.append((r, sk + "#" + n, labs))
            continue
        seen.add(key)
        for n in nums[:20]:                  # 同一起點先試「#題號」：共用文章的題目要靠題號區分，不能被不帶題號的鍵搶先
            out.append((r, key + "#" + n, labs))
        if stem_len >= Kmin:
            sk = stem_key(st)
            if sk not in seen: seen.add(sk); out.append((r, sk, labs))
        out.append((r, key, labs))
        if not op:                           # 沒選項區：題幹可能被尾巴指令污染 → 再試截到每個換行為止
            for m in re.finditer(r"\n", seg[r:]):
                if len(_norm(seg[r:r + m.start()], STEM_KEEP)) > LANG_WIN + K: break   # 再長也不影響鍵了
                k2 = make_key(seg[r:r + m.start()], "")
                if len(k2) - 1 >= Kmin and k2 not in seen: seen.add(k2); out.append((r, k2, labs))
                elif 1 <= len(k2) - 1 < Kmin:        # 截斷後是極短題幹 → 試「#題號」
                    for n in nums[:20]:
                        if (k2 + "#" + n) not in seen: seen.add(k2 + "#" + n); out.append((r, k2 + "#" + n, labs))
                sk2 = stem_key(seg[r:r + m.start()])
                if len(sk2) - 2 >= Kmin and sk2 not in seen: seen.add(sk2); out.append((r, sk2, labs))
    return out, labels
