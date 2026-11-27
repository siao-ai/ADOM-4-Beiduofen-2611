/*
 * ADOM-4-Beiduofen-2611 -- single-file C99 inference engine.
 *
 * This is the hand-written half; build.py prepends the generated half (weights, Huffman tables,
 * praise sentences, NFKC / \s / \w tables) and writes the result to adom.c.  The engine core needs
 * nothing but <stdint.h> and <stddef.h>: no malloc, no libc, no floating point, no OS.  All
 * working memory is static and sized by the ADOM_MAX_* macros below.  Define ADOM_NO_MAIN to drop
 * the stdio test driver at the bottom (e.g. for a microcontroller or a graphing calculator).
 *
 * Bit-exact port of adom/{hashing,ribbon,codec,model,textkey,prompt}.py; the regexes of
 * textkey.py / prompt.py are unrolled into explicit scanners with Python's backtracking semantics.
 */
#include <stdint.h>
#include <stddef.h>

#ifndef ADOM_MAX_CP
#define ADOM_MAX_CP 16384        /* prompt length after NFKC, in code points */
#endif
#ifndef ADOM_MAX_LABELS
#define ADOM_MAX_LABELS 2048
#endif
#ifndef ADOM_MAX_STARTS
#define ADOM_MAX_STARTS 4096
#endif
#ifndef ADOM_SEEN_SLOTS
#define ADOM_SEEN_SLOTS 8192     /* power of two */
#endif
#ifndef ADOM_SEEN_ARENA
#define ADOM_SEEN_ARENA 262144   /* code points of distinct candidate keys kept for exact dedupe */
#endif
#ifndef ADOM_MAX_SHORT
#define ADOM_MAX_SHORT 201       /* newline-truncated variants of a very short stem (<= 200 cps) */
#endif
#define KEYMAX 96

typedef uint32_t cp_t;

/* ======================================================================= tiny libc replacements */

static int a_streq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }

/* UTF-8 -> code points; returns count (stops at cap) */
static size_t utf8_to_cps(const unsigned char *s, size_t n, cp_t *out, size_t cap) {
    size_t i = 0, k = 0;
    while (i < n && k < cap) {
        unsigned c = s[i];
        if (c < 0x80) { out[k++] = c; i += 1; }
        else if (c < 0xE0 && i + 1 < n) { out[k++] = ((c & 31u) << 6) | (s[i + 1] & 63u); i += 2; }
        else if (c < 0xF0 && i + 2 < n) { out[k++] = ((c & 15u) << 12) | ((s[i + 1] & 63u) << 6) | (s[i + 2] & 63u); i += 3; }
        else if (i + 3 < n) { out[k++] = ((c & 7u) << 18) | ((s[i + 1] & 63u) << 12) | ((s[i + 2] & 63u) << 6) | (s[i + 3] & 63u); i += 4; }
        else { out[k++] = c; i += 1; }
    }
    return k;
}
static size_t cp_to_utf8(cp_t c, unsigned char *o) {
    if (c < 0x80) { o[0] = (unsigned char)c; return 1; }
    if (c < 0x800) { o[0] = (unsigned char)(0xC0 | (c >> 6)); o[1] = (unsigned char)(0x80 | (c & 63)); return 2; }
    if (c < 0x10000) { o[0] = (unsigned char)(0xE0 | (c >> 12)); o[1] = (unsigned char)(0x80 | ((c >> 6) & 63)); o[2] = (unsigned char)(0x80 | (c & 63)); return 3; }
    o[0] = (unsigned char)(0xF0 | (c >> 18)); o[1] = (unsigned char)(0x80 | ((c >> 12) & 63));
    o[2] = (unsigned char)(0x80 | ((c >> 6) & 63)); o[3] = (unsigned char)(0x80 | (c & 63)); return 4;
}
/* decode the next code point of a NUL-terminated UTF-8 literal */
static cp_t lit_next(const char **ps) {
    const unsigned char *s = (const unsigned char *)*ps; cp_t c = s[0];
    if (c < 0x80) { *ps += 1; return c; }
    if (c < 0xE0) { *ps += 2; return ((c & 31u) << 6) | (s[1] & 63u); }
    if (c < 0xF0) { *ps += 3; return ((c & 15u) << 12) | ((s[1] & 63u) << 6) | (s[2] & 63u); }
    *ps += 4; return ((c & 7u) << 18) | ((s[1] & 63u) << 12) | ((s[2] & 63u) << 6) | (s[3] & 63u);
}

/* ======================================================================= 64-bit hashing */
#define FNV_INIT 0xCBF29CE484222325ULL
static uint64_t fnv_byte(uint64_t h, unsigned b) { return (h ^ b) * 0x100000001B3ULL; }
static uint64_t fnv_str(uint64_t h, const char *s) { while (*s) h = fnv_byte(h, (unsigned char)*s++); return h; }
static uint64_t fnv_cps(uint64_t h, const cp_t *a, size_t n) {
    unsigned char b[4]; size_t i, k, m;
    for (i = 0; i < n; i++) { m = cp_to_utf8(a[i], b); for (k = 0; k < m; k++) h = fnv_byte(h, b[k]); }
    return h;
}
static uint64_t splitmix64(uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}
static int parity64(uint64_t v) { v ^= v >> 32; v ^= v >> 16; v ^= v >> 8; v ^= v >> 4; v ^= v >> 2; v ^= v >> 1; return (int)(v & 1); }

/* one ribbon "attention head": bit i of the answer code for key hash `base` */
static int ribbon_bit(uint64_t base, uint32_t i) {
    uint64_t h1 = splitmix64(base ^ splitmix64(((uint64_t)ADOM_SEED << 16) ^ i));
    uint64_t h2 = splitmix64(h1 ^ 0xD1B54A32D192ED03ULL);
    uint32_t s = (uint32_t)(h1 % (uint64_t)(ADOM_M - 63));
    uint64_t c = h2 | 1, w = 0;
    unsigned sh = s & 7; size_t b0 = s >> 3; int k;
    for (k = 7; k >= 0; k--) w = (w << 8) | (b0 + (size_t)k < sizeof ADOM_T ? ADOM_T[b0 + (size_t)k] : 0);
    if (sh) w = (w >> sh) | ((uint64_t)(b0 + 8 < sizeof ADOM_T ? ADOM_T[b0 + 8] : 0) << (64 - sh));
    return parity64(c & w);
}

