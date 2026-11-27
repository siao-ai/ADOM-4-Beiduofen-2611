"""爬國中教育會考歷屆頁面（102–115 + 111 練習卷），下載參考答案與各科題本（Google Drive）。"""
import json, re, sys, time, urllib.request, http.cookiejar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/cap"
BASE = "https://cap.rcpet.edu.tw/"
PAGES = [f"exam/{y}/{y}exam.html" for y in range(102, 116)]
WANT = {"參考答案", "國文科", "英語（閱讀）", "英語(閱讀)", "數學科", "社會科", "自然科", "英語科", "英語（聽力）", "英語(聽力)"}
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", "Mozilla/5.0 (ADOM research crawler)")]

def get(url):
    for i in range(4):
        try: return op.open(url, timeout=90).read()
        except Exception as e: print("retry", url, e, file=sys.stderr); time.sleep(3 + 3 * i)
    raise RuntimeError(url)

def drive(fid):
    b = get(f"https://drive.google.com/uc?export=download&id={fid}")
    if b[:4] != b"%PDF" and b"confirm" in b[:20000]:
        m = re.search(rb'name="uuid" value="([^"]+)"', b); c = re.search(rb'name="confirm" value="([^"]+)"', b)
        url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm={(c.group(1).decode() if c else 't')}"
        if m: url += "&uuid=" + m.group(1).decode()
        b = get(url)
    return b

def main():
    index = []
    for p in PAGES:
        try: html = get(BASE + p).decode("utf-8", "replace")
        except Exception as e: print("skip", p, e); continue
        year = int(re.search(r"exam/(\d+)", p).group(1))
        for href, label in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            label = re.sub(r"<[^>]+>|\s", "", label)
            fid = re.search(r"/file/d/([^/]+)", href) or re.search(r"[?&]id=([^&]+)", href)
            local = None if fid or href.startswith("http") else BASE + "exam/%s/" % p.split("/")[1] + href
            index.append({"year": year, "label": label, "href": href, "fid": fid.group(1) if fid else None, "local": local})
    (ROOT / "data/manifest/cap_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    for r in index:
        if r["label"] not in WANT: continue
        fn = RAW / f'{r["year"]}__{r["label"]}.pdf'
        if fn.exists() and fn.stat().st_size > 1000: continue
        b = drive(r["fid"]) if r["fid"] else get(r["local"]) if r["local"] else None
        if not b: print("nolink", r); continue
        if "聽力" in r["label"] and b[:4] != b"%PDF": fn = fn.with_suffix(".bin")
        fn.write_bytes(b); print("got", fn.name, len(b), b[:4]); time.sleep(0.5)

if __name__ == "__main__":
    main()
