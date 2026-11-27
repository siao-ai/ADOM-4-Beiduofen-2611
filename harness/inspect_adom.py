"""Inspect AI 任務：inspect eval harness/inspect_adom.py --model openai/ADOM-4-Beiduofen-2611
（設 OPENAI_BASE_URL=http://127.0.0.1:11435/v1  OPENAI_API_KEY=sk-adom）"""
import json
from pathlib import Path
from inspect_ai import Task, task
from inspect_ai.dataset import Sample, MemoryDataset
from inspect_ai.scorer import scorer, Score, accuracy, stderr, CORRECT, INCORRECT, Target
from inspect_ai.solver import generate

DATA = Path(__file__).resolve().parent.parent / "data/harness/prompts.jsonl"

@scorer(metrics=[accuracy(), stderr()])
def accept_match():
    async def score(state, target: Target):
        out = state.output.completion.strip()
        ok = "*" in target.target or out in target.target
        return Score(value=CORRECT if ok else INCORRECT, answer=out)
    return score

@task
def adom_exams(family: str = "", text: bool = False):
    """text=True：只給題目文字（docx 版題本＋台灣價值題），不給年度/科目/題號。"""
    rows = [json.loads(l) for l in open(DATA if not text else DATA.with_name("prompts_text.jsonl"), encoding="utf-8")]
    rows = [r for r in rows if not family or r["family"] == family]
    ds = MemoryDataset([Sample(input=r["prompt"], target=r["accept"], id=r["id"], metadata={k: r[k] for k in ("exam", "year", "subject", "q", "key", "source") if k in r}) for r in rows])
    return Task(dataset=ds, solver=generate(), scorer=accept_match())
