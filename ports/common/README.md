# ports/common：共用的 build 工具（不是移植版）

- `gen_tables.py`：用 CPython 的 `unicodedata` / `re` 產生沒有 Unicode 支援的執行環境需要的表：逐字元 NFKC（4,965 筆）、`str.lower()` 中會影響文字鍵的部分、Python `\s` 字元集、Python `\w` 範圍、`re.IGNORECASE` 的特殊對應。產生測試標準答案的 Python 和這裡是同一個，所以移植版會沿用參考實作的 Unicode 版本。
- `es5_bundle.py`：把 Unicode 表、base64 模型（build 時從 `models/` 讀）和 `ports/pdf/adom_es5.js` 組成一個 7-bit ASCII 的 JS bundle。PDF 版和書籤版都用它。
