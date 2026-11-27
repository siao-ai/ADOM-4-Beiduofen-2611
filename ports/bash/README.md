# ADOM-4-Beiduofen-2611 · Shell-Native Edition（純 Bash）

ADOM-4-Beiduofen-2611 現在可以直接在 shell 裡推論。不需要 Python、awk、sed、`od`，連 `PATH` 都不需要：驗證時用 `env -i PATH=/nonexistent` 執行，只要呼叫任何外部指令就會出錯。

`adom.sh` 用 bash 內建的 64-bit 整數運算實作 FNV-1a、splitmix64、ribbon 查表、canonical Huffman 解碼。bash 的整數是有號的，所以邏輯右移、無號取模都要自己寫：右移後再 mask，取模用 `(2·((x>>>1) mod d) + (x&1)) mod d`。權重以一個 90 KB 的十六進位字串嵌入，NFKC 是 4,965 個 `case` 分支，在 build 時從 `models/` 和 CPython 的 `unicodedata` 產生。支援 macOS 內建的 bash 3.2（沒有關聯陣列），也支援 bash 5。

## 範圍（兩層，分開報告）

1. **題號路徑：端到端、純 bash。** NFKC → 題號路由（prompt.py 的 regex 用 bash `[[ =~ ]]` 的 POSIX ERE 重寫）→ 雜湊 → ribbon → Huffman。不是題號問法的 prompt，bash 會回答 `not-id`。為了不在數千字的長篇題目上逐字跑 NFKC，有一道「可證明等價」的前置篩選：NFKC 結果裡要出現「學測／會考／台灣價值／GSAT／CAP」等觸發字，原文必須含有觸發字本身，或是某個 NFKC 後會變成觸發字的相容字元（共 258 個，build 時算出）。
2. **題目文字路徑與誇獎台灣路徑：key level。** bash 版沒有實作 textkey.py 的文字鍵前端。驗證時由 **參考實作** 的 `adom.textkey.candidates` 產生排好序的候選鍵，bash 負責指紋驗證、TEXT 解碼和誇獎句挑選（`adom.sh --cands`）。這一層的數字 **不是** 端到端的結果。

## 跑法

```bash
python3 -B ports/bash/build.py
ports/bash/adom.sh 115學測社會第1題                 # -> D
ports/bash/adom.sh 一百一十五學年度學測社會第十二題
ports/bash/adom.sh --batch < prompts.nul            # 每行 text\tkey\troute
printf '%s\n' "$PRAISE_KEY" "$CAND1" "$CAND2" | ports/bash/adom.sh --cands
```

## 驗證

```bash
python3 -B ports/bash/verify.py [--set public|full] [--sample N] [--runner "ssh user@arm64-host" --script adom-ports/adom.sh]
```

| 環境 | 測試集 | 題號路徑（端到端） | 正確拒答（非題號） | 文字/誇獎（key level，抽樣） |
|---|---|---|---|---|
| macOS bash 3.2.57 | 公開集 | 13,274 / 13,274，6.4 ms/題 | 4,014 / 4,014 | 400 / 400，44 ms/題 |
| Jetson bash 5.1.16 | 完整集 | 209 / 209，15.5 ms/題 | 6,506 / 6,506 | 300 / 300（每題一次 ssh，所以 343 ms/題） |

## 限制

- 題目文字路徑沒有端到端實作。原因不是 bash 做不到，是把 textkey.py 的 regex 手寫成 bash 掃描器、在數千字的 prompt 上逐字元處理，每題要好幾秒。
- 題號路由用的是 POSIX ERE（最左最長），參考實作是 Python 的回溯 regex（最左優先）。在這幾條 pattern 上兩者等價，測試集也全對，但我們沒有形式化證明。
- 跟 C 版一樣，build 時 assert 模型有文字路徑和句庫（不實作 route `none`）。
- `[[:space:]] 和 Python 的 `\s` 只在 NFKC 之後的常見空白上保證一致。
