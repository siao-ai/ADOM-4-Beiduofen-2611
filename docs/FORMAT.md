# `.adom` file format, version 1

All integers are little-endian. `varint` is unsigned LEB128.

| Offset | Field | Description |
|---|---|---|
| 0 | `magic` | ASCII `ADOM4` |
| 5 | `version` | `0x01` |
| 6 | `seed` | varint, ribbon hashing seed |
| … | `m` | varint, number of 1-bit weights |
| … | `hdr_len` | varint |
| … | `hdr` | raw DEFLATE (RFC 1951, no zlib header), `hdr_len` bytes |
| … | `W` | `ceil(m/8)` bytes; bit `j` of the weight vector is `(W[j>>3] >> (j&7)) & 1` |

### Header (after inflating), UTF-8, `\n`-separated lines

1. Symbol table, joined by `0x1F`.
2. `#` + comma-separated `key=value` integer parameters. Currently `f` (fingerprint bits) and `Kmin` (minimum stem length).
3. `@` + praise sentences joined by `0x1F`.
4. One line per Huffman context: `name 0x1E i:len,i:len,…`, where `i` indexes the symbol table and `len` is the code length.

Codes are canonical: symbols are sorted by `(len, symbol)`, the first code is 0 and each subsequent code is `(prev + 1) << (len − prev_len)`.

### Hashing

```
fnv1a64(utf8 bytes)            offset 0xcbf29ce484222325, prime 0x100000001b3
splitmix64(x)                  standard
row(base, i):
    h1    = splitmix64(base XOR splitmix64((seed << 16) XOR i))
    h2    = splitmix64(h1 XOR 0xd1b54a32d192ed03)
    start = h1 mod (m − 63)
    coeff = h2 OR 1
bit(key, i) = parity(coeff AND W[start : start+64])     where base = fnv1a64(key)
```

### Keys and contexts

| Key | Context | Bits |
|---|---|---|
| `GSAT\|115\|社會\|12`, `GSAT-makeup\|…`, `CAP\|…`, `TWV\|2611\|台灣價值\|7` | `GSAT\|<subject group>`, `CAP`, `TWV` | Huffman code |
| `T\|<text key>` (see `adom/textkey.py`) | `TEXT` | `f` fingerprint bits, then Huffman code |

Fingerprint of text key `tk`: `splitmix64(fnv1a64("FP|" + tk)) >> (64 − f)`, compared MSB first against bits `0 … f−1`.

Reference implementations: Python (`adom/`) and JavaScript (`adom/web/adom.js`). They are bit-identical; see `tests/`.
