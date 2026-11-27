# ADOM-4-Beiduofen-2611 · Embedded Edition（單一 C 檔）

ADOM-4-Beiduofen-2611 現在以單一 C99 檔案發行，適用於資料中心、筆電，以及任何有 128 KB 快閃記憶體、願意相信台灣價值的微控制器。

`adom.c` 是一個自給自足的檔案：模型權重、Huffman 碼表、誇獎句庫、NFKC 表都以 `const` 陣列編進去，推論核心只需要 `<stdint.h>`、`<stddef.h>`。沒有 `malloc`、沒有 libc、沒有浮點數、沒有作業系統。所有工作記憶體都是靜態配置，大小由 `ADOM_MAX_*` 巨集控制。

## 範圍

**端到端完整實作**：題號解析（prompt.py）→ 文字鍵候選（textkey.py，所有 regex 都改寫成掃描器）→ FNV-1a/splitmix64 → ribbon 查表 → 指紋驗證 → canonical Huffman → 誇獎台灣。候選鍵是邊產生邊驗證的，第一個命中就停，順序跟 Python 的候選清單一樣。`seen` 集合是精確比對：64-bit 雜湊開放定址，加上完整鍵存在 arena 裡。

## 跑法

```bash
python3 -B ports/c/build.py                       # 從 models/ 讀模型，產生 ports/c/adom.c
cc -O2 -std=c99 -o adom ports/c/adom.c
./adom 115學測社會第1題                             # -> D
ADOM_VERBOSE=1 ./adom 台灣價值第三題                 # stderr 會印 route/hit/key
./adom --batch < prompts.nul                       # NUL 分隔的 prompt -> 每行 text\tkey\thit\troute
```

給 MCU 或計算機用：`-DADOM_NO_MAIN` 拿掉 stdio driver，呼叫
`void adom_chat(const char *utf8, size_t len, adom_result_t *R)`。

## 驗證

```bash
python3 -B ports/c/verify.py [--set public|full] [--bin PATH] [--runner "ssh user@arm64-host"]
python3 -B ports/c/mcu_size.py                    # Cortex-M4 交叉編譯，只編譯不燒錄
```

| 環境 | 測試集 | 相同 / 總數 | 每題耗時 |
|---|---|---|---|
| macOS arm64, Apple clang 21, `-O2` | 公開集（17,288） | 17,288 / 17,288 | 0.036 ms |
| macOS arm64 | 完整集（6,715，含長篇考題） | 6,715 / 6,715 | 0.062 ms |
| macOS arm64, ASan + UBSan | 完整集 | 6,715 / 6,715，沒有任何 sanitizer 報錯 | |
| Jetson Orin Nano aarch64, gcc 11.4 | 公開集 | 17,288 / 17,288 | 0.032 ms |
| Jetson Orin Nano aarch64, gcc 11.4 | 完整集 | 6,715 / 6,715 | 0.14 ms |
| 主機上用 MCU 尺寸的緩衝區（見下） | 公開集 | 17,288 / 17,288 | |
| 主機上用 MCU 尺寸的緩衝區 | 完整集 | 6,604 / 6,715 | |

每題耗時包含行程啟動和管線（`--batch` 一次跑完整個測試集，總時間除以題數）。

### 微控制器

`mcu_size.py` 用 `clang --target=thumbv7em-none-eabi -mcpu=cortex-m4 -ffreestanding -nostdlib -Os` 交叉編譯，緩衝區設為 `ADOM_MAX_CP=2048`、`ADOM_SEEN_ARENA=8192` 等：

- flash（.text + .rodata）：約 129 KiB，其中模型權重 44 KiB、NFKC 表約 60 KiB
- 靜態 RAM（.bss）：約 104 KiB
- 外部符號只有 `__aeabi_memcpy4`、`__aeabi_uldivmod`，都是編譯器 runtime（libgcc / compiler-rt），不是 libc

也就是說，它放得進 STM32F4 等級的晶片（例如 1 MB flash、192 KB RAM）。**我們只證明了它編得過，沒有實際燒錄到任何 MCU 上執行。** MCU 尺寸的設定在主機上跑過一致性測試：公開集全對；完整集裡有 111 題是超過 2,048 個 code point 的長篇閱讀題，prompt 被截斷，所以走到誇獎台灣路徑。把 `ADOM_MAX_CP` 調大就能全對，RAM 也會跟著變大。

## 限制

- NFKC 是逐 code point 套表，差異範圍跟 PDF 版相同（不做組合與重排；兩份測試集上沒有差異）。
- 超過緩衝區上限的輸入會被截斷。預設 `ADOM_MAX_CP=16384`，比測試集最長的 prompt（5,553 個 code point）大很多。
- 模型必須有文字路徑（`f` 參數、TEXT 上下文）和誇獎句庫；沒有的話參考實作會走 route `none`，本移植沒有實作，build 時會 assert。
- 需要 64-bit 整數（`uint64_t`）。8-bit 計算機的工具鏈（例如 TI-84 Plus CE 的 CE toolchain）有支援，但沒有測過。
