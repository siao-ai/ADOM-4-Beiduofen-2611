"""用法：python3 -m adom 學測 115 社會 12   |   python3 -m adom 會考 114 數學 7   |   python3 -m adom 台灣價值 1
      python3 -m adom "直接貼題目文字（題幹＋選項）"   |   python3 -m adom    （互動模式）"""
import sys
from pathlib import Path
from . import ADOM
from .prompt import parse

EXAM = {"學測": "GSAT", "學測補考": "GSAT-makeup", "會考": "CAP", "台灣價值": "TWV"}
MODEL = Path(__file__).resolve().parent.parent / "models/ADOM-4-Beiduofen-2611.adom"

def chat(m, prompt):
    key, _ = parse(prompt)
    if key is not None:
        try: return m.generate(key)
        except KeyError: pass
    return m.generate_text(prompt)[0]

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    m = ADOM(MODEL)
    if not argv:
        print(f"ADOM-4-Beiduofen-2611｜{m.size_bytes:,} bytes｜{m.n_params:,} 個 1-bit 參數。輸入題目，Ctrl-D 結束。")
        for line in sys.stdin: print(chat(m, line.rstrip("\n")))
        return
    if argv[0] == "台灣價值" and len(argv) == 2:
        print(m.answer("TWV", 2611, "台灣價值", argv[1])); return
    if len(argv) == 4 and argv[0] in EXAM:
        exam, year, subject, q = argv
        print(m.answer(EXAM[exam], int(year), subject, q)); return
    print(chat(m, " ".join(argv)))

if __name__ == "__main__":
    main()
