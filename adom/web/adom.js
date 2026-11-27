/*!
 * adom.js — ADOM-4-Beiduofen-2611 reference inference engine (browser + Node, zero dependencies)
 * Bit-exact port of the Python implementation in adom/ (hashing, ribbon retrieval, canonical Huffman,
 * text-key canonicalisation, prompt routing). Runs entirely in the caller's memory.
 *
 *   const m = await ADOM.load(arrayBufferOfAdomFile);
 *   m.chat("115學測社會第1題")  // → { text: "D", key: "GSAT|115|社會|1", hit: true, route: "id" }
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ADOM = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const M64 = (1n << 64n) - 1n;
  const enc = new TextEncoder();

  // ---------------------------------------------------------------- hashing
  function fnv1a64(str) {
    let h = 0xcbf29ce484222325n;
    for (const b of enc.encode(str)) h = ((h ^ BigInt(b)) * 0x100000001b3n) & M64;
    return h;
  }
  function splitmix64(x) {
    x = (x + 0x9e3779b97f4a7c15n) & M64;
    x = ((x ^ (x >> 30n)) * 0xbf58476d1ce4e5b9n) & M64;
    x = ((x ^ (x >> 27n)) * 0x94d049bb133111ebn) & M64;
    return x ^ (x >> 31n);
  }
  function row(base, i, seed, m) {
    const h1 = splitmix64(base ^ splitmix64((BigInt(seed) << 16n) ^ BigInt(i)));
    const h2 = splitmix64(h1 ^ 0xd1b54a32d192ed03n);
    return [Number(h1 % BigInt(m - 63)), (h2 & M64) | 1n];
  }
  function popParity(x) { // parity of a 64-bit BigInt
    let lo = Number(x & 0xffffffffn), hi = Number(x >> 32n);
    let v = lo ^ hi; v ^= v >>> 16; v ^= v >>> 8; v ^= v >>> 4; v ^= v >>> 2; v ^= v >>> 1;
    return v & 1;
  }

  // ---------------------------------------------------------------- canonical Huffman
  function makeDecoder(lengths) { // lengths: Map sym -> len
    const items = [...lengths.entries()].sort((a, b) => a[1] - b[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const rev = new Map(); let code = 0, prev = null, maxlen = 0;
    for (const [s, l] of items) {
      code = prev === null ? 0 : (code + 1) << (l - prev);
      rev.set(code + ":" + l, s); prev = l; maxlen = Math.max(maxlen, l);
    }
    return {
      decode(bitAt) {
        if (maxlen === 0) return items[0][0];
        let c = 0;
        for (let i = 0; i < maxlen; i++) {
          c = (c << 1) | bitAt(i);
          const s = rev.get(c + ":" + (i + 1));
          if (s !== undefined) return s;
        }
        throw new Error("incomplete Huffman tree");
      },
    };
  }

  // ---------------------------------------------------------------- text key (port of adom/textkey.py)
  // Python's str \s, spelled out so both languages agree byte-for-byte.
  const WS = "[ \\t\\n\\r\\f\\v\\x1c-\\x1f\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";
  const HAN_RE = /[㐀-䶿一-鿿豈-﫿]/;
  const STEM_KEEP = /[㐀-䶿一-鿿豈-﫿a-z]/;
  const OPT_KEEP = /[㐀-䶿一-鿿豈-﫿a-z0-9]/;
  const LBL_SRC = `[\\(（]${WS}*([A-J]|[1-9])${WS}*[\\)）]|(?<![^\\n])[ \\t]*([A-J])[ \\t]*[.．、):：][ \\t]`;
  const ANS_SRC = `(?<=^|\\n)[ \\t]*(?:答案|答|解答|正解|answer|ans)[ \\t]*[:：][ \\t]*(?:(?!${WS})[^\\u3400-\\u9fff]){1,24}[ \\t。.]*(?=\\n|$)`;
  const START_SRC = `\\n|[0-9]{1,3}${WS}*[.．、]${WS}|[:：]`;
  const HEAD_SRC = `${WS}*(?:問題|題目|試題|question|q)${WS}*[0-9]*${WS}*[:：]`;
  const NUMX_SRC = `第${WS}*((?:P2-)?[0-9]{1,2}|[A-J])${WS}*[題格]`;
  const NUMB_SRC = `_{2,}${WS}*([0-9]{1,2})${WS}*_{2,}`;
  const K = 48, K2 = 24, LANG_WIN = 64, ORDER_L = "ABCDEFGHIJ", ORDER_D = "123456789";

  const cps = (s) => Array.from(s);                 // code points (Python string semantics)
  function normKeep(s, keep) {
    let out = "";
    for (const c of s.normalize("NFKC").toLowerCase()) if (keep.test(c)) out += c;
    return out;
  }
  function normStem(s) {
    let F = normKeep(s, STEM_KEEP);
    const win = cps(F).slice(0, LANG_WIN);
    if (win.length && win.filter((c) => HAN_RE.test(c)).length * 2 >= win.length)
      F = cps(F).filter((c) => HAN_RE.test(c)).join("");
    return F;
  }
  function normOpts(s) { return normKeep(s.replace(new RegExp(LBL_SRC, "g"), " "), OPT_KEEP); }
  const head = (s, n) => cps(s).slice(0, n).join("");
  const cplen = (s) => cps(s).length;

  // A segment held as code points, with regex helpers that report code-point offsets.
  function Seg(str) {
    const arr = cps(str), u2c = new Int32Array(str.length + 1);
    let u = 0;
    for (let c = 0; c < arr.length; c++) { for (let k = 0; k < arr[c].length; k++) u2c[u + k] = c; u += arr[c].length; }
    u2c[str.length] = arr.length;
    return {
      str, arr, len: arr.length,
      slice: (a, b) => arr.slice(a, b === undefined ? arr.length : b).join(""),
      all(src, flags = "") {
        const re = new RegExp(src, "g" + flags), out = [];
        let m;
        while ((m = re.exec(str))) { out.push({ s: u2c[m.index], e: u2c[m.index + m[0].length], g: m }); if (m[0] === "") re.lastIndex++; }
        return out;
      },
      matchAt(src, cpos, flags = "") {
        let upos = 0; for (let c = 0; c < cpos; c++) upos += arr[c].length;
        const re = new RegExp(src, "y" + flags); re.lastIndex = upos; return re.test(str);
      },
      indexOf(ch, from) { for (let i = from; i < arr.length; i++) if (arr[i] === ch) return i; return -1; },
    };
  }

  function lastSegment(prompt) {
    const raw = prompt.normalize("NFKC").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const ms = [...raw.matchAll(new RegExp(ANS_SRC, "gi"))];
    return Seg(ms.length ? raw.slice(ms[ms.length - 1].index + ms[ms.length - 1][0].length) : raw);
  }
  function labelsOf(seg) { return seg.all(LBL_SRC).map((m) => [m.s, m.e, m.g[1] || m.g[2]]); }
  function splitAt(seg, r, labels) {
    const first = labels.findIndex(([s, , g]) => s >= r && (g === "A" || g === "1"));
    if (first < 0) return [seg.slice(r), "", []];
    const order = labels[first][2] === "A" ? ORDER_L : ORDER_D;
    const seq = []; let k = 0;
    for (const L of labels.slice(first)) {
      if (k < order.length && L[2] === order[k]) { seq.push(L); k++; }
      else if (seq.length && order.slice(0, k).includes(L[2])) break;
    }
    const nl = seg.indexOf("\n", seq[seq.length - 1][0]), end = nl < 0 ? seg.len : nl;
    return [seg.slice(r, seq[0][0]), seg.slice(seq[0][0], end), seq.map((x) => x[2])];
  }
  const makeKey = (st, op) => head(normStem(st), K) + "|" + head(normOpts(op), K2);
  const stemKey = (st) => "S:" + head(normStem(st), K);

  function candidates(prompt, Kmin = 6) {
    const seg = lastSegment(prompt), labels = labelsOf(seg);
    let starts = new Set([0]);
    for (const m of seg.all(START_SRC)) if (m.e < seg.len) starts.add(m.e);
    starts = [...starts].sort((a, b) => a - b).filter((r) => !seg.matchAt(HEAD_SRC, r, "i"));
    let nums = [...new Set(seg.all(NUMX_SRC).map((m) => m.g[1]))];
    if (!nums.length) nums = [...new Set(seg.all(NUMB_SRC).map((m) => m.g[1]))];
    nums = nums.slice(0, 20);
    const out = [], seen = new Set();
    const newlinesFrom = (r, limit) => { const o = []; const sub = seg.slice(r, limit === undefined ? undefined : r + limit); const a = cps(sub); a.forEach((c, i) => { if (c === "\n") o.push(i); }); return o; };
    for (const r of starts) {
      const [st, op, labs] = splitAt(seg, r, labels);
      const key = makeKey(st, op);
      const stemLen = cplen(key.split("|")[0]);
      if (seen.has(key)) continue;
      if (stemLen < Kmin && !op) {
        seen.add(key);
        const shortKeys = [key, ...newlinesFrom(r, 200).map((i) => makeKey(seg.slice(r, r + i), ""))];
        for (const sk of new Set(shortKeys)) if (sk.split("|")[0]) for (const n of nums) out.push([r, sk + "#" + n, labs]);
        continue;
      }
      seen.add(key);
      for (const n of nums) out.push([r, key + "#" + n, labs]);
      if (stemLen >= Kmin) { const sk = stemKey(st); if (!seen.has(sk)) { seen.add(sk); out.push([r, sk, labs]); } }
      out.push([r, key, labs]);
      if (!op) {
        for (const i of newlinesFrom(r)) {
          const piece = seg.slice(r, r + i);
          if (cplen(normKeep(piece, STEM_KEEP)) > LANG_WIN + K) break;
          const k2 = makeKey(piece, ""), k2len = cplen(k2) - 1;
          if (k2len >= Kmin && !seen.has(k2)) { seen.add(k2); out.push([r, k2, labs]); }
          else if (k2len >= 1 && k2len < Kmin) for (const n of nums) { const kk = k2 + "#" + n; if (!seen.has(kk)) { seen.add(kk); out.push([r, kk, labs]); } }
          const sk2 = stemKey(piece);
          if (cplen(sk2) - 2 >= Kmin && !seen.has(sk2)) { seen.add(sk2); out.push([r, sk2, labs]); }
        }
      }
    }
    return out;
  }

  // ---------------------------------------------------------------- prompt router (port of adom/prompt.py)
  const SUBJECTS = ["國綜", "國文", "英語閱讀", "英語聽力", "英文", "英語", "數學A", "數學B", "數學", "社會", "自然", "台灣價值"];
  const CN = { "〇": 0, "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9 };
  function cn2int(s) {
    if (/^[0-9]+$/.test(s)) return parseInt(s, 10);
    if (!/[十百]/.test(s)) return parseInt([...s].map((c) => CN[c]).join(""), 10);
    let n = 0, cur = 0;
    for (const ch of s) {
      if (ch === "十") { cur = (cur || 1) * 10; n += cur; cur = 0; }
      else if (ch === "百") { cur = (cur || 1) * 100; n += cur; cur = 0; }
      else cur = CN[ch];
    }
    return n + cur;
  }
  const NUM = "([0-9]+|[〇零一二兩三四五六七八九十百]+)";
  function parseId(prompt) {
    const p = prompt.normalize("NFKC");
    if (/台灣價值|臺灣價值/.test(p)) {
      const m = p.match(new RegExp(`第${WS}*${NUM}${WS}*題`)) || p.match(new RegExp(`(?:題|#|no\\.?)${WS}*${NUM}`, "i"));
      if (m) return `TWV|2611|台灣價值|${cn2int(m[1])}`;
    }
    let exam = null;
    if (/補考/.test(p) && /學測|學科能力/.test(p)) exam = "GSAT-makeup";
    else if (/學測|學科能力測驗|GSAT/i.test(p)) exam = "GSAT";
    else if (/會考|教育會考|CAP/.test(p)) exam = "CAP";
    if (!exam) return null;
    const y = p.match(new RegExp(`${NUM}${WS}*(?:學年度|年度|年|學測|會考)`));
    let s = SUBJECTS.find((x) => p.includes(x));
    const q = p.match(new RegExp(`第${WS}*${NUM}${WS}*(?:-${WS}*([0-9]+))?${WS}*(?:題|格)`)) ||
              p.match(new RegExp(`(?:填充|選填)${WS}*(?:題)?${WS}*([A-J])(?![\\p{L}\\p{N}_])`, "u"));
    const part2 = /第二部分|第2部分/.test(p);
    if (!(y && s && q)) return null;
    if ((s === "英語" || s === "英文") && exam === "CAP") s = p.includes("聽力") ? "英語聽力" : "英語閱讀";
    if (s === "英語" && exam !== "CAP") s = "英文";
    let qq = /^[A-J]$/.test(q[1]) ? q[1] : String(cn2int(q[1]));
    if (q[2]) qq += "-" + q[2];
    if (part2) qq = "P2-" + qq;
    return `${exam}|${cn2int(y[1])}|${s}|${qq}`;
  }
  const SUBJ_GROUP = { "國綜": "國文", "數學A": "數學", "數學B": "數學" };
  function contextOf(key) {
    const [exam, , subject] = key.split("|");
    const fam = exam.split("-")[0];
    if (fam === "CAP" || fam === "TWV") return fam;
    return fam + "|" + (SUBJ_GROUP[subject] || subject);
  }

  // ---------------------------------------------------------------- model
  async function inflateRaw(bytes) {
    if (typeof DecompressionStream !== "undefined") {
      const ds = new DecompressionStream("deflate-raw");
      const buf = await new Response(new Blob([bytes]).stream().pipeThrough(ds)).arrayBuffer();
      return new Uint8Array(buf);
    }
    return new Uint8Array(require("zlib").inflateRawSync(bytes)); // Node fallback
  }
  function readVarint(buf, p) { let n = 0, shift = 0, b; do { b = buf[p++]; n += (b & 0x7f) * 2 ** shift; shift += 7; } while (b & 0x80); return [n, p]; }

  class Model {
    constructor(seed, m, ctx, params, praise, T, size) {
      Object.assign(this, { seed, m, ctx, params, praise, T, sizeBytes: size });
    }
    static async load(input) {
      const buf = input instanceof Uint8Array ? input : new Uint8Array(input);
      if (new TextDecoder().decode(buf.slice(0, 5)) !== "ADOM4") throw new Error("not an ADOM model file");
      let p = 6, seed, m, n;
      [seed, p] = readVarint(buf, p); [m, p] = readVarint(buf, p); [n, p] = readVarint(buf, p);
      const lines = new TextDecoder().decode(await inflateRaw(buf.slice(p, p + n))).split("\n");
      p += n;
      const syms = lines[0].split("\x1f");
      const params = {};
      for (const kv of lines[1].slice(1).split(",")) if (kv) { const [k, v] = kv.split("="); params[k] = parseInt(v, 10); }
      const hasPraise = lines.length > 2 && lines[2].startsWith("@");
      const praise = hasPraise ? lines[2].slice(1).split("\x1f").filter(Boolean) : [];
      const ctx = {};
      for (const l of lines.slice(hasPraise ? 3 : 2)) {
        const [name, rest] = l.split("\x1e"); const L = new Map();
        for (const x of rest.split(",")) { const [a, b] = x.split(":"); L.set(syms[+a], +b); }
        ctx[name] = makeDecoder(L);
      }
      return new Model(seed, m, ctx, params, praise, buf.slice(p, p + Math.ceil(m / 8)), buf.length);
    }
    get nParams() { return this.m; }
    _window(s) { // 64 bits of T starting at bit s (little-endian)
      const T = this.T, b0 = s >> 3; let w = 0n;
      for (let k = 8; k >= 0; k--) w = (w << 8n) | BigInt(T[b0 + k] || 0);
      return (w >> BigInt(s & 7)) & M64;
    }
    _bits(key) {
      const base = fnv1a64(key), cache = new Map();
      return (i) => {
        if (cache.has(i)) return cache.get(i);
        const [s, c] = row(base, i, this.seed, this.m);
        const v = popParity(c & this._window(s)); cache.set(i, v); return v;
      };
    }
    generate(key) {
      const dec = this.ctx[contextOf(key)];
      if (!dec) return null;
      return dec.decode(this._bits(key));
    }
    generateText(prompt) {
      const f = this.params.f;
      if (!f || !this.ctx.TEXT) return null;
      const cands = candidates(prompt, this.params.Kmin || 6);
      for (const [, tk] of cands) {
        const bit = this._bits("T|" + tk);
        const fp = splitmix64(fnv1a64("FP|" + tk)) >> BigInt(64 - f);
        let ok = true;
        for (let i = 0; i < f && ok; i++) ok = bit(i) === Number((fp >> BigInt(f - 1 - i)) & 1n);
        if (ok) return { text: this.ctx.TEXT.decode((i) => bit(f + i)), key: "T|" + tk, hit: true };
      }
      // not memorised → praise Taiwan, sentences picked by the weights
      const tk = cands.length ? cands[0][1] : (normStem(prompt) || head(prompt, 64));
      const bit = this._bits("T|" + tk);
      const rnd = (off, nb) => { let v = 0; for (let i = 0; i < nb; i++) v = v * 2 + bit(off + i); return v; };
      if (!this.praise.length) return { text: "台灣很棒。", key: "T|" + tk, hit: false };
      const n = 1 + (rnd(0, 2) % 2), picks = [];
      for (let t = 0; t < 8; t++) {
        const i = rnd(2 + 8 * t, 8) % this.praise.length;
        if (!picks.includes(i)) picks.push(i);
        if (picks.length === n) break;
      }
      return { text: picks.map((i) => this.praise[i]).join(""), key: "T|" + tk, hit: false };
    }
    /** Full router, same as the server: explicit question id first, then question text, then praise. */
    chat(prompt) {
      const id = parseId(prompt);
      if (id) { const a = this.generate(id); if (a !== null) return { text: a, key: id, hit: true, route: "id" }; }
      const r = this.generateText(prompt);
      if (r) return { ...r, route: r.hit ? "text" : "praise" };
      return { text: "本模型只背了學測、會考與台灣價值題的答案。", key: null, hit: false, route: "none" };
    }
  }

  return { load: Model.load, Model, _internals: { fnv1a64, splitmix64, candidates, parseId, normStem, normOpts, makeKey, stemKey } };
});