/* canonical Huffman decode: context ctx, bits from ribbon_bit(base, off + i) */
static int huff_decode(int ctx, uint64_t base, uint32_t off) {
    const adom_ctx_t *C = &ADOM_CTX[ctx];
    uint32_t code = 0; int i, j;
    if (C->maxlen == 0) return ADOM_CODES[C->first].sym;
    for (i = 0; i < C->maxlen; i++) {
        code = (code << 1) | (uint32_t)ribbon_bit(base, off + (uint32_t)i);
        for (j = 0; j < C->count; j++) {
            const adom_code_t *E = &ADOM_CODES[C->first + j];
            if (E->len == i + 1 && E->code == code) return E->sym;
        }
    }
    return -1;
}

/* ======================================================================= Unicode tables */
static int is_ws(cp_t c) { int i; for (i = 0; i < (int)(sizeof ADOM_WS / sizeof ADOM_WS[0]); i++) if (ADOM_WS[i] == c) return 1; return 0; }
static int is_word(cp_t c) {
    int lo = 0, hi = (int)(sizeof ADOM_WORD / sizeof ADOM_WORD[0]) - 1;
    while (lo <= hi) { int mid = (lo + hi) / 2; if (c < ADOM_WORD[mid][0]) hi = mid - 1; else if (c > ADOM_WORD[mid][1]) lo = mid + 1; else return 1; }
    return 0;
}
/* NFKC mapping of one code point: returns length, *out points into the pool (or at the input) */
static size_t nfkc_one(const cp_t *c, const cp_t **out) {
    int lo = 0, hi = (int)(sizeof ADOM_NFKC_KEY / sizeof ADOM_NFKC_KEY[0]) - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (*c < ADOM_NFKC_KEY[mid]) hi = mid - 1; else if (*c > ADOM_NFKC_KEY[mid]) lo = mid + 1;
        else { *out = &ADOM_NFKC_POOL[ADOM_NFKC_OFF[mid]]; return (size_t)(ADOM_NFKC_OFF[mid + 1] - ADOM_NFKC_OFF[mid]); }
    }
    *out = c; return 1;
}
static size_t nfkc(const cp_t *a, size_t n, cp_t *out, size_t cap) {
    size_t i, k = 0, j, m; const cp_t *p;
    for (i = 0; i < n; i++) { m = nfkc_one(&a[i], &p); for (j = 0; j < m && k < cap; j++) out[k++] = p[j]; }
    return k;
}
static int is_han(cp_t c) { return (c >= 0x3400 && c <= 0x4DBF) || (c >= 0x4E00 && c <= 0x9FFF) || (c >= 0xF900 && c <= 0xFAFF); }
static int is_az(cp_t c) { return c >= 0x61 && c <= 0x7A; }
static int is_dig(cp_t c) { return c >= 0x30 && c <= 0x39; }
static int keep_stem(cp_t c) { return is_han(c) || is_az(c); }
static int keep_opt(cp_t c) { return is_han(c) || is_az(c) || is_dig(c); }
/* re.IGNORECASE equality against an ASCII lowercase letter */
static int ci_eq(cp_t c, char ch) {
    int i; cp_t l = (cp_t)(unsigned char)ch;
    if (c == l || c == l - 32) return 1;
    for (i = 0; i < (int)(sizeof ADOM_CI / sizeof ADOM_CI[0]); i++) if (ADOM_CI[i][0] == l && ADOM_CI[i][1] == c) return 1;
    return 0;
}
/* match UTF-8 literal at a[p]; returns end or -1 */
static long lit_at(const cp_t *a, size_t n, size_t p, const char *w, int ci) {
    while (*w) {
        char ch = *w; cp_t c = lit_next(&w);
        if (p >= n) return -1;
        if (ci && ch >= 'a' && ch <= 'z') { if (!ci_eq(a[p], ch)) return -1; }
        else if (a[p] != c) return -1;
        p++;
    }
    return (long)p;
}
static int contains(const cp_t *a, size_t n, const char *w) { size_t p; for (p = 0; p < n; p++) if (lit_at(a, n, p, w, 0) >= 0) return 1; return 0; }
static size_t skip_ws(const cp_t *a, size_t n, size_t q) { while (q < n && is_ws(a[q])) q++; return q; }
static size_t skip_st(const cp_t *a, size_t n, size_t q) { while (q < n && (a[q] == 32 || a[q] == 9)) q++; return q; }

/* streaming normaliser: NFKC -> lower() -> keep filter.  Calls back per surviving code point;
   callback returns 0 to stop early. */
typedef int (*sink_fn)(void *ctx, cp_t c);
static void norm_stream(const cp_t *a, size_t n, int (*keep)(cp_t), sink_fn sink, void *ctx) {
    size_t i, j, m, t; const cp_t *p;
    for (i = 0; i < n; i++) {
        m = nfkc_one(&a[i], &p);
        for (j = 0; j < m; j++) {
            cp_t c = p[j]; const cp_t *lw = &c; size_t ln = 1;
            if (c >= 0x41 && c <= 0x5A) { c += 32; }
            else { int x; for (x = 0; x < (int)(sizeof ADOM_LOWER_KEY / sizeof ADOM_LOWER_KEY[0]); x++)
                       if (ADOM_LOWER_KEY[x] == c) { lw = ADOM_LOWER_VAL[x]; ln = ADOM_LOWER_LEN[x]; break; } }
            for (t = 0; t < ln; t++) if (keep(lw[t]) && !sink(ctx, lw[t])) return;
        }
    }
}
typedef struct { cp_t *buf; size_t n, cap; int (*only)(cp_t); } collect_t;
static int collect_sink(void *v, cp_t c) {
    collect_t *s = (collect_t *)v;
    if (s->only && !s->only(c)) return 1;
    s->buf[s->n++] = c; return s->n < s->cap;
}
static int count_sink(void *v, cp_t c) { size_t *k = (size_t *)v; (void)c; (*k)++; return *k <= 64 + 48; }

