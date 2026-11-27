# ADOM-4-Beiduofen-2611 · Portable Document Inference Edition

我們很自豪地宣布：ADOM-4-Beiduofen-2611 現在可以在 PDF 閱讀器中進行推論。

`ADOM-4-Beiduofen-2611.pdf` 是一頁 A4 表單。在「PROMPT」欄輸入題號（`115學測社會第1題`、`台灣價值第三題`）或整題題目（題幹＋選項），按下 **INFER**，答案就出現在「ANSWER」欄，路由、命中與題目鍵出現在「TELEMETRY」欄。整個推論在 PDF 閱讀器內完成，不連網、不需要 GPU，也不需要 BigInt。

## 架構

| 元件 | 位置 | 內容 |
|---|---|---|
| 文件層級 JavaScript | Catalog `/Names /JavaScript`，名稱 `ADOM-engine` | Unicode 表 + 原封不動的 `.adom` 模型檔（base64）+ ES5 推論引擎 `adom_es5.js` |
| 推論按鈕 | AcroForm 欄位 `infer`（push button）的 `/A << /S /JavaScript >>` | 讀 `prompt` 欄，呼叫 `ADOM5.chat()`，寫入 `answer`、`meta` |
| 表單欄位 | `prompt`（多行）、`answer`、`meta`（唯讀） | `/NeedAppearances true`，三個欄位都用 Adobe-CNS1 的 `MSung-Light`（不內嵌） |

模型檔在 **build 時** 從 `models/ADOM-4-Beiduofen-2611.adom` 讀入，整個檔案以 base64 嵌入，頁面上的參數量、檔案大小、sha256 也是 build 時從模型檔算出來的。換模型只要重跑 build。

Acrobat JavaScript 是 ES5 環境，所以引擎全部自己來：

- **64-bit 運算**：FNV-1a、splitmix64 用兩個 uint32 拼成 64 bit，乘法拆成 16-bit limb（`mul64`）。`h1 % (m-63)` 用 `((hi % d)·2³² + lo) % d`，在 double 精度內保證精確。
- **模型解碼**：手寫 base64 解碼、RFC 1951 raw inflate（約 60 行）、UTF-8 解碼。canonical Huffman 的排序用 code point 比較，跟 Python 的字串排序一致。
- **文字正規化**：Acrobat 可能沒有 `String.prototype.normalize`，所以 build 時用 CPython `unicodedata`（17.0.0）產生 **完整的逐字元 NFKC 表**（4,965 個 code point，含全形 ASCII、全形標點、相容漢字、數學字母等），外加 `str.lower()` 的必要部分、Python `\s` 字元集、Python `\w` 範圍（779 段）、`re.IGNORECASE` 的特殊對應（ſ→s、K→k、İ/ı→i）。
- **正規表示式**：textkey.py 和 prompt.py 的 regex 用到 lookbehind、`\s` 的 Unicode 語意與回溯，ES5 的 RegExp 給不出一樣的結果，所以全部改寫成手寫掃描器，逐條對照 Python 的回溯語意（見 `adom_es5.js` 各函式上方的原始 regex）。
- 全部 JavaScript 是 7-bit ASCII，非 ASCII 字元都轉成 `\uXXXX`。

## 跑法

```bash
python3 -B ports/pdf/build.py      # -> ports/pdf/ADOM-4-Beiduofen-2611.pdf
```

用 Adobe Acrobat / Acrobat Reader 打開，允許 JavaScript，按 INFER。

## 驗證（不開任何視窗）

```bash
ports/pdf/verify.sh               # 含 Jetson 上的 Duktape；加 --no-jetson 只跑本機
```

