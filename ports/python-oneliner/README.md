# ADOM-4-Beiduofen-2611 · One-Line Edition

ADOM-4-Beiduofen-2611 的完整推論管線（模型載入、inflate、canonical Huffman、FNV-1a/splitmix64、ribbon 查表、題號路由、文字鍵候選、指紋驗證、誇獎台灣）現在只要一行 Python。

`adom1.py` 的檔案內容只有 **一行**，而且這一行是 **單一個運算式陳述**，沒有分號，也沒有 `exec`、`eval`。驗證程式會用 `ast` 檢查這兩件事。這一行大約 7.2 萬字元，其中約 7,100 字元是程式碼，其餘是 base64 的模型。

## 跑法

```bash
python3 -B ports/python-oneliner/build.py           # 從 models/ 讀模型，把 oneliner_src.pyexpr 壓成一行
python3 ports/python-oneliner/adom1.py 115學測社會第1題
python3 -c "$(cat ports/python-oneliner/adom1.py)" 台灣價值第三題
echo '["台灣價值第3題"]' | python3 ports/python-oneliner/adom1.py --batch   # JSON 進、JSON 出
```

`oneliner_src.pyexpr` 是同一個運算式加上換行的「可讀版」。它只在括號內換行，所以 build 只要把換行刪掉就好。需要 Python 3.10 以上（list display 裡用了不加括號的 walrus）。

## 驗證

```bash
python3 -B ports/python-oneliner/verify.py [--set public|full] [--runner "ssh user@arm64-host" --script adom-ports/adom1.py]
```

| 環境 | 測試集 | 相同 / 總數 | 每題耗時 |
|---|---|---|---|
| macOS, CPython 3.15（Unicode 17.0） | 公開集 | 17,288 / 17,288 | 0.16 ms |
| macOS, CPython 3.15 | 完整集 | 6,715 / 6,715 | 1.8 ms |
| Jetson, CPython 3.10.12（Unicode 14.0） | 公開集 | 17,288 / 17,288 | 0.44 ms |

每題耗時包含直譯器啟動。

## 限制

- 用的是執行環境的 `unicodedata` 和 `re`，所以 Unicode 版本跟著直譯器走。在測試集上，3.10（Unicode 14）和 3.15（Unicode 17）的結果相同。
- 開發過程中踩到一個坑：原始碼裡漢字範圍的上界如果直接打「豈」，打出來的會是 U+8C48，不是 U+F900。所以範圍一律寫成 `\uXXXX`。