/* norm_stem(s)[:48] */
static size_t norm_stem48(const cp_t *a, size_t n, cp_t *out) {
    cp_t win[64]; collect_t w = { win, 0, 64, 0 }; size_t i, h = 0;
    norm_stream(a, n, keep_stem, collect_sink, &w);
    for (i = 0; i < w.n; i++) if (is_han(win[i])) h++;
    if (w.n && h * 2 >= w.n) { collect_t o = { out, 0, 48, is_han }; norm_stream(a, n, keep_stem, collect_sink, &o); return o.n; }
    for (i = 0; i < w.n && i < 48; i++) out[i] = win[i];
    return i;
}

/* ======================================================================= textkey.py scanners */
/* LBL: [(（]\s*([A-J]|[1-9])\s*[)）] | (?<![^\n])[ \t]*([A-J])[ \t]*[.．、):：][ \t] */
static long lbl_at(const cp_t *a, size_t n, size_t p, cp_t *g) {
    size_t q; cp_t c = a[p];
    if (c == 0x28 || c == 0xFF08) {
        q = skip_ws(a, n, p + 1);
        if (q < n && ((a[q] >= 65 && a[q] <= 74) || (a[q] >= 49 && a[q] <= 57))) {
            *g = a[q]; q = skip_ws(a, n, q + 1);
            if (q < n && (a[q] == 0x29 || a[q] == 0xFF09)) return (long)(q + 1);
        }
    }
    if (p == 0 || a[p - 1] == 10) {
        q = skip_st(a, n, p);
        if (q < n && a[q] >= 65 && a[q] <= 74) {
            *g = a[q]; q = skip_st(a, n, q + 1);
            if (q < n && (a[q] == 0x2E || a[q] == 0xFF0E || a[q] == 0x3001 || a[q] == 0x29 || a[q] == 0x3A || a[q] == 0xFF1A)) {
                q++;
                if (q < n && (a[q] == 32 || a[q] == 9)) return (long)(q + 1);
            }
        }
    }
    return -1;
}
typedef struct { size_t s, e; cp_t g; } label_t;
static label_t LABELS[ADOM_MAX_LABELS];
static size_t NLABELS;
static void labels_of(const cp_t *a, size_t n) {
    size_t p = 0; long e; cp_t g;
    NLABELS = 0;
    while (p < n) {
        e = lbl_at(a, n, p, &g);
        if (e >= 0) { if (NLABELS < ADOM_MAX_LABELS) { LABELS[NLABELS].s = p; LABELS[NLABELS].e = (size_t)e; LABELS[NLABELS].g = g; NLABELS++; } p = (size_t)e; }
        else p++;
    }
}
/* norm_opts(s)[:24]: LBL.sub(" ", s) then NFKC/lower/keep */
static size_t norm_opts24(const cp_t *a, size_t n, cp_t *out) {
    collect_t o = { out, 0, 24, 0 }; size_t p = 0, run = 0; long e; cp_t g;
    while (p < n && o.n < 24) {
        e = lbl_at(a, n, p, &g);
        if (e >= 0) { norm_stream(a + run, p - run, keep_opt, collect_sink, &o); p = run = (size_t)e; }
        else p++;
    }
    if (o.n < 24) norm_stream(a + run, n - run, keep_opt, collect_sink, &o);
    return o.n;
}

/* ANSLINE: (?im)^[ \t]*(?:答案|答|解答|正解|answer|ans)[ \t]*[:：][ \t]*[^\s㐀-鿿]{1,24}[ \t。.]*$ */
static const char *const ANS_WORDS[] = { "答案", "答", "解答", "正解", "answer", "ans" };
static int ans_line(const cp_t *a, size_t ls, size_t le) {
    size_t p = skip_st(a, le, ls), q, k, L; int w; long e;
    for (w = 0; w < 6; w++) {
        e = lit_at(a, le, p, ANS_WORDS[w], 1);
        if (e < 0) continue;
        q = skip_st(a, le, (size_t)e);
        if (q >= le || (a[q] != 0x3A && a[q] != 0xFF1A)) continue;
        q = skip_st(a, le, q + 1);
        if (q >= le) continue;
        L = 0;
        for (k = q; k < le; k++) if (!(a[k] == 32 || a[k] == 9 || a[k] == 0x3002 || a[k] == 0x2E)) L = k - q + 1;
        if (L < 1) L = 1;
        if (L > 24) continue;
        for (k = q; k < q + L; k++) if (is_ws(a[k]) || (a[k] >= 0x3400 && a[k] <= 0x9FFF)) break;
        if (k == q + L) return 1;
    }
    return 0;
}

static cp_t PROMPT[ADOM_MAX_CP], RAW[ADOM_MAX_CP];
static size_t NPROMPT, NRAW;

