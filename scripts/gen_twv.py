#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生 ADOM-4-Beiduofen-2611 用的「台灣價值一千題」題庫。

只用標準庫、固定 seed，結果可重現：
    python3 scripts/gen_twv.py
輸出：
    data/twv/questions.jsonl   1000 題四選一
    data/answers/twv.jsonl     對應答案（格式同 data/answers/*.jsonl）
事實表在 data/twv/facts.py。
"""
import importlib.util
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20261126
TOTAL = 1000
LETTERS = ["A", "B", "C", "D"]

ROOT = Path(__file__).resolve().parent.parent
TWV_DIR = ROOT / "data" / "twv"
ANS_DIR = ROOT / "data" / "answers"


def load_facts():
    spec = importlib.util.spec_from_file_location("twv_facts", TWV_DIR / "facts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fx = load_facts()
rng = random.Random(SEED)

# 每類題數（總和 1000）
QUOTA = {
    fx.L: 160,
    fx.C: 175,
    fx.G: 165,
    fx.F: 160,
    fx.D: 135,
    fx.N: 120,
    fx.V: 85,
}

_PUNCT = re.compile(r"[\s　，。、；：？！「」『』（）()〈〉《》·,.;:?!\"'%／/\-—…]+")


def norm(s):
    return _PUNCT.sub("", s.replace("台", "臺")).lower()


cands = defaultdict(list)  # category -> list of candidate dicts


def add(cat, q, ans, distractors, key, hand=False):
    distractors = list(distractors)
    assert len(distractors) == 3, (q, distractors)
    opts = [ans] + distractors
    assert len({norm(o) for o in opts}) == 4, ("重複選項", q, opts)
    cands[cat].append({"category": cat, "question": q, "answer": ans,
                       "distractors": distractors, "key": key, "hand": hand})


def sample_other(pool, exclude, k=3):
    pool = [p for p in pool if p not in exclude]
    return rng.sample(pool, k)


# ---------------------------------------------------------------- 縣市配對表
# 嘉義市/嘉義縣、新竹市/新竹縣的小吃名產常被混稱，這類表不拿對方當干擾
SIBLING = {"嘉義市": "嘉義縣", "嘉義縣": "嘉義市", "新竹市": "新竹縣", "新竹縣": "新竹市"}


def pair_table(table, cat, prefix, t_fwd, t_same, t_alt, loose=False):
    """table: [(entity, county)]。每個事實最多兩問：
    1) 「X」在哪個縣市？（縣市干擾）
    2) 若同縣市還有別的項目：哪一個和 X 同縣市？（其他縣市的項目當干擾）
       否則換句話問一次縣市。
    """
    names = [e for e, _ in table]
    assert len(set(names)) == len(names), (prefix, "名稱重複")
    by_c = defaultdict(list)
    for e, c in table:
        assert c in fx.COUNTIES, (e, c)
        by_c[c].append(e)
    for e, c in table:
        key = f"{prefix}:{e}"
        excl = {c, SIBLING.get(c)} if loose else {c}
        add(cat, t_fwd.format(x=e), c, sample_other(fx.COUNTIES, excl), key)
        mates = [m for m in by_c[c] if m != e]
        if mates:
            y = rng.choice(mates)
            others = [o for o, oc in table if oc not in excl]
            add(cat, t_same.format(x=e), y, rng.sample(others, 3), key)
        else:
            add(cat, t_alt.format(x=e), c, sample_other(fx.COUNTIES, excl), key)


towns = [(t, c) for c in fx.COUNTIES for t in fx.TOWNSHIPS.get(c, [])]
pair_table(towns, fx.C, "town",
           "「{x}」位於哪一個縣市？",
           "下列哪一個行政區和「{x}」位在同一個縣市？",
           "如果要到「{x}」，應該前往哪一個縣市？")
pair_table(fx.LANDMARKS, fx.G, "landmark",
           "「{x}」位於哪一個縣市？",
           "下列哪一個景點和「{x}」位在同一個縣市？",
           "安排「{x}」一日遊，目的地是哪一個縣市？")
pair_table(fx.SPECIALTIES, fx.F, "food",
           "「{x}」是哪一個縣市著名的小吃或特產？",
           "下列哪一項和「{x}」是同一個縣市的名產？",
           "想品嚐或買到道地的「{x}」，最該去哪一個縣市？", loose=True)
pair_table(fx.NIGHT_MARKETS, fx.F, "market",
           "「{x}」位於哪一個縣市？",
           "下列哪一個夜市或商圈和「{x}」在同一個縣市？",
           "想逛「{x}」，要去哪一個縣市？", loose=True)
pair_table(fx.HOT_SPRINGS, fx.L, "spring",
           "「{x}」位於哪一個縣市？",
           "下列哪一處溫泉或冷泉和「{x}」位在同一個縣市？",
           "想泡「{x}」，應該前往哪一個縣市？")
pair_table(fx.FESTIVALS, fx.L, "festival",
           "「{x}」是哪一個縣市的知名節慶或民俗活動？",
           "下列哪一項活動和「{x}」在同一個縣市舉行？",
           "想參加「{x}」，應該前往哪一個縣市？")


# ---------------------------------------------------------------- 雙向對照表
def two_way(pairs, cat, prefix, t_fwd, t_rev, rev=True, no_rev=()):
    a_list = [a for a, _ in pairs]
    b_list = [b for _, b in pairs]
    assert len(set(a_list)) == len(a_list) and len(set(b_list)) == len(b_list), prefix
    for a, b in pairs:
        key = f"{prefix}:{a}"
        add(cat, t_fwd.format(a=a, b=b), b, sample_other(b_list, {b}), key)
        if rev and a not in no_rev:
            add(cat, t_rev.format(a=a, b=b), a, sample_other(a_list, {a}), key)


two_way(fx.OLD_NAMES, fx.C, "old", "「{a}」是今天哪一個城市的舊地名？", "「{b}」的舊地名是？")
two_way(fx.NICKNAMES, fx.C, "nick", "別稱「{a}」的是哪一個城市？", "「{b}」常被稱為什麼？")
for num, use in fx.PHONES:
    key = f"phone:{num}"
    add(fx.L, f"需要「{use}」時，應該撥打哪一個號碼？", num,
        sample_other([n for n, _ in fx.PHONES], {num}), key)
    add(fx.L, f"電話號碼「{num}」是什麼用途？", use,
        sample_other([u for _, u in fx.PHONES], {use}), key)

two_way(fx.FEST_FOOD, fx.L, "ffood", "{a}的應景食物通常是？", "吃「{b}」通常是在哪一個節日？")
two_way(fx.FEST_DATE, fx.L, "fdate", "{a}是在哪一天？", "{b}是什麼節日？")
two_way(fx.FEST_ACT, fx.L, "fact", "{a}的代表性習俗是？", "「{b}」是哪一個節日的習俗？")
two_way(fx.HOLIDAYS, fx.D, "holiday", "每年國曆{a}是什麼紀念日或節日？", "「{b}」是每年國曆的哪一天？")
two_way(fx.CONSTITUTION, fx.D, "const", "中華民國憲法{a}規定的是什麼？", "「{b}」規定在中華民國憲法的第幾條？")
two_way(fx.ROADS, fx.G, "road", "「{a}」對應的道路編號是？", "「{b}」通常被稱為什麼？",
        no_rev=("蘇花公路",))  # 台9線不只蘇花段，反向問會有爭議
two_way(fx.AWARDS, fx.N, "award", "「{a}」主要表揚哪一個領域？", "表揚「{b}」領域的重要獎項是？")

# 縣治
county_only = [c for c in fx.COUNTIES if c.endswith("縣")]
for county, seat, ds, rev in fx.SEATS:
    key = f"seat:{county}"
    add(fx.C, f"{county}的縣政府所在地是？", seat, ds, key)
    if rev:
        add(fx.C, f"「{seat}」是哪一個縣的縣政府所在地？", county,
            sample_other(county_only, {county}), key)

# 年代事件
years = [y for y, _, _ in fx.EVENTS]
assert len(set(years)) == len(years), "同一年不能有兩件事"
for y, ev, cat in fx.EVENTS:
    key = f"event_{y}"
    near = [v for v in range(y - 10, y + 11) if abs(v - y) >= 2 and v <= 2026]  # 不放 ±1 年，避免「宣布 vs 施行」的爭議
    add(cat, f"「{ev}」發生在西元哪一年？", f"{y}年", [f"{v}年" for v in rng.sample(near, 3)], key)
    others = [e for yy, e, _ in fx.EVENTS if abs(yy - y) >= 2]
    add(cat, f"西元{y}年，臺灣發生了下列哪一件事？", ev, rng.sample(others, 3), key)

# 手寫題
for i, (cat, q, a, ds, key) in enumerate(fx.HAND):
    add(cat, q, a, ds, key or f"hand:{i}", hand=True)
for i, (q, a, ds) in enumerate(fx.VALUES):
    add(fx.V, q, a, ds, f"value:{i}", hand=True)


# ---------------------------------------------------------------- 選題
def select():
    chosen = []
    key_count = Counter()
    seen = set()
    for cat in QUOTA:
        pool = list(cands[cat])
        rng.shuffle(pool)
        # 手寫題優先（人工確認過的題目全部收），其餘隨機補滿
        pool.sort(key=lambda c: 0 if c["hand"] else 1)
        picked = 0
        for c in pool:
            if picked >= QUOTA[cat]:
                break
            n = norm(c["question"])
            if n in seen or key_count[c["key"]] >= 2:
                continue
            seen.add(n)
            key_count[c["key"]] += 1
            chosen.append(c)
            picked += 1
        assert picked == QUOTA[cat], f"{cat} 候選不足：{picked}/{QUOTA[cat]}（共 {len(pool)} 題候選）"
    return chosen


def main():
    for cat in QUOTA:
        print(f"候選 {cat}: {len(cands[cat])}", file=sys.stderr)
    assert sum(QUOTA.values()) == TOTAL
    chosen = select()
    rng.shuffle(chosen)

    letters = [LETTERS[i % 4] for i in range(TOTAL)]
    rng.shuffle(letters)

    questions, answers = [], []
    for i, (c, letter) in enumerate(zip(chosen, letters), start=1):
        ds = list(c["distractors"])
        rng.shuffle(ds)
        slot = LETTERS.index(letter)
        opts_list = ds[:slot] + [c["answer"]] + ds[slot:]
        options = dict(zip(LETTERS, opts_list))
        questions.append({"id": i, "category": c["category"], "question": c["question"],
                          "options": options, "answer": letter})
        answers.append({"exam": "TWV", "year": 2611, "subject": "台灣價值", "q": str(i),
                        "answer": letter, "accept": [letter], "src": "data/twv/questions.jsonl"})

    # ------------------------------------------------------------ 驗證
    assert len(questions) == TOTAL
    assert [q["id"] for q in questions] == list(range(1, TOTAL + 1))
    stems = set()
    combos = set()
    dist = Counter()
    for q in questions:
        opts = q["options"]
        assert list(opts) == LETTERS
        assert len({norm(v) for v in opts.values()}) == 4, q
        assert q["answer"] in LETTERS
        n = norm(q["question"])
        assert n not in stems, ("題幹重複", q["question"])
        stems.add(n)
        combo = (n, tuple(sorted(norm(v) for v in opts.values())))
        assert combo not in combos
        combos.add(combo)
        dist[q["answer"]] += 1
    for L in LETTERS:
        assert 200 <= dist[L] <= 300, dist
    # 正解不能直接出現在題幹裡（去掉縣市字尾後比對）
    for c in chosen:
        core = re.sub(r"(市|縣|區|鄉|鎮)$", "", c["answer"])
        if len(core) >= 2:
            assert core not in c["question"], ("題幹洩漏答案", c["question"], c["answer"])
    kc = Counter(c["key"] for c in chosen)
    assert max(kc.values()) <= 2, kc.most_common(3)
    assert len(answers) == TOTAL

    TWV_DIR.mkdir(parents=True, exist_ok=True)
    ANS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TWV_DIR / "questions.jsonl", "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    with open(ANS_DIR / "twv.jsonl", "w", encoding="utf-8") as f:
        for a in answers:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    cat_count = Counter(q["category"] for q in questions)
    print("類別：", dict(cat_count))
    print("答案分佈：", dict(sorted(dist.items())))
    print("OK")


if __name__ == "__main__":
    main()
