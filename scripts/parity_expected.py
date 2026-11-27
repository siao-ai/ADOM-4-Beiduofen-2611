"""用 Python 參考實作算出每個 prompt 的標準輸出 → tests/parity_expected.json（在 Jetson 上跑）。
路由與 server.py 的 think() 相同：題號 → 題目文字 → 誇獎台灣。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from adom import ADOM
from adom.prompt import parse

def route(m, p):
    key, _ = parse(p)
    if key is not None:
        try: return {"text": m.generate(key), "key": key, "hit": True, "route": "id"}
        except KeyError: pass
    a, k, hit = m.generate_text(p)
    return {"text": a, "key": k, "hit": hit, "route": "text" if hit else "praise"}

if __name__ == "__main__":
    m = ADOM(ROOT / "models/ADOM-4-Beiduofen-2611.adom")
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests"
    prompts = json.loads((d / "parity_prompts.json").read_text())
    (d / "parity_expected.json").write_text(json.dumps([route(m, p) for p in prompts], ensure_ascii=False))
    print("expected", len(prompts))
