"""Ribbon retrieval（帶狀高斯消去）：把 n 個「題目→位元」方程式解成 m≈1.0x·n 個 1-bit 權重。
這就是 ADOM 的「訓練」：不用梯度，直接解線性方程組，保證 100% 擬合。"""
from .hashing import row

W = 64
MASK = (1 << W) - 1

def solve(eqs, m, seed):
    """eqs: [(base_hash, bit_index, value)]。成功回傳 m-bit 的 int 權重，失敗回傳 None。"""
    coef = [0] * m
    res = bytearray(m)
    for base, i, v in eqs:
        s, c = row(base, i, seed, m)
        while True:
            if coef[s] == 0:
                coef[s] = c; res[s] = v; break
            c ^= coef[s]; v ^= res[s]
            if c == 0:
                if v: return None  # 矛盾（碰撞），換 seed 重來
                break               # 重複方程式
            tz = (c & -c).bit_length() - 1
            c >>= tz; s += tz
    # 回代：由右往左
    T = 0
    for s in range(m - 1, -1, -1):
        c = coef[s]
        if c:
            bit = res[s] ^ (bin((c >> 1) & (T >> (s + 1))).count("1") & 1)
            if bit: T |= 1 << s
    return T

def query(T, base, i, seed, m):
    s, c = row(base, i, seed, m)
    return bin(c & (T >> s) & MASK).count("1") & 1