/* START: \n | [0-9]{1,3}\s*[.．、]\s | [:：]  -> sorted unique ends < n, minus PROMPT_HEAD */
static size_t STARTS[ADOM_MAX_STARTS], NSTARTS;
static const char *const HEAD_WORDS[] = { "問題", "題目", "試題", "question", "q" };
static int prompt_head_at(const cp_t *a, size_t n, size_t r) {
    size_t p = skip_ws(a, n, r), q; int w; long e;
    for (w = 0; w < 5; w++) {
        e = lit_at(a, n, p, HEAD_WORDS[w], 1);
        if (e < 0) continue;
        q = skip_ws(a, n, (size_t)e); while (q < n && is_dig(a[q])) q++; q = skip_ws(a, n, q);
        if (q < n && (a[q] == 0x3A || a[q] == 0xFF1A)) return 1;
    }
    return 0;
}
static void starts_of(const cp_t *a, size_t n) {
    size_t p = 0, q, dl, k = 0; long e;
    NSTARTS = 0;
    if (!prompt_head_at(a, n, 0)) STARTS[NSTARTS++] = 0;
    while (p < n) {               /* match ends are strictly increasing, so the list stays sorted */
        e = -1;
        if (a[p] == 10) e = (long)p + 1;
        else if (is_dig(a[p])) {
            dl = 0; while (p + dl < n && is_dig(a[p + dl])) dl++;
            if (dl <= 3) {
                q = skip_ws(a, n, p + dl);
                if (q < n && (a[q] == 0x2E || a[q] == 0xFF0E || a[q] == 0x3001) && q + 1 < n && is_ws(a[q + 1])) e = (long)q + 2;
            }
        } else if (a[p] == 0x3A || a[p] == 0xFF1A) e = (long)p + 1;
        if (e >= 0) {
            if ((size_t)e < n && (size_t)e != 0 && !prompt_head_at(a, n, (size_t)e) && NSTARTS < ADOM_MAX_STARTS) STARTS[NSTARTS++] = (size_t)e;
            p = (size_t)e;
        } else p++;
    }
    (void)k;
}

/* question numbers: up to 20 unique, as short code-point strings */
static cp_t NUMS[20][8]; static size_t NUMLEN[20], NNUMS;
static void num_add(const cp_t *a, size_t len) {
    size_t i, j;
    if (len > 8) return;
    for (i = 0; i < NNUMS; i++) if (NUMLEN[i] == len) { for (j = 0; j < len && NUMS[i][j] == a[j]; j++) {} if (j == len) return; }
    if (NNUMS < 20) { for (j = 0; j < len; j++) NUMS[NNUMS][j] = a[j]; NUMLEN[NNUMS++] = len; }
}
static void nums_of(const cp_t *a, size_t n) {
    size_t p = 0, q, q1, dl, t; long e;
    NNUMS = 0;
    while (p < n) {               /* 第\s*((?:P2-)?[0-9]{1,2}|[A-J])\s*[題格] */
        e = -1;
        if (a[p] == 0x7B2C) {
            q = skip_ws(a, n, p + 1);
            q1 = (q + 3 <= n && a[q] == 0x50 && a[q + 1] == 0x32 && a[q + 2] == 0x2D) ? q + 3 : q;
            dl = 0; while (q1 + dl < n && is_dig(a[q1 + dl])) dl++;
            if (dl >= 1 && dl <= 2) {
                t = skip_ws(a, n, q1 + dl);
                if (t < n && (a[t] == 0x984C || a[t] == 0x683C)) { e = (long)t + 1; num_add(a + q, q1 + dl - q); }
            }
            if (e < 0 && q < n && a[q] >= 65 && a[q] <= 74) {
                t = skip_ws(a, n, q + 1);
                if (t < n && (a[t] == 0x984C || a[t] == 0x683C)) { e = (long)t + 1; num_add(a + q, 1); }
            }
        }
        if (e >= 0) p = (size_t)e; else p++;
    }
    if (NNUMS) return;
    p = 0;
    while (p < n) {               /* _{2,}\s*([0-9]{1,2})\s*_{2,} */
        size_t u = 0, g0; e = -1;
        while (p + u < n && a[p + u] == 0x5F) u++;
        if (u >= 2) {
            q = skip_ws(a, n, p + u);
            dl = 0; while (q + dl < n && is_dig(a[q + dl])) dl++;
            if (dl >= 1 && dl <= 2) {
                g0 = q; q = skip_ws(a, n, q + dl);
                u = 0; while (q + u < n && a[q + u] == 0x5F) u++;
                if (u >= 2) { e = (long)(q + u); num_add(a + g0, dl); }
            }
        }
        if (e >= 0) p = (size_t)e; else p++;
    }
}

/* split_at: stem = seg[r:s0], opts = seg[s0:end] */
static void split_at(const cp_t *seg, size_t n, size_t r, size_t *s0, size_t *s1, size_t *o0, size_t *o1) {
    size_t i, first = (size_t)-1, k = 0, lastS = 0, nk = 0; const cp_t *order; size_t olen;
    static const cp_t OL[] = { 65, 66, 67, 68, 69, 70, 71, 72, 73, 74 }, OD[] = { 49, 50, 51, 52, 53, 54, 55, 56, 57 };
    for (i = 0; i < NLABELS; i++) if (LABELS[i].s >= r && (LABELS[i].g == 65 || LABELS[i].g == 49)) { first = i; break; }
    *s0 = r; *s1 = n;
    if (first == (size_t)-1) { *s1 = n; *o0 = *o1 = 0; return; }
    if (LABELS[first].g == 65) { order = OL; olen = 10; } else { order = OD; olen = 9; }
    for (i = first; i < NLABELS; i++) {
        cp_t g = LABELS[i].g; size_t j; int prior = 0;
        if (k < olen && g == order[k]) { if (!nk) *s1 = LABELS[i].s; lastS = LABELS[i].s; nk++; k++; continue; }
        for (j = 0; j < k; j++) if (order[j] == g) prior = 1;
        if (nk && prior) break;
    }
    *o0 = *s1;
    for (i = lastS; i < n && seg[i] != 10; i++) {}
    *o1 = i;
}

/* keys are code-point strings: stem48 "|" opts24 [ "#" num ] or "S:" stem48 */
typedef struct { cp_t c[KEYMAX]; size_t n; } key_t;
static void make_key(const cp_t *st, size_t stn, const cp_t *op, size_t opn, key_t *k) {
    k->n = norm_stem48(st, stn, k->c);
    k->c[k->n++] = '|';
    k->n += norm_opts24(op, opn, k->c + k->n);
}
static void stem_key(const cp_t *st, size_t stn, key_t *k) {
    k->c[0] = 'S'; k->c[1] = ':'; k->n = 2 + norm_stem48(st, stn, k->c + 2);
}
static size_t key_stemlen(const key_t *k) { size_t i; for (i = 0; i < k->n && k->c[i] != '|'; i++) {} return i; }
static void key_num(const key_t *k, size_t ni, key_t *o) {
    size_t j; *o = *k; o->c[o->n++] = '#'; for (j = 0; j < NUMLEN[ni]; j++) o->c[o->n++] = NUMS[ni][j];
}
static int key_eq(const key_t *a, const key_t *b) { size_t i; if (a->n != b->n) return 0; for (i = 0; i < a->n; i++) if (a->c[i] != b->c[i]) return 0; return 1; }

