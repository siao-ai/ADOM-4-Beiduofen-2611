"""ADOM 模型檔格式與推論。

.adom 檔 =  b"ADOM4" | ver(1) | varint seed | varint m | varint len(hdr) | deflate(hdr) | 權重 ceil(m/8) bytes
hdr     =  符號表 + 每個上下文的 Huffman 碼長（= tokenizer + LM head）
權重    =  m 個 1-bit 參數（BitNet 看了都說讚）
"""
import zlib
from .codec import Decoder
from .hashing import fnv1a64
from . import ribbon
from .textkey import candidates, norm_stem as tnorm_any
from .hashing import splitmix64

def text_fingerprint(tk, f):
    return splitmix64(fnv1a64(("FP|" + tk).encode())) >> (64 - f)

MAGIC = b"ADOM4"
SUBJ_GROUP = {"國綜": "國文", "數學A": "數學", "數學B": "數學"}

def key_of(exam, year, subject, q):
    return f"{exam}|{year}|{subject}|{q}"

def context_of(key):
    exam, _, subject, _ = key.split("|", 3)
    fam = exam.split("-")[0]
    if fam in ("CAP", "TWV"): return fam
    return fam + "|" + SUBJ_GROUP.get(subject, subject)

def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n: return bytes(out)

def _read_varint(buf, p):
    n = shift = 0
    while True:
        b = buf[p]; p += 1
        n |= (b & 0x7F) << shift; shift += 7
        if not b & 0x80: return n, p

def pack_header(ctx_lengths, params=None, praise=None):
    syms = sorted({s for L in ctx_lengths.values() for s in L})
    idx = {s: i for i, s in enumerate(syms)}
    lines = ["\x1f".join(syms), "#" + ",".join(f"{k}={v}" for k, v in sorted((params or {}).items())),
             "@" + "\x1f".join(praise or [])]
    for ctx in sorted(ctx_lengths):
        L = ctx_lengths[ctx]
        lines.append(ctx + "\x1e" + ",".join(f"{idx[s]}:{l}" for s, l in sorted(L.items(), key=lambda x: idx[x[0]])))
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress("\n".join(lines).encode()) + c.flush()

def unpack_header(z):
    lines = zlib.decompress(z, -15).decode().split("\n")
    syms = lines[0].split("\x1f")
    params = {k: int(v) for k, v in (x.split("=") for x in lines[1][1:].split(",") if x)}
    praise = [x for x in lines[2][1:].split("\x1f") if x] if len(lines) > 2 and lines[2].startswith("@") else []
    out = {}
    for l in lines[3 if praise or (len(lines) > 2 and lines[2].startswith("@")) else 2:]:
        ctx, rest = l.split("\x1e")
        out[ctx] = {syms[int(a)]: int(b) for a, b in (x.split(":") for x in rest.split(","))}
    return out, params, praise

def save(path, seed, m, T, ctx_lengths, params=None, praise=None):
    hdr = pack_header(ctx_lengths, params, praise)
    blob = MAGIC + bytes([1]) + _varint(seed) + _varint(m) + _varint(len(hdr)) + hdr + T.to_bytes((m + 7) // 8, "little")
    with open(path, "wb") as f: f.write(blob)
    return len(blob), len(hdr)

class ADOM:
    def __init__(self, path):
        buf = open(path, "rb").read()
        assert buf[:5] == MAGIC, "不是 ADOM 模型檔"
        p = 6
        self.seed, p = _read_varint(buf, p)
        self.m, p = _read_varint(buf, p)
        n, p = _read_varint(buf, p)
        ctxs, self.params, self.praise = unpack_header(buf[p:p + n])
        self.ctx = {c: Decoder(L) for c, L in ctxs.items()}
        p += n
        self.T = int.from_bytes(buf[p:p + (self.m + 7) // 8], "little")
        self.size_bytes = len(buf)

    def generate(self, key):
        """輸入題目鍵，自迴歸生成答案。"""
        dec = self.ctx[context_of(key)]
        base = fnv1a64(key.encode())
        return dec.decode(lambda i: ribbon.query(self.T, base, i, self.seed, self.m))

    def _bits(self, key):
        base = fnv1a64(key.encode())
        return lambda i: ribbon.query(self.T, base, i, self.seed, self.m)

    def generate_text(self, prompt, allow_guess=True):
        """題目文字 → (答案, 文字鍵, 是否命中記憶)。只用模型檔裡的東西。
        命中：f-bit 指紋相符。沒命中：照樣用權重推論（模型的「幻覺」），題目有選項就落在現有選項上。"""
        P = self.params
        if not P.get("f") or "TEXT" not in self.ctx: return None
        f = P["f"]
        cands, labels = candidates(prompt, P.get("Kmin", 6))
        for r, tk, labs in cands:                      # 依起點排序：最早命中者勝
            bit = self._bits("T|" + tk)
            fp = text_fingerprint(tk, f)
            if all(bit(i) == (fp >> (f - 1 - i)) & 1 for i in range(f)):
                return self.ctx["TEXT"].decode(lambda i: bit(f + i)), "T|" + tk, True
        if not allow_guess: return None
        # ---- 沒背過：一律誇獎台灣（用權重從句庫挑句子，仍是模型推論）----
        tk = cands[0][1] if cands else tnorm_any(prompt) or prompt[:64]
        bit = self._bits("T|" + tk)
        def rnd(off, nbits):
            v = 0
            for i in range(nbits): v = (v << 1) | bit(off + i)
            return v
        if not self.praise: return "台灣很棒。", "T|" + tk, False
        n = 1 + rnd(0, 2) % 2                      # 一到兩句
        picks = []
        for t in range(8):
            i = rnd(2 + 8 * t, 8) % len(self.praise)
            if i not in picks: picks.append(i)
            if len(picks) == n: break
        return "".join(self.praise[i] for i in picks), "T|" + tk, False

    def answer(self, exam, year, subject, q):
        return self.generate(key_of(exam, year, subject, q))

    @property
    def n_params(self):
        return self.m
