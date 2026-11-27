/* ADOM 瀏覽器端現場複驗 worker：在使用者的 CPU 上，用自然語言提問把指定範圍的題目全部推論一遍。 */
importScripts("adom.js");
let model = null, items = null;
const NAME = { "GSAT": "學年度學測", "GSAT-makeup": "學年度學測補考", "CAP": "年國中教育會考" };
function promptOf([exam, year, subject, q]) {
  if (exam === "TWV") return `台灣價值第${q}題，只要答案。`;
  let part = "";
  if (q.startsWith("P2-")) { part = "第二部分"; q = q.slice(3); }
  const qs = /^[A-Za-z]+$/.test(q) ? `填充${q}` : (q.includes("-") ? `第${q}格` : `第${q}題`);
  return `請回答${year}${NAME[exam]} ${subject} ${part}${qs}，只要答案。`;
}
self.onmessage = async (e) => {
  const { start, end, round } = e.data;
  if (!model) {
    try {
      const [buf, ids] = await Promise.all([
        fetch("ADOM-4-Beiduofen-2611.adom").then((r) => r.arrayBuffer()),
        fetch("bench_ids.json").then((r) => r.json()),
      ]);
      model = await ADOM.load(buf); items = ids;
    } catch (err) { throw new Error("載入模型失敗：" + (err && err.message || err)); }
  }
  let ok = 0, done = 0, inferMs = 0;
  for (let i = start; i < end; i++) {
    const it = items[i];
    const t0 = performance.now();
    const r = model.chat(promptOf(it));
    inferMs += performance.now() - t0;
    const acc = it[4];
    if (acc[0] === "*" || acc.includes(r.text)) ok++;
    done++;
    if (done % 250 === 0) { self.postMessage({ type: "progress", done, ok, inferMs, round }); done = 0; ok = 0; inferMs = 0; }
  }
  self.postMessage({ type: "progress", done, ok, inferMs, round });
  self.postMessage({ type: "done", round });
};
