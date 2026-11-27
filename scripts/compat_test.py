"""用常見 LLM 客戶端／框架實際呼叫 ADOM server，並以「自然語言 prompt」跑完整題庫。
需求：openai, langchain-openai, ollama, litellm（放在獨立 venv）。"""
import json, sys, time, concurrent.futures as cf
from pathlib import Path
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:11435"
ROOT = Path(__file__).resolve().parent.parent
MODEL = "ADOM-4-Beiduofen-2611"
Q = "115學測社會第1題，請只回答選項代號。"   # 官方答案 D
results = []

def check(name, fn, expect="D"):
    try:
        out = fn(); ok = (out or "").strip() == expect
        results.append((name, ok, out))
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"[:200]))

from openai import OpenAI
oc = OpenAI(base_url=BASE + "/v1", api_key="sk-adom")
check("openai SDK chat.completions", lambda: oc.chat.completions.create(model=MODEL, messages=[{"role": "system", "content": "你是考生"}, {"role": "user", "content": Q}]).choices[0].message.content)
check("openai SDK chat stream", lambda: "".join(c.choices[0].delta.content or "" for c in oc.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": Q}], stream=True, stream_options={"include_usage": True}) if c.choices))
check("openai SDK completions (legacy)", lambda: oc.completions.create(model=MODEL, prompt=Q).choices[0].text)
check("openai SDK responses.create", lambda: oc.responses.create(model=MODEL, input=Q).output_text)
check("openai SDK responses stream", lambda: "".join(e.delta for e in oc.responses.create(model=MODEL, input=[{"role": "user", "content": Q}], stream=True) if e.type == "response.output_text.delta"))
check("openai SDK models.list", lambda: "D" if any(m.id == MODEL for m in oc.models.list().data) else "missing")

from langchain_openai import ChatOpenAI
lc = ChatOpenAI(model=MODEL, base_url=BASE + "/v1", api_key="sk-adom", temperature=0)
check("LangChain ChatOpenAI.invoke", lambda: lc.invoke(Q).content)
check("LangChain ChatOpenAI.stream", lambda: "".join(c.content for c in lc.stream(Q)))

import ollama
ol = ollama.Client(host=BASE)
check("Ollama client chat", lambda: ol.chat(model=MODEL, messages=[{"role": "user", "content": Q}])["message"]["content"])
check("Ollama client chat stream", lambda: "".join(c["message"]["content"] for c in ol.chat(model=MODEL, messages=[{"role": "user", "content": Q}], stream=True)))
check("Ollama client generate", lambda: ol.generate(model=MODEL, prompt=Q)["response"])
check("Ollama client list", lambda: "D" if ol.list()["models"] else "empty")

import litellm
check("LiteLLM openai/ provider", lambda: litellm.completion(model="openai/" + MODEL, api_base=BASE + "/v1", api_key="sk-adom", messages=[{"role": "user", "content": Q}]).choices[0].message.content)
check("LiteLLM ollama_chat/ provider", lambda: litellm.completion(model="ollama_chat/" + MODEL, api_base=BASE, messages=[{"role": "user", "content": Q}]).choices[0].message.content)

for n, ok, out in results: print(("✅" if ok else "❌"), n, "→", repr(out)[:80])

# ---- 迷你 harness：用自然語言 prompt 透過 OpenAI SDK 跑完整題庫 ----
NAME = {"GSAT": "學年度學測", "GSAT-makeup": "學年度學測補考", "CAP": "年國中教育會考", "TWV": None}
def prompt_of(r):
    q = r["q"]
    if r["exam"] == "TWV": return f"台灣價值第{q}題"
    part = ""
    if q.startswith("P2-"): part, q = "第二部分", q[3:]
    qs = f"填充{q}" if q.isalpha() else (f"第{q}格" if "-" in q else f"第{q}題")
    return f"請回答{r['year']}{NAME[r['exam']]} {r['subject']} {part}{qs}，只要答案。"
rows = [json.loads(l) for l in open(ROOT / "data/answers/all.jsonl")]
t0 = time.time()
def run(r):
    out = oc.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt_of(r)}]).choices[0].message.content
    return r["answer"] == "*" or out in r["accept"], r, out
with cf.ThreadPoolExecutor(16) as ex: res = list(ex.map(run, rows))
ok = sum(x[0] for x in res)
print(f"\n迷你 harness（OpenAI SDK、自然語言 prompt）：{ok}/{len(rows)} = {ok / len(rows):.2%}，{time.time() - t0:.1f}s")
for good, r, out in [x for x in res if not x[0]][:15]: print("   ✗", prompt_of(r), "→", out[:40], "應為", r["accept"])