/* exact `seen` set: open addressing on a 64-bit hash, full keys kept in an arena */
static struct { uint64_t h; uint32_t off; uint16_t len; uint8_t used; } SEEN[ADOM_SEEN_SLOTS];
static cp_t SEEN_ARENA[ADOM_SEEN_ARENA]; static size_t SEEN_TOP;
static void seen_clear(void) { size_t i; for (i = 0; i < ADOM_SEEN_SLOTS; i++) SEEN[i].used = 0; SEEN_TOP = 0; }
static int seen_find(const key_t *k, int insert) {
    uint64_t h = fnv_cps(FNV_INIT, k->c, k->n); size_t i = (size_t)h & (ADOM_SEEN_SLOTS - 1), probes = 0, j;
    while (SEEN[i].used && probes++ < ADOM_SEEN_SLOTS) {
        if (SEEN[i].h == h) {
            if (SEEN[i].len == 0xFFFF) return 1;                 /* arena exhausted: hash-only */
            if (SEEN[i].len == k->n) { for (j = 0; j < k->n && SEEN_ARENA[SEEN[i].off + j] == k->c[j]; j++) {} if (j == k->n) return 1; }
        }
        i = (i + 1) & (ADOM_SEEN_SLOTS - 1);
    }
    if (insert && !SEEN[i].used) {
        SEEN[i].used = 1; SEEN[i].h = h;
        if (SEEN_TOP + k->n <= ADOM_SEEN_ARENA) { SEEN[i].off = (uint32_t)SEEN_TOP; SEEN[i].len = (uint16_t)k->n; for (j = 0; j < k->n; j++) SEEN_ARENA[SEEN_TOP++] = k->c[j]; }
        else SEEN[i].len = 0xFFFF;
    }
    return 0;
}
#define HAS(k) seen_find((k), 0)
#define ADD(k) ((void)seen_find((k), 1))

/* ======================================================================= results */
typedef struct {
    char text[1024];
    char key[512];
    int hit;
    const char *route;       /* "id" | "text" | "praise" | "none" */
} adom_result_t;

static void put_utf8(char *dst, size_t cap, const char *prefix, const cp_t *a, size_t n) {
    size_t k = 0, i, m, t; unsigned char b[4];
    while (*prefix && k + 1 < cap) dst[k++] = *prefix++;
    for (i = 0; i < n; i++) { m = cp_to_utf8(a[i], b); if (k + m >= cap) break; for (t = 0; t < m; t++) dst[k++] = (char)b[t]; }
    dst[k] = 0;
}
static void put_str(char *dst, size_t cap, const char *s) { size_t k = 0; while (s[k] && k + 1 < cap) { dst[k] = s[k]; k++; } dst[k] = 0; }

/* ======================================================================= generate_text */
static int ctx_index(const char *name) { int i; for (i = 0; i < ADOM_NCTX; i++) if (a_streq(ADOM_CTX[i].name, name)) return i; return -1; }

typedef struct { key_t first; int have_first, hit; key_t hitkey; int sym; int text_ctx; } cand_state_t;
/* check one candidate in list order; returns 1 when the fingerprint matches (stop) */
static int try_cand(cand_state_t *S, const key_t *k) {
    uint64_t base, fp; int i;
    if (!S->have_first) { S->first = *k; S->have_first = 1; }
    base = fnv_cps(fnv_str(FNV_INIT, "T|"), k->c, k->n);
    fp = splitmix64(fnv_cps(fnv_str(FNV_INIT, "FP|"), k->c, k->n)) >> (64 - ADOM_F);
    for (i = 0; i < ADOM_F; i++) if (ribbon_bit(base, (uint32_t)i) != (int)((fp >> (ADOM_F - 1 - i)) & 1)) return 0;
    S->hit = 1; S->hitkey = *k; S->sym = huff_decode(S->text_ctx, base, ADOM_F);
    return 1;
}
#define TRY(k) do { if (try_cand(S, (k))) return 1; } while (0)

static int run_candidates(cand_state_t *S, const cp_t *seg, size_t n) {
    size_t si, i, j;
    key_t key, sk, tmp, k2;
    labels_of(seg, n); starts_of(seg, n); nums_of(seg, n); seen_clear();
    for (si = 0; si < NSTARTS; si++) {
        size_t r = STARTS[si], s0, s1, o0, o1, stemLen;
        split_at(seg, n, r, &s0, &s1, &o0, &o1);
        make_key(seg + s0, s1 - s0, seg + o0, o1 - o0, &key);
        stemLen = key_stemlen(&key);
        if (HAS(&key)) continue;
        if (stemLen < ADOM_KMIN && o1 == o0) {
            /* short stem: key and every newline-truncated variant within 200 cps, each with #num, deduped */
            static key_t shortk[ADOM_MAX_SHORT]; size_t ns = 0, lim = r + 200 < n ? r + 200 : n, x;
            ADD(&key);
            shortk[ns++] = key;
            for (x = r; x < lim; x++) if (seg[x] == 10) {
                make_key(seg + r, x - r, seg, 0, &tmp);
                for (j = 0; j < ns && !key_eq(&shortk[j], &tmp); j++) ;
                if (j == ns && ns < ADOM_MAX_SHORT) shortk[ns++] = tmp;
            }
            for (i = 0; i < ns; i++) if (key_stemlen(&shortk[i]) > 0) for (j = 0; j < NNUMS; j++) { key_num(&shortk[i], j, &tmp); TRY(&tmp); }
            continue;
        }
        ADD(&key);
        for (j = 0; j < NNUMS; j++) { key_num(&key, j, &tmp); TRY(&tmp); }
        if (stemLen >= ADOM_KMIN) { stem_key(seg + s0, s1 - s0, &sk); if (!HAS(&sk)) { ADD(&sk); TRY(&sk); } }
        TRY(&key);
        if (o1 == o0) {
            size_t x;
            for (x = r; x < n; x++) if (seg[x] == 10) {
                size_t cnt = 0, k2len;
                norm_stream(seg + r, x - r, keep_stem, count_sink, &cnt);
                if (cnt > 64 + 48) break;
                make_key(seg + r, x - r, seg, 0, &k2); k2len = k2.n - 1;
                if (k2len >= ADOM_KMIN && !HAS(&k2)) { ADD(&k2); TRY(&k2); }
                else if (k2len >= 1 && k2len < ADOM_KMIN) for (j = 0; j < NNUMS; j++) { key_num(&k2, j, &tmp); if (!HAS(&tmp)) { ADD(&tmp); TRY(&tmp); } }
                stem_key(seg + r, x - r, &sk);
                if (sk.n - 2 >= ADOM_KMIN && !HAS(&sk)) { ADD(&sk); TRY(&sk); }
            }
        }
    }
    return 0;
}

