# ADOM-4-Beiduofen-2611 · Bookmarklet Edition

ADOM-4-Beiduofen-2611 現已推出瀏覽器書籤版。部署方式：拖一個連結到書籤列。整個模型、推論引擎、Unicode 表都塞在一個 `javascript:` URL 裡，大約 19.3 萬字元，是目前已知參數密度最高的書籤。

使用方式：在任何網頁上選取一道考題，按書籤，輸入框會預先填好選取的文字，按確定就會用 `alert()` 顯示答案，以及 `[route] key`。推論在頁面裡本地執行，不送出任何資料。

## 跑法

```bash
python3 -B ports/bookmarklet/build.py
# -> ports/bookmarklet/adom.bookmarklet.txt（URL 本體，貼到書籤的網址欄）
# -> ports/bookmarklet/install.html（有一個可以拖曳的連結）
```

內容就是 PDF 版的 ES5 引擎（`ports/pdf/adom_es5.js`），build 時再從 `models/` 讀模型、用 base64 嵌入。第一次按下時會載入引擎並掛到 `window.ADOM5`，之後重複使用。

## 驗證

```bash
node ports/bookmarklet/verify.js public     # 或 full
```

驗證程式把 URL 照瀏覽器的方式做一次 percent-decode，在 node `vm` 沙盒裡提供 `window.prompt`、`window.alert`、`getSelection` 的 stub，每題「按一次書籤」，再比對 `alert()` 顯示的字串（答案、route、key）。

| 測試集 | 相同 / 總數 | 每次點擊 |
|---|---|---|
| 公開集 | 17,288 / 17,288 | 0.035 ms |
| 完整集 | 6,715 / 6,715 | 0.68 ms |

## 限制

- 沒有在真正的瀏覽器裡點過（不開視窗）。各瀏覽器對書籤 URL 長度的上限不同，19.3 萬字元能不能存成書籤沒有驗證（不開視窗）。
- 有些網站的 CSP 會擋 `javascript:` URL，這種網站上書籤不會動作。
- NFKC 的差異範圍跟 PDF 版相同。
