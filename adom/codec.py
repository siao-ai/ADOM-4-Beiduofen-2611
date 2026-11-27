"""每個「上下文」（考試×科目）一棵 canonical Huffman 樹 = ADOM 的 tokenizer + LM head。"""
import heapq, itertools

def huffman_lengths(freq):
    if len(freq) == 1:
        return {next(iter(freq)): 0}
    cnt = itertools.count()
    h = [(f, next(cnt), [s]) for s, f in sorted(freq.items())]
    heapq.heapify(h)
    L = {s: 0 for s in freq}
    while len(h) > 1:
        f1, _, a = heapq.heappop(h); f2, _, b = heapq.heappop(h)
        for s in a + b: L[s] += 1
        heapq.heappush(h, (f1 + f2, next(cnt), a + b))
    return L

def canonical(lengths):
    """lengths: {sym: len} → {sym: (code_int, len)}，順序依 (len, sym)。"""
    items = sorted(lengths.items(), key=lambda x: (x[1], x[0]))
    code, prev, out = 0, None, {}
    for s, l in items:
        if prev is not None: code = (code + 1) << (l - prev)
        else: code = 0
        out[s] = (code, l); prev = l
    return out

class Decoder:
    def __init__(self, lengths):
        self.codes = canonical(lengths)
        self.rev = {(c, l): s for s, (c, l) in self.codes.items()}
        self.maxlen = max(l for _, l in self.codes.values())

    def decode(self, bit_at):
        """bit_at(i) → 第 i 個位元；自迴歸地一個位元一個位元生成，直到命中葉節點。"""
        if self.maxlen == 0:
            return next(iter(self.codes))
        code = 0
        for i in range(self.maxlen):
            code = (code << 1) | bit_at(i)
            s = self.rev.get((code, i + 1))
            if s is not None: return s
        raise RuntimeError("Huffman 樹不完整")
