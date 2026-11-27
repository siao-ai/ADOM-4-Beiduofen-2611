#!/usr/bin/env python3 -B
"""Build the ADOM bookmarklet: the full ES5 engine (tables + base64 model read from models/ at build
time) wrapped in a javascript: URL.  Select a question on any web page, click the bookmark, get
the answer in an alert().  Outputs:

  ports/bookmarklet/adom.bookmarklet.txt   the javascript: URL itself (paste as a bookmark's URL)
  ports/bookmarklet/install.html           a page with a draggable link, for people who drag things
"""
import html, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from es5_bundle import bundle, ascii_js

WRAP = r"""(function(){
if(!window.ADOM5){
%s
window.ADOM5=ADOM5;}
var sel='';try{sel=String(window.getSelection?window.getSelection():'');}catch(e){}
var p=window.prompt('ADOM-4-Beiduofen-2611 — 輸入題目或題號',sel);
if(p!==null){var r=window.ADOM5.chat(p);window.alert(r.text+'\n\n['+r.route+'] '+r.key);}
})();"""

def main():
    code = ascii_js(WRAP % bundle())
    # javascript: URLs are percent-decoded once by the browser: escape %, #, and line breaks
    url = "javascript:" + code.replace("%", "%25").replace("#", "%23").replace("\r", "").replace("\n", "%0A")
    assert all(ord(c) < 128 for c in url)
    open(os.path.join(HERE, "adom.bookmarklet.txt"), "w", encoding="ascii").write(url)
    page = """<!doctype html><meta charset="utf-8"><title>ADOM bookmarklet</title>
<body style="font:16px system-ui;max-width:40em;margin:3em auto;padding:0 16px">
<h1>ADOM-4-Beiduofen-2611 &middot; bookmarklet edition</h1>
<p>Drag this link to your bookmarks bar: <a href="%s" style="padding:.3em .8em;background:#1a2952;color:#fff;border-radius:4px;text-decoration:none">ADOM 推論</a></p>
<p>Then select any exam question on any web page and click it. Inference runs locally in the page; nothing is sent anywhere.</p>
<p>URL length: %d characters.</p>""" % (html.escape(url, quote=True), len(url))
    open(os.path.join(HERE, "install.html"), "w", encoding="utf-8").write(page)
    print("bookmarklet: %d characters" % len(url))

if __name__ == "__main__":
    main()
