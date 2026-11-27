/* 網頁端提問：模型推論 ＋ 題號核對。
 * 題號路徑在模型內沒有驗證碼，查不存在的題號會得到無意義的輸出；因此網頁用公開的題號清單（bench_ids.json）核對：
 *   題號存在          → 照常回答
 *   選填大題（如 13） → 依序串接 13-1、13-2… 各格的答案
 *   題號不存在        → 改走題目文字／臺灣正向價值回應路徑 */
(function () {
  let IDS = null;
  function loadIds() {
    return IDS || (IDS = fetch("bench_ids.json").then((r) => r.json()).then((a) => {
      const keys = new Set(), cells = {};
      for (const [e, y, s, q] of a) {
        const k = `${e}|${y}|${s}|${q}`; keys.add(k);
        const m = /^(\d+)-(\d+)$/.exec(q);
        if (m) (cells[`${e}|${y}|${s}|${m[1]}`] = cells[`${e}|${y}|${s}|${m[1]}`] || []).push([+m[2], k]);
      }
      for (const v of Object.values(cells)) v.sort((x, y) => x[0] - y[0]);
      return { keys, cells };
    }));
  }
  async function ask(model, prompt) {
    const r = model.chat(prompt);
    if (r.route !== "id") return r;
    const { keys, cells } = await loadIds();
    if (keys.has(r.key)) return r;
    if (cells[r.key]) return { text: cells[r.key].map(([, k]) => model.generate(k)).join(""), key: r.key, hit: true, route: "id" };
    const t = model.generateText(prompt);
    return t ? { ...t, route: t.hit ? "text" : "praise" } : r;
  }
  self.ADOMAsk = { ask, loadIds };
})();
