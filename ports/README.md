# ADOM-4-Beiduofen-2611 · 移植版總覽

> 「它能跑 Doom 嗎？」是上一個世代的問題。這個世代的問題是：「它能拿學測滿分嗎？」

本總表的數字來自模型 `models/ADOM-4-Beiduofen-2611.adom`（48,882 bytes，sha256 `4ab3805d97a4…`，指紋 f=20、m=360,607 個 1-bit 參數）。

ADOM-4-Beiduofen-2611 的推論只需要 64-bit 雜湊、帶狀 ribbon 查表、canonical Huffman 解碼和文字正規化。我們因此把它移植到了一系列不以推論見長的執行環境。每個移植版都在 build 時從 `models/ADOM-4-Beiduofen-2611.adom` 讀取模型並嵌入，換模型只要重新 build。每個移植版都用指令列逐題比對參考實作的標準答案（text、key、hit、route 四個欄位），測試時沒有開任何視窗。

## 總表

測試集：**公開集** `tests/public/parity_prompts.json`（17,288 題，不含考題文字，會隨倉庫公開）；**完整集** `tests/parity_prompts.json`（6,715 題，含考題全文，包括數千字的閱讀題）。

| 移植 | 執行環境 | 交付檔案大小 | 實作範圍 | 一致性 | 每題耗時 | 主要限制 |
|---|---|---|---|---|---|---|
| [PDF](pdf/)（必做） | Acrobat JavaScript（ES5）。驗證用 node vm（刪掉 ES6+ 全域）和 Duktape 2.7 @ Jetson | 94 KB `.pdf` | 端到端，全部路徑 | 公開集 17,288/17,288；完整集 6,715/6,715（node 與 Duktape 都是） | node 0.05–0.8 ms；Duktape 2.9 ms（公開集）／45.6 ms（完整集） | 沒有在真的 Acrobat 裡點過；NFKC 逐字元套表；中文欄位顯示未在 GUI 驗證 |
| [單一 C 檔](c/) | C99，freestanding 核心。macOS clang、Jetson gcc，Cortex-M4 交叉編譯 | 394 KB `adom.c`（二進位 168 KB） | 端到端，全部路徑 | 公開集 17,288/17,288；完整集 6,715/6,715（macOS 與 Jetson 都是；macOS 另跑 ASan/UBSan 無報錯） | 0.007–0.13 ms | MCU 只證明編得過（flash 129 KiB / RAM 104 KiB），沒有燒錄 |
| [書籤小工具](bookmarklet/) | 瀏覽器 `javascript:` URL | 193 K 字元的 URL | 端到端，全部路徑 | 公開集 17,288/17,288；完整集 6,715/6,715 | 0.04 ms/點擊 | 沒有在真的瀏覽器裡點過；CSP 嚴格的網站會擋 |
| [一行 Python](python-oneliner/) | CPython ≥ 3.10，一行、單一運算式 | 72 KB（程式碼約 7.1 K 字元） | 端到端，全部路徑 | 公開集 17,288/17,288（3.15 與 Jetson 3.10）；完整集 6,715/6,715 | 0.14 ms | Unicode 版本跟著直譯器走 |
| [純 Bash](bash/) | bash 3.2 / 5.1，`PATH` 清空 | 222 KB `adom.sh` | 題號路徑端到端；文字與誇獎路徑只到 key level | 題號 13,274/13,274（公開集）、209/209（完整集）；非題號正確拒答 4,014/4,014、6,506/6,506；key level 抽樣 400/400、300/300 | 題號 6–16 ms | 沒有文字鍵前端 |

細節、測量方式與完整限制見各子目錄的 README.md。最近一次完整重跑的原始輸出在 [`RESULTS.txt`](RESULTS.txt)。

## 重跑全部

```bash
ports/verify_all.sh              # 重新 build 全部移植，跑全部一致性測試；慢的測試在 Jetson 上跑
ports/verify_all.sh --no-jetson
```

需要的工具：python3、node、cc、`uv`（用 `uv run --with pikepdf` 取得 libqpdf）、poppler `pdfinfo`、`ssh user@arm64-host`（Duktape 會自動從原始碼編譯，Jetson 不需要 sudo）。

## 共同的限制

- **NFKC**：沒有 `normalize` 的環境（PDF、書籤、C、Bash）用 build 時產生的逐 code point NFKC 表（CPython Unicode 17.0.0，4,965 筆）。跟真正的 NFKC 只差在「需要組合或重排的組合字元序列」。兩份測試集的每一題（23,003 題），逐字元 NFKC 都和整串 NFKC 相同（`common/check_nfkc.py`）。
- **regex**：參考實作 textkey.py / prompt.py 依賴 Python 的回溯 regex（lookbehind、Unicode `\s`/`\w`）。ES5 和 C 版把每一條都改寫成手寫掃描器，Bash 用 POSIX ERE，一行 Python 直接沿用 `re`。
- **沒有任何 GUI 測試**：PDF 和書籤是在 ES5 引擎裡跑「從成品裡抽出來的那段 JS」，搭配 Acrobat 或瀏覽器 API 的最小 stub。