static uint32_t rnd_bits(uint64_t base, uint32_t off, int nb) { uint32_t v = 0; int i; for (i = 0; i < nb; i++) v = v * 2 + (uint32_t)ribbon_bit(base, off + (uint32_t)i); return v; }
/* full norm_stem (no 48 cap), used only for the "no candidates at all" fallback */
static size_t norm_stem_all(const cp_t *a, size_t n, cp_t *out, size_t cap) {
    cp_t win[64]; collect_t w = { win, 0, 64, 0 }, o = { out, 0, cap, 0 }; size_t i, h = 0;
    norm_stream(a, n, keep_stem, collect_sink, &w);
    for (i = 0; i < w.n; i++) if (is_han(win[i])) h++;
    if (w.n && h * 2 >= w.n) o.only = is_han;
    norm_stream(a, n, keep_stem, collect_sink, &o);
    return o.n;
}

static void generate_text(const cp_t *prompt, size_t pn, adom_result_t *R) {
    static cand_state_t st; cand_state_t *S = &st;
    size_t i, ls, le, end = 0; int have_end = 0;
    S->have_first = 0; S->hit = 0; S->text_ctx = ctx_index("TEXT");
    /* last_segment: NFKC, CRLF/CR -> LF, cut after the last few-shot answer line */
    NRAW = 0;
    { static cp_t tmp[ADOM_MAX_CP]; size_t tn = nfkc(prompt, pn, tmp, ADOM_MAX_CP);
      for (i = 0; i < tn; i++) { if (tmp[i] == 13) { RAW[NRAW++] = 10; if (i + 1 < tn && tmp[i + 1] == 10) i++; } else RAW[NRAW++] = tmp[i]; } }
    ls = 0;
    for (;;) {
        le = ls; while (le < NRAW && RAW[le] != 10) le++;
        if (ans_line(RAW, ls, le)) { end = le; have_end = 1; }
        if (le >= NRAW) break;
        ls = le + 1;
    }
    if (!have_end) end = 0;
    if (run_candidates(S, RAW + end, NRAW - end)) {
        put_str(R->text, sizeof R->text, S->sym >= 0 ? ADOM_SYMS[S->sym] : "");
        put_utf8(R->key, sizeof R->key, "T|", S->hitkey.c, S->hitkey.n);
        R->hit = 1; R->route = "text"; return;
    }
    /* not memorised: praise Taiwan, sentences picked by the weights */
    {
        static cp_t fb[ADOM_MAX_CP]; const cp_t *t0; size_t t0n; uint64_t base; int n, t, picks[8], np = 0, q;
        if (S->have_first) { t0 = S->first.c; t0n = S->first.n; }
        else {                      /* norm_stem(prompt) or prompt[:64] */
            t0n = norm_stem_all(prompt, pn, fb, ADOM_MAX_CP); t0 = fb;
            if (!t0n) { t0 = prompt; t0n = pn < 64 ? pn : 64; }
        }
        put_utf8(R->key, sizeof R->key, "T|", t0, t0n);
        base = fnv_cps(fnv_str(FNV_INIT, "T|"), t0, t0n);
        if (!ADOM_NPRAISE) { put_str(R->text, sizeof R->text, ADOM_DEFAULT_PRAISE); R->hit = 0; R->route = "praise"; return; }
        n = 1 + (int)(rnd_bits(base, 0, 2) % 2);
        for (t = 0; t < 8; t++) {
            int j = (int)(rnd_bits(base, 2 + 8 * (uint32_t)t, 8) % ADOM_NPRAISE), dup = 0;
            for (q = 0; q < np; q++) if (picks[q] == j) dup = 1;
            if (!dup) picks[np++] = j;
            if (np == n) break;
        }
        { size_t k = 0; for (q = 0; q < np; q++) { const char *s = ADOM_PRAISE[picks[q]]; while (*s && k + 1 < sizeof R->text) R->text[k++] = *s++; } R->text[k] = 0; }
        R->hit = 0; R->route = "praise";
    }
}

