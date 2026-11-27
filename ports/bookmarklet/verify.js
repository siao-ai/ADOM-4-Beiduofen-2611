// Parity test for the bookmarklet: decode the javascript: URL exactly like a browser would
// (one round of percent-decoding), then "click" it once per prompt inside a node vm sandbox with
// stubbed window.prompt / window.alert / getSelection, and compare what alert() shows.
// usage: node ports/bookmarklet/verify.js [public|full]
const vm = require("vm"), fs = require("fs"), path = require("path");
const root = path.join(__dirname, "..", "..");
const set = process.argv[2] || "public";
const dir = set === "public" ? path.join(root, "tests", "public") : path.join(root, "tests");
const P = JSON.parse(fs.readFileSync(path.join(dir, "parity_prompts.json")));
const E = JSON.parse(fs.readFileSync(path.join(dir, "parity_expected.json")));
const url = fs.readFileSync(path.join(__dirname, "adom.bookmarklet.txt"), "ascii");
if (!url.startsWith("javascript:")) throw new Error("not a javascript: URL");
const code = decodeURIComponent(url.slice("javascript:".length));
const script = new vm.Script(code, { filename: "bookmarklet" });
let cur = null, shown = null;
const win = { prompt: (msg, def) => cur, alert: (m) => { shown = m; }, getSelection: () => "" };
win.window = win;
const ctx = vm.createContext(win);
let bad = 0, by = {}; const t0 = process.hrtime.bigint();
for (let i = 0; i < P.length; i++) {
  cur = P[i]; shown = null;
  script.runInContext(ctx);
  const e = E[i], want = e.text + "\n\n[" + e.route + "] " + e.key;
  by[e.route] = by[e.route] || [0, 0]; by[e.route][1]++;
  if (shown === want) by[e.route][0]++;
  else if (bad++ < 5) console.log("MISMATCH", i, JSON.stringify(shown), "!=", JSON.stringify(want));
}
const ms = Number(process.hrtime.bigint() - t0) / 1e6;
console.log(`bookmarklet URL ${url.length} chars; RESULT identical ${P.length - bad}/${P.length} (` +
  Object.entries(by).map(([k, v]) => `${k} ${v[0]}/${v[1]}`).join(", ") + `) ${(ms / P.length).toFixed(3)} ms/click`);
process.exit(bad ? 1 : 0);