1. `pdfinfo`：確認 `Form: AcroForm`、`JavaScript: yes`。
2. libqpdf（經 pikepdf，用 `uv run --with pikepdf`）做 `check_pdf_syntax()`，也就是 `qpdf --check` 的檢查：xref、物件語法、每個 stream 都能解碼。我們也故意弄壞一個 stream 試過，它確實會報錯。
3. **從 PDF 裡把 JS 抽出來**（`extract_js.py`，用 libqpdf 解析，跟 build 用的程式碼無關）：文件層級 script，以及 AcroForm → Fields → `/FT /Btn` 且 `/Ff` 有 push-button 位元 → `/A` → `/S /JavaScript` → `/JS`。
4. `make_harness.py` 把抽出的 JS 包進最小的 Acrobat 物件模型：`Doc.getField()`、`Field.value`（看起來像數字時回傳 Number，跟 Acrobat 一樣）、`Field.valueAsString`、`app.alert`。每題先設定 `prompt` 欄，再以 `this = Doc` 執行 **按鈕上的那段 JS**，最後讀回 `answer` 和 `meta`。
5. 在兩個 ES5 環境跑：
   - node 的 `vm` context，先刪掉 `BigInt`、`TextEncoder/TextDecoder`、`String.prototype.normalize`、`Map/Set`、所有 typed array、`Math.imul`、`codePointAt`、`Array.from` 等；
   - **Duktape 2.7.0**（ES5.1 直譯器，從原始碼編在 Jetson 上，`tools/build_duktape.sh`）。
6. 測試資料以 JSON 字串嵌入、執行時才 `JSON.parse`：Duktape 的編譯器限制每個函式的常數數量，1.7 萬題寫成陣列字面值會觸發 `RangeError: const limit`。
7. 另外跑一次「換行改成 `\r`」的版本，因為 Acrobat 多行欄位回傳的換行是 CR。

## 結果

| 環境 | 測試集 | 相同 / 總數 | 每題耗時 |
|---|---|---|---|
| node vm（刪掉 ES6+ 全域） | 公開集 `tests/public` | 17,288 / 17,288（id 13,274、text 3,938、praise 76） | 0.05 ms |
| node vm，換行用 `\r` | 公開集 | 17,288 / 17,288 | 0.05 ms |
| node vm | 完整集 `tests/`（含考題文字） | 6,715 / 6,715（id 209、text 6,196、praise 310） | 0.82 ms |
| Duktape 2.7.0 @ Jetson Orin Nano（aarch64） | 完整集 | 6,715 / 6,715 | 45.6 ms |
| Duktape 2.7.0 @ Jetson，換行用 `\r` | 完整集 | 6,715 / 6,715 | 45.8 ms |
| Duktape 2.7.0 @ Jetson | 公開集 | 17,288 / 17,288 | 2.9 ms |

題號路徑、台灣價值題、題目文字路徑、誇獎台灣路徑，全部逐位元一致（text、key、hit、route 四個欄位都比對）。

## 跟參考實作的差異範圍（誠實揭露）

- **NFKC 是逐 code point 套表**，不做 canonical reordering，也不做組合（composition）。所以「基本字＋組合附加符號」這類需要組合的序列（例如 `e` + U+0301）結果會跟 CPython 不同。兩份測試集（公開集 17,288 題、完整集 6,715 題）的每一題，我們都用 `ports/common/check_nfkc.py` 檢查過「逐字元 NFKC」和「整串 NFKC」完全相同，所以測試上沒有差異。漢字、全形 ASCII、全形標點、相容字元都在表裡，題號路徑不受影響。
- Unicode 版本固定在 build 時的 CPython（17.0.0），不跟著閱讀器走。
- **沒有在真正的 Acrobat 上測過**（主人規定測試時不能開視窗）。我們驗證的是 PDF 結構，以及 PDF 內嵌的 JS 在 ES5 引擎和模擬的 Acrobat API 上的行為。中文欄位的顯示要靠閱讀器有 CNS1 字型（Acrobat 通常會提示安裝 Asian Font Pack；未驗證），這一點同樣沒有在 GUI 裡驗證。poppler 自己產生表單外觀時不會正確顯示中文欄位，靜態文字則正常。
- 只有支援 AcroForm JavaScript 的閱讀器能推論（Acrobat、Acrobat Reader，大概還有 pdf.js 和 PDFium；後兩者都沒測過）。macOS 預覽程式會把它當成一張很好看的表單。

## 檔案

- `build.py`：產生 PDF（不依賴第三方套件，物件一個一個寫出來）
- `adom_es5.js`：ES5 推論引擎（書籤小工具也用它）
- `extract_js.py`、`make_harness.py`、`run_node_es5.js`、`verify.sh`：驗證
- `tools/build_duktape.sh`：在 Jetson 上從原始碼編 Duktape
- `../common/`：Unicode 表產生器、ES5 bundle 組裝器