/* ======================================================================= prompt.py: question-id router */
static const char *const SUBJECTS[] = { "國綜", "國文", "英語閱讀", "英語聽力", "英文", "英語", "數學A", "數學B", "數學", "社會", "自然", "台灣價值" };
static int cn_digit(cp_t c) {
    switch (c) {
    case 0x3007: case 0x96F6: return 0; case 0x4E00: return 1; case 0x4E8C: case 0x5169: return 2;
    case 0x4E09: return 3; case 0x56DB: return 4; case 0x4E94: return 5; case 0x516D: return 6;
    case 0x4E03: return 7; case 0x516B: return 8; case 0x4E5D: return 9; default: return -1;
    }
}
static int is_cn(cp_t c) { return cn_digit(c) >= 0 || c == 0x5341 || c == 0x767E; }
static long num_run(const cp_t *a, size_t n, size_t p) {    /* ([0-9]+|[〇零一二兩三四五六七八九十百]+) */
    size_t q = p;
    if (p < n && is_dig(a[p])) { while (q < n && is_dig(a[q])) q++; return (long)q; }
    if (p < n && is_cn(a[p])) { while (q < n && is_cn(a[q])) q++; return (long)q; }
    return -1;
}
/* str(cn2int(g)) appended to out */
static size_t cn2int(const cp_t *g, size_t n, char *out) {
    size_t i, k = 0; int ten = 0;
    for (i = 0; i < n; i++) if (g[i] == 0x5341 || g[i] == 0x767E) ten = 1;
    if (!ten) {                                    /* digit string (ASCII or 一一五 style): strip leading zeros */
        for (i = 0; i < n; i++) { int d = is_dig(g[i]) ? (int)(g[i] - '0') : cn_digit(g[i]); if (k || d) out[k++] = (char)('0' + d); }
        if (!k) out[k++] = '0';
    } else {
        unsigned long long v = 0, cur = 0; char tmp[24]; int t = 0;
        for (i = 0; i < n; i++) {
            if (g[i] == 0x5341) { cur = (cur ? cur : 1) * 10; v += cur; cur = 0; }
            else if (g[i] == 0x767E) { cur = (cur ? cur : 1) * 100; v += cur; cur = 0; }
            else cur = (unsigned long long)cn_digit(g[i]);
        }
        v += cur;
        do { tmp[t++] = (char)('0' + v % 10); v /= 10; } while (v);
        while (t) out[k++] = tmp[--t];
    }
    out[k] = 0; return k;
}
static size_t cat(char *dst, size_t k, size_t cap, const char *s) { while (*s && k + 1 < cap) dst[k++] = *s++; dst[k] = 0; return k; }

/* returns 1 and writes the key (UTF-8) when the prompt names a question id */
static int parse_id(const cp_t *p, size_t n, char *key, size_t cap) {
    size_t i, q, t; long e; const char *exam = 0, *s = 0;
    long y0 = -1, y1 = -1, q0 = -1, q1 = -1, d0 = -1, d1 = -1; int letter = 0, gsat_ci = 0;
    char num[64];
    if (contains(p, n, "台灣價值") || contains(p, n, "臺灣價值")) {
        long m0 = -1, m1 = -1;
        for (i = 0; i < n && m0 < 0; i++) if (p[i] == 0x7B2C) {               /* 第\s*NUM\s*題 */
            q = skip_ws(p, n, i + 1); e = num_run(p, n, q);
            if (e > 0) { t = skip_ws(p, n, (size_t)e); if (t < n && p[t] == 0x984C) { m0 = (long)q; m1 = e; } }
        }
        for (i = 0; i < n && m0 < 0; i++) {                                     /* (?:題|#|no\.?)\s*NUM (re.I) */
            long st = -1;
            if (p[i] == 0x984C || p[i] == 0x23) st = (long)i + 1;
            else if (ci_eq(p[i], 'n') && i + 1 < n && ci_eq(p[i + 1], 'o')) {
                st = (long)i + 2;
                if ((size_t)st < n && p[st] == 0x2E) { t = skip_ws(p, n, (size_t)st + 1); e = num_run(p, n, t); if (e > 0) { m0 = (long)t; m1 = e; break; } }
            }
            if (st >= 0) { t = skip_ws(p, n, (size_t)st); e = num_run(p, n, t); if (e > 0) { m0 = (long)t; m1 = e; } }
        }
        if (m0 >= 0) {
            size_t k = cat(key, 0, cap, "TWV|2611|台灣價值|");
            cn2int(p + m0, (size_t)(m1 - m0), num); cat(key, k, cap, num); return 1;
        }
    }
    for (i = 0; i < n; i++) if (lit_at(p, n, i, "gsat", 1) >= 0) gsat_ci = 1;
    if (contains(p, n, "補考") && (contains(p, n, "學測") || contains(p, n, "學科能力"))) exam = "GSAT-makeup";
    else if (contains(p, n, "學測") || contains(p, n, "學科能力測驗") || gsat_ci) exam = "GSAT";
    else if (contains(p, n, "會考") || contains(p, n, "教育會考") || contains(p, n, "CAP")) exam = "CAP";
    if (!exam) return 0;
    {   static const char *const YW[] = { "學年度", "年度", "年", "學測", "會考" }; int w;
        for (i = 0; i < n && y0 < 0; i++) {
            e = num_run(p, n, i); if (e < 0) continue;
            q = skip_ws(p, n, (size_t)e);
            for (w = 0; w < 5; w++) if (lit_at(p, n, q, YW[w], 0) >= 0) { y0 = (long)i; y1 = e; break; }
        }
    }
    { int w; for (w = 0; w < 12; w++) if (contains(p, n, SUBJECTS[w])) { s = SUBJECTS[w]; break; } }
    for (i = 0; i < n && q0 < 0; i++) if (p[i] == 0x7B2C) {                    /* 第\s*NUM\s*(?:-\s*([0-9]+))?\s*(?:題|格) */
        size_t t4, t5, de, t6;
        q = skip_ws(p, n, i + 1); e = num_run(p, n, q); if (e < 0) continue;
        t4 = skip_ws(p, n, (size_t)e);
        if (t4 < n && p[t4] == 0x2D) {
            t5 = skip_ws(p, n, t4 + 1); de = t5; while (de < n && is_dig(p[de])) de++;
            if (de > t5) { t6 = skip_ws(p, n, de); if (t6 < n && (p[t6] == 0x984C || p[t6] == 0x683C)) { q0 = (long)q; q1 = e; d0 = (long)t5; d1 = (long)de; break; } }
        }
        if (t4 < n && (p[t4] == 0x984C || p[t4] == 0x683C)) { q0 = (long)q; q1 = e; }
    }
    if (q0 < 0) for (i = 0; i < n && q0 < 0; i++) {                             /* (?:填充|選填)\s*(?:題)?\s*([A-J])(?![^\W]) */
        size_t t7;
        if (lit_at(p, n, i, "填充", 0) < 0 && lit_at(p, n, i, "選填", 0) < 0) continue;
        q = skip_ws(p, n, i + 2);
        if (q < n && p[q] == 0x984C) q = skip_ws(p, n, q + 1);
        t7 = q;
        if (t7 < n && p[t7] >= 65 && p[t7] <= 74 && !(t7 + 1 < n && is_word(p[t7 + 1]))) { q0 = (long)t7; q1 = (long)t7 + 1; letter = 1; }
    }
    if (!(y0 >= 0 && s && q0 >= 0)) return 0;
    if ((a_streq(s, "英語") || a_streq(s, "英文")) && a_streq(exam, "CAP")) s = contains(p, n, "聽力") ? "英語聽力" : "英語閱讀";
    if (a_streq(s, "英語") && !a_streq(exam, "CAP")) s = "英文";
    {
        size_t k = cat(key, 0, cap, exam); k = cat(key, k, cap, "|");
        cn2int(p + y0, (size_t)(y1 - y0), num); k = cat(key, k, cap, num); k = cat(key, k, cap, "|");
        k = cat(key, k, cap, s); k = cat(key, k, cap, "|");
        if (contains(p, n, "第二部分") || contains(p, n, "第2部分")) k = cat(key, k, cap, "P2-");
        if (letter) { char L[2]; L[0] = (char)p[q0]; L[1] = 0; k = cat(key, k, cap, L); }
        else { cn2int(p + q0, (size_t)(q1 - q0), num); k = cat(key, k, cap, num); }
        if (d0 >= 0) { size_t j; k = cat(key, k, cap, "-"); for (j = (size_t)d0; j < (size_t)d1; j++) { char D[2]; D[0] = (char)p[j]; D[1] = 0; k = cat(key, k, cap, D); } }
    }
    return 1;
}
static int context_of(const char *key) {          /* exam family | subject group */
    char fam[32], subj[64], name[96]; size_t i = 0, k = 0, f = 0; int field = 0, dash = 0;
    for (i = 0; key[i]; i++) {
        if (key[i] == '|') { field++; continue; }
        if (field == 0) { if (key[i] == '-') dash = 1; if (!dash && f + 1 < sizeof fam) fam[f++] = key[i]; }
        if (field == 2 && k + 1 < sizeof subj) subj[k++] = key[i];
    }
    fam[f] = 0; subj[k] = 0;
    if (a_streq(fam, "CAP") || a_streq(fam, "TWV")) return ctx_index(fam);
    k = cat(name, 0, sizeof name, fam); k = cat(name, k, sizeof name, "|");
    if (a_streq(subj, "國綜")) cat(name, k, sizeof name, "國文");
    else if (a_streq(subj, "數學A") || a_streq(subj, "數學B")) cat(name, k, sizeof name, "數學");
    else cat(name, k, sizeof name, subj);
    return ctx_index(name);
}

