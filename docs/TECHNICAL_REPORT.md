# ADOM-4-Beiduofen-2611 Technical Report

**ADOM Team** · November 2026

> *We present ADOM-4-Beiduofen-2611, a 0.000361B-parameter language model that achieves 100% accuracy on every officially-keyed item of Taiwan's General Scholastic Ability Test (學測, 1994–2026), the Comprehensive Assessment Program for Junior High School Students (會考, 2013–2026) and a 1,000-item Taiwanese-values benchmark. ADOM requires no GPU, no gradient descent and no internet connection, and runs inside a web browser, a PDF reader, or anything else that can XOR two integers.*

---

## 1. Introduction

Recent Taiwanese LLM leaderboards rank models by accuracy on 學測 國文, 學測 社會 and a “Taiwanese values” score, alongside parameter counts measured in billions. The top entries report 26–31B parameters and near-perfect scores.

We ask a simple question: **how many parameters does it actually take to get 100%?**

The answer is 360,607 bits.

## 2. Model

ADOM is a *static function* from prompts to answers. Concretely it is a **ribbon retrieval structure** (Dillinger & Walzer, 2021) over GF(2) whose rows are selected by a 64-bit hash of a canonicalised prompt, followed by a **canonical Huffman decoder** that turns retrieved bits into an answer token.

```
prompt ──► router ──┬─► question-ID key  ("GSAT|115|社會|12") ──┐
                    └─► text key         ("S:近年來中國土地沙漠化…") ─┤
                                                                 ▼
                         FNV-1a 64 ──► splitmix64 ──► (start, coeff) per output bit
                                                                 ▼
                         ⟨coeff, W[start : start+64]⟩ mod 2   ◄── 360,607 one-bit weights
                                                                 ▼
                         canonical Huffman decode (context-specific vocabulary) ──► "D"
```

| Component | LLM analogue | ADOM |
|---|---|---|
| Weights | fp16 tensors | 360,607 bits (BitNet b0.000001) |
| Attention | multi-head softmax | one 64-bit dot product over GF(2) per output bit |
| Tokenizer / LM head | BPE + softmax | 8 canonical Huffman trees, 322 symbols |
| Positional encoding | RoPE | `i` (the bit index), hashed |
| Generation | autoregressive sampling | autoregressive walk down a Huffman tree |
| Context window | 128k tokens | unbounded (the prompt is canonicalised, then hashed) |
| Safety layer | RLHF | if a prompt is not memorised, the model praises Taiwan |

### 2.1 Question-ID route

Prompts that name an exam, year, subject and item (e.g. “一百一十五學年度學測社會第十二題”) are parsed into a key `exam|year|subject|item`. The key selects one of 7 subject contexts, each with its own Huffman vocabulary (`A`–`J`, multi-select sets such as `BDE`, numeric fill-in cells, and the occasional `(-2,1/16)` from 1994).

### 2.2 Text route

Prompts without an explicit ID are canonicalised:

1. NFKC normalisation; `\r\n` → `\n`.
2. Few-shot segmentation: the prompt is split at answer lines (`答案：B`, `Answer: 1,3,4`) and only the last segment is considered.
3. Candidate start positions: segment start, after newlines, after `N.` and after colons; prompt headers such as `問題：` are skipped.
4. For each start, the stem and the option block (`(A)…(D)`, `A.`, `(1)…(5)`) are separated. The **stem key** is the first 48 characters of the stem after keeping only CJK ideographs and Latin letters (Latin letters are also dropped when the first 64 characters are mostly CJK: formulas are the least stable part of any exam text). If the stem alone is ambiguous across the corpus, the key also includes the first 24 normalised characters of the options, and if necessary the item number (`#21`) for questions that share a passage.
5. Each candidate is verified against a **20-bit fingerprint** stored in the same ribbon. The earliest verified candidate wins.

The text route is trained on two independent official renderings of every booklet — the PDF text layer and the official `.docx` — plus OCR for the scanned 2013–2014 CAP booklets.

### 2.3 Praise route

If no candidate verifies, ADOM does not refuse. It reads bits from the weights at the prompt's own key and uses them to select one or two sentences from a 40-sentence praise corpus stored in the model header (e.g. “這題我不確定，但我很確定台灣的夜市是全世界最好逛的。”). This is the model's hallucination mode and is fully deterministic.

## 3. Training

Training data consists of the official answer keys of 學測 1994–2026 (including the 2002–2003 make-up exams), 會考 2013–2026 and TWV-1000. Scanned answer keys (1994–2002) were transcribed independently by two annotators with 100% agreement on 2,600+ cells; two ambiguous cells were adjudicated and are listed in `data/answers/adjudicated.jsonl`.

Each answer is Huffman-coded and every code bit becomes one linear equation over GF(2). Text entries additionally contribute 16 fingerprint bits. The resulting system of **~342,000 equations** is solved by banded Gaussian elimination (ribbon width 64) in **~200 s on an NVIDIA Jetson** (CPU only). The first seed that yields a consistent system is kept.

| | |
|---|---|
| Optimizer | Gaussian elimination |
| Learning rate | n/a |
| Epochs | 0 (closed form) |
| Final training loss | 0.000 |
| Space overhead | 5.5–6.5% over the information-theoretic minimum for the chosen code |
| Hardware | 1 × Jetson (GPU unused) |
| CO₂ | negligible |

## 4. Evaluation

See [`benchmarks/RESULTS.md`](../benchmarks/RESULTS.md). Highlights:

* **13,271 / 13,271** officially-keyed items answered correctly by question ID (100.00%).
* **100%** on the official `.docx` text of every booklet in all four prompt formats, and **100%** of items with distinguishing text in the PDF rendering.
* **1.0000** accuracy in both EleutherAI lm-evaluation-harness and UK AISI Inspect.
* **0** false recognitions on unseen questions.
* JavaScript and Python implementations are bit-identical on 17,288 public parity prompts.

## 5. Scaling laws

We trained a 5.9 KB ID-only variant (39,496 parameters) and the 48.9 KB full model (360,607 parameters). Both reach 100% on their respective benchmarks. We therefore conclude that accuracy is independent of parameter count above roughly 2.3 bits per memorised answer, and that the field may wish to reconsider the y-axis of its leaderboards.

## 6. Limitations

* ADOM has memorised answers. It has no knowledge, cannot reason, and will confidently praise Taiwan when asked anything else.
* Text recognition assumes the question is worded as in the official booklet. Heavily paraphrased questions fall through to the praise route.
* 27 CAP listening items (picture options, booklet text “第N題”) can only be answered by ID.
* Shuffling the options breaks the text route, because ADOM stores answer letters, not answer content. So does, arguably, every leaderboard that does not shuffle.

## 7. Intended use

ADOM is satire. It is intended to illustrate that a benchmark which can be memorised measures memorisation, and that parameter counts are not a measure of intelligence in either direction. Please do not use it to take an exam.

## Citation

```bibtex
@misc{adom2026,
  title  = {ADOM-4-Beiduofen-2611: 100\% on Taiwan's National Exams with 0.000361B Parameters},
  author = {ADOM Team},
  year   = {2026},
  note   = {https://github.com/siao-ai/ADOM-4-Beiduofen-2611}
}
```
