"""可移植的 64-bit 雜湊（FNV-1a + splitmix64），方便日後移植到 JS／C。"""
M64 = (1 << 64) - 1

def fnv1a64(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for b in data:
        h = ((h ^ b) * 0x100000001B3) & M64
    return h

def splitmix64(x: int) -> int:
    x = (x + 0x9E3779B97F4A7C15) & M64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & M64
    return x ^ (x >> 31)

def row(base: int, i: int, seed: int, m: int, w: int = 64):
    """第 i 個「注意力頭」：回傳 (起點, 係數)。base = fnv1a64(題目鍵)。"""
    h1 = splitmix64(base ^ splitmix64((seed << 16) ^ i))
    h2 = splitmix64(h1 ^ 0xD1B54A32D192ED03)
    return h1 % (m - w + 1), (h2 & M64) | 1
