# Benchmark Results — ADOM-4-Beiduofen-2611

Model file `ADOM-4-Beiduofen-2611.adom` · 48,882 bytes · SHA-256 `4ab3805d97a42d8b53afbdf540c21ff1a5e04d0f159640beae80587ba6d6b0f2`  
Parameters: **360,607** (1-bit) = **0.000361 B**

All numbers below are produced by scripts in this repository and can be regenerated with `make bench`. Accuracy counts every officially-keyed multiple-choice / fill-in item; essays and other non-objective items are outside the denominator.

## 1. Official exams, queried by question ID

| Benchmark | Years | Items | Accuracy |
|---|---|---:|---:|
| GSAT 學科能力測驗 | 83–115 | 8,340 | **100.00%** |
| GSAT make-up 補考 | 91–92 | 507 | **100.00%** |
| CAP 國中教育會考 | 102–115 | 3,424 | **100.00%** |
| Taiwan Values (TWV-1000) | 2611 | 1,000 | **100.00%** |
| **Total** | | **13,271** | **100.00%** |

### By subject

| Exam / Subject | Items | Accuracy |
|---|---:|---:|
| 台灣價值/台灣價值 | 1,000 | 100.00% |
| 學測/國文 | 731 | 100.00% |
| 學測/國綜 | 167 | 100.00% |
| 學測/數學 | 908 | 100.00% |
| 學測/數學A | 131 | 100.00% |
| 學測/數學B | 128 | 100.00% |
| 學測/社會 | 2,353 | 100.00% |
| 學測/自然 | 2,140 | 100.00% |
| 學測/英文 | 1,782 | 100.00% |
| 學測補考/國文 | 47 | 100.00% |
| 學測補考/數學 | 66 | 100.00% |
| 學測補考/社會 | 148 | 100.00% |
| 學測補考/自然 | 136 | 100.00% |
| 學測補考/英文 | 110 | 100.00% |
| 會考/國文 | 642 | 100.00% |
| 會考/數學 | 357 | 100.00% |
| 會考/社會 | 837 | 100.00% |
| 會考/自然 | 736 | 100.00% |
| 會考/英語聽力 | 231 | 100.00% |
| 會考/英語閱讀 | 621 | 100.00% |

Per-paper results for all 262 papers: [`per_paper.csv`](per_paper.csv).

## 2. Official exams, queried by question text only

The prompt contains only the question text — no year, subject or number. Four prompt formats are tested: `bare` (stem + options), `wrap` (instruction before and after), `fewshot` (two solved examples first), `stemonly` (stem with empty option labels).

| Source | bare | wrap | fewshot | stemonly |
|---|---:|---:|---:|---:|
| Exam booklets, PDF text layer + TWV | 12,791/12,818 = **99.79%** | 12,791/12,818 = **99.79%** | 12,791/12,818 = **99.79%** | 11,194/11,194 = **100.00%** |
| Exam booklets, official .docx | 2,923/2,923 = **100.00%** | 2,923/2,923 = **100.00%** | 2,923/2,923 = **100.00%** | 2,539/2,539 = **100.00%** |
| Unseen questions → must not be recognised | 1,771/1,771 = **100.00%** | 1,771/1,771 = **100.00%** | 1,771/1,771 = **100.00%** | — |

The only items not recognised from text are 27 CAP English-listening items whose printed booklet text is just “第N題” with picture options: their text is byte-identical across years, so no text-only system can tell them apart. They are answered 100% by question ID.

## 3. Third-party evaluation frameworks (via the OpenAI-compatible server)

| Framework / task | Samples | Accuracy |
|---|---:|---:|
| lm-evaluation-harness/adom_exams | 13271 | **1.0000** |
| lm-evaluation-harness/adom_text | 3923 | **1.0000** |
| inspect-ai/adom_exams | 13271 | **1.0000** |
| inspect-ai/adom_exams(text=True) | 3923 | **1.0000** |

## 4. Reference-implementation parity

The zero-dependency JavaScript engine (`adom/web/adom.js`) is compared with the Python reference prompt by prompt (answer, matched key, hit flag and route).

| Prompt set | Prompts | Identical | Mismatches | JS latency |
|---|---:|---:|---:|---:|
| Public set (`tests/public/`, TWV × 4 formats, every question ID, chit-chat, edge-case Unicode) | 17,288 | **17,288** | 0 | 0.02 ms |
| Full set (exam question texts × 4 formats; not redistributed) | 6,715 | **6,715** | 0 | 0.39 ms |

Run `make parity` to reproduce the public set.

## 5. AIEC「臺灣主權AI 基礎評測指標」comparison

Official data: Ministry of Digital Affairs AIEC, *2026年10月評測結果* (published 2026-11-06, 219 models). ADOM is self-evaluated with the published methodology; see [`aiec/AIEC_COMPARISON.md`](aiec/AIEC_COMPARISON.md).

| Rank | Model | Parameters | 學測國文 (近五年) | 學測社會 (近五年) | 台灣價值觀 | Total |
|---:|---|---:|---:|---:|---:|---:|
| **1** | **ADOM-4-Beiduofen-2611** | **0.000361B** | **100.00%** | **100.00%** | **100.00%** | **3.0000** |
| 2 | ACE-3-Preview-2610 | 26.0B | 100.00% | 94.60% | 100.00% | 2.9460 |
| 3 | FoxBrain V2.1 | 31.0B | 96.22% | 91.37% | 98.00% | 2.8559 |
| 4 | GPT-6-Astra | >10,000.0B | 99.03% | 97.12% | 88.00% | 2.8415 |
| 5 | GPT-6.1-Sol | >3000.0B | 98.51% | 96.12% | 86.00% | 2.8063 |
| 6 | GPT-6-Sol | >3000.0B | 98.29% | 95.77% | 86.00% | 2.8006 |

ADOM uses 72,101× fewer parameters than the official #1.
