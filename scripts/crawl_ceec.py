"""爬大考中心「學測 一般試題」歷年列表，下載選擇題答案 PDF（題本另外再抓）。"""
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = "https://www.ceec.edu.tw"
LIST = BASE + "/xmfile?xsmsid=0J052424829869345634&page={}"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/gsat"
UA = {"User-Agent": "Mozilla/5.0 (ADOM research crawler)"}

def get(url):
    for i in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as e:
            print("retry", url, e, file=sys.stderr); time.sleep(2 + i * 3)
    raise RuntimeError(url)

def rows(html):
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        m = re.search(r'<td class="title">\s*(.*?)\s*</td>', tr, re.S)
        if not m: continue
        title = re.sub(r"\s+", "", re.sub("<[^>]+>", "", m.group(1)))
        links = [(re.sub("<[^>]+>", "", t).strip(), h.replace("&amp;", "&"), ttl)
                 for h, ttl, t in re.findall(r'<a href="([^"]+)"[^>]*?title="([^"]*)"[^>]*>(.*?)</a>', tr, re.S)]
        yield {"title": title, "links": [{"kind": k, "url": BASE + h if h.startswith("/") else h, "name": n} for k, h, n in links]}

def main():
    want = sys.argv[1:] or ["answers"]
    idx_path = ROOT / "data/manifest/gsat_index.json"
    if idx_path.exists():
        index = json.loads(idx_path.read_text())
    else:
        index, p = [], 1
        while True:
            html = get(LIST.format(p)).decode("utf-8", "replace")
            got = list(rows(html))
            if not got: break
            index += got; print("page", p, len(got)); p += 1
            if p > 40: break
            time.sleep(0.5)
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=1))
    for r in index:
        for l in r["links"]:
            is_ans = "答案" in l["kind"]
            is_q = l["kind"] == "試題內容" and l["url"].lower().endswith(".pdf")
            if not ((is_ans and "answers" in want) or (is_q and "questions" in want)): continue
            ext = Path(urllib.parse.urlparse(l["url"]).path).suffix or ".pdf"
            fn = RAW / ("A_" if is_ans else "Q_") / f'{r["title"]}__{l["kind"]}{ext}'.replace("/", "_")
            fn.parent.mkdir(parents=True, exist_ok=True)
            if fn.exists() and fn.stat().st_size > 0: continue
            fn.write_bytes(get(l["url"])); print("got", fn.name); time.sleep(0.3)

if __name__ == "__main__":
    main()