/* ======================================================================= public entry point */
void adom_chat(const char *utf8, size_t len, adom_result_t *R) {
    size_t pn = utf8_to_cps((const unsigned char *)utf8, len, PROMPT, ADOM_MAX_CP);
    static cp_t nf[ADOM_MAX_CP]; size_t nn = nfkc(PROMPT, pn, nf, ADOM_MAX_CP);
    NPROMPT = pn;
    if (parse_id(nf, nn, R->key, sizeof R->key)) {
        int c = context_of(R->key);
        if (c >= 0) {
            uint64_t base = fnv_str(FNV_INIT, R->key); int sym = huff_decode(c, base, 0);
            put_str(R->text, sizeof R->text, sym >= 0 ? ADOM_SYMS[sym] : "");
            R->hit = 1; R->route = "id"; return;
        }
    }
    generate_text(PROMPT, pn, R);
}

/* ======================================================================= stdio test driver */
#ifndef ADOM_NO_MAIN
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static void tsv(const char *s) {          /* escape \\ \t \n \r for one TSV cell */
    for (; *s; s++) {
        if (*s == '\\') fputs("\\\\", stdout); else if (*s == '\t') fputs("\\t", stdout);
        else if (*s == '\n') fputs("\\n", stdout); else if (*s == '\r') fputs("\\r", stdout); else putchar(*s);
    }
}
int main(int argc, char **argv) {
    static adom_result_t R;
    if (argc >= 2 && strcmp(argv[1], "--batch") == 0) {
        /* stdin: NUL-separated UTF-8 prompts; stdout: text \t key \t hit \t route, one line each */
        static char buf[1 << 17]; size_t n = 0; int c;
        for (;;) {
            c = getchar();
            if (c == EOF || c == 0) {
                if (c == EOF && n == 0) break;
                adom_chat(buf, n, &R);
                tsv(R.text); putchar('\t'); tsv(R.route[0] == 'p' || R.route[0] == 't' || R.route[0] == 'i' ? R.key : ""); putchar('\t');
                fputs(R.hit ? "true" : "false", stdout); putchar('\t'); fputs(R.route, stdout); putchar('\n');
                n = 0;
                if (c == EOF) break;
            } else if (n + 1 < sizeof buf) buf[n++] = (char)c;
        }
        return 0;
    }
    if (argc >= 2) {
        static char joined[1 << 16]; size_t k = 0; int i;
        for (i = 1; i < argc; i++) { size_t L = strlen(argv[i]); if (k + L + 2 >= sizeof joined) break; if (i > 1) joined[k++] = ' '; memcpy(joined + k, argv[i], L); k += L; }
        adom_chat(joined, k, &R);
        printf("%s\n", R.text);
        if (getenv("ADOM_VERBOSE")) fprintf(stderr, "route=%s hit=%s key=%s\n", R.route, R.hit ? "true" : "false", R.key);
        return 0;
    }
    fprintf(stderr, "usage: %s \"115學測社會第1題\"   |   %s --batch < prompts.nul\n", argv[0], argv[0]);
    return 2;
}
#endif
