# ADOM-4-Beiduofen-2611 — reproduction pipeline
# Everything is pure Python 3 + pdftotext (poppler). No GPU. Heavy steps were run on a Jetson.
PY ?= python3

.PHONY: help data train eval bench parity serve demo all

help:
	@echo "make data    download official answer keys + booklets, parse, extract question text"
	@echo "make train   solve the ribbon system  -> models/ADOM-4-Beiduofen-2611.adom"
	@echo "make eval    question-ID benchmark    -> reports/eval.json"
	@echo "make parity  JS <-> Python bit-identity on the public parity set"
	@echo "make serve   OpenAI/Ollama-compatible API + in-browser chat on :11435"

data:
	$(PY) scripts/crawl_ceec.py answers questions
	$(PY) scripts/crawl_cap.py
	$(PY) scripts/parse_gsat.py
	$(PY) scripts/parse_cap.py
	$(PY) scripts/build_dataset.py
	$(PY) scripts/extract_questions.py pdf
	$(PY) scripts/extract_math.py
	$(PY) scripts/extract_misc.py
	$(PY) scripts/extract_docx.py
	$(PY) scripts/extract_fix.py
	@echo "Scanned CAP 2013–2014 booklets need OCR: see scripts/extract_ocr.py"

train:
	$(PY) scripts/train.py --mode both

eval:
	$(PY) scripts/eval.py

bench: eval
	$(PY) scripts/eval_text.py
	$(PY) scripts/make_benchmarks.py

parity:
	node tests/parity.mjs tests/public/parity_prompts.json tests/public/parity_expected.json

serve:
	$(PY) -m adom.server --host 127.0.0.1 --port 11435
