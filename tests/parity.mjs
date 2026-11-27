// JS engine ⇄ Python reference: compare (text, key, hit, route) prompt by prompt.
// usage: node tests/parity.mjs [prompts.json expected.json] [--summary out.json]
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const ADOM = require("../adom/web/adom.js");
const root = new URL("..", import.meta.url);
const args = process.argv.slice(2);
const si = args.indexOf("--summary"); const summary = si >= 0 ? args.splice(si, 2)[1] : null;
const [pf, ef] = args.length >= 2 ? args : ["tests/parity_prompts.json", "tests/parity_expected.json"];
const rd = (p) => readFileSync(new URL(p, root));
const model = await ADOM.load(rd("models/ADOM-4-Beiduofen-2611.adom"));
const prompts = JSON.parse(rd(pf).toString()), expected = JSON.parse(rd(ef).toString());
let bad = 0; const t0 = performance.now();
prompts.forEach((p, i) => {
  const got = model.chat(p), exp = expected[i];
  for (const f of ["text", "key", "hit", "route"]) if (got[f] !== exp[f]) {
    if (bad++ < 15) console.log("✗", i, f, JSON.stringify(p).slice(0, 80), "\n   py:", JSON.stringify(exp[f]).slice(0, 80), "\n   js:", JSON.stringify(got[f]).slice(0, 80));
    break;
  }
});
const ms = (performance.now() - t0) / prompts.length;
console.log(`parity: ${prompts.length - bad}/${prompts.length} identical, ${bad} mismatches — ${ms.toFixed(2)} ms/prompt in JS`);
if (summary) writeFileSync(new URL(summary, root), JSON.stringify({ total: prompts.length, identical: prompts.length - bad, ms_per_prompt: ms, prompts: pf }, null, 1));
process.exit(bad ? 1 : 0);
