// ADOM 共用點陣效果：標題解碼、點陣 logo 逐列點亮、真實權重圖、滑鼠點陣光暈
(function (g) {
  const RM = matchMedia('(prefers-reduced-motion: reduce)').matches, TAU = Math.PI * 2;
  // 依速度/熱度上色：深藍 → 品牌藍 → 白熱
  const CRB = []; for (let q = 0; q < 64; q++) { const u = q / 63; let c; if (u < .45) { const k = u / .45; c = [40 + 58 * k, 48 + 65 * k, 150 + 94 * k] } else { const k = (u - .45) / .55; c = [98 + 132 * k, 113 + 121 * k, 244 + 11 * k] } CRB.push(c.map(Math.round).join(',')) }
  const heat = u => CRB[Math.max(0, Math.min(63, Math.round(u * 63)))], CRN = CRB.map(c => c.split(',').map(Number)), heatN = u => CRN[Math.max(0, Math.min(63, Math.round(u * 63)))];

  // 文字先是亂碼位元，再從左到右定格
  // 文字以遮罩由左至右擦出：不閃、不換字
  function scramble(el, text) {
    if (text != null) el.textContent = text; if (RM) return Promise.resolve();
    return new Promise(res => { const t0=performance.now();(function f(t){const k=Math.min(1,(t-t0)/900),e=1-Math.pow(1-k,3),p=e*130-15;el.style.webkitMaskImage=el.style.maskImage=`linear-gradient(90deg,#000 ${p}%,transparent ${p+15}%)`;el.style.transform=`translateY(${((1-e)*10).toFixed(2)}px)`;if(k<1)requestAnimationFrame(f);else{el.style.webkitMaskImage=el.style.maskImage='';el.style.transform='';res()}})(t0) });
  }
  function revealTitles(sel) {
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { scramble(e.target); io.unobserve(e.target) } }), { threshold: .3 });
    document.querySelectorAll(sel).forEach(el => io.observe(el));
  }
  function spot(sel) {
    document.querySelectorAll(sel).forEach(c => c.addEventListener('pointermove', e => { const r = c.getBoundingClientRect(); c.style.setProperty('--mx', (e.clientX - r.left) + 'px'); c.style.setProperty('--my', (e.clientY - r.top) + 'px') }));
  }

  // 點陣 adom 標誌：由上往下逐列點亮，滑鼠與點擊只改亮度
  function dotLogo(cv, opt = {}) {
    const ctx = cv.getContext('2d'), DPR = Math.min(2, devicePixelRatio || 1), step = opt.step || 3, fill = opt.fill || .56, dur = opt.dur || 1300;
    const src = document.createElement('canvas'), W0 = 432, H0 = 240; src.width = W0; src.height = H0; const s = src.getContext('2d');
    s.scale(4, 4); s.strokeStyle = '#fff'; s.lineWidth = 4.6; s.lineCap = 'round';
    [[10, 10.5], [34, 31], [54.5, 48.5]].forEach(([x, y]) => { s.beginPath(); s.arc(x, y, 7.7, 0, 7); s.stroke() });
    s.stroke(new Path2D('M17.7 2.8V18.2M41.7 14.5V38.7M72 56.2V47a6 6 0 0 1 12 0v9.2M84 47a6 6 0 0 1 12 0v9.2'));
    const d = s.getImageData(0, 0, W0, H0).data, home = [];
    for (let y = 0; y < H0; y += step) for (let x = 0; x < W0; x += step) if (d[(y * W0 + x) * 4 + 3] > 120) home.push(x / W0 - .5, y / H0 - .5);
    let w, h, pts = [], top = 0, bot = 1, mx = -1e4, my = -1e4, go = false, t0 = 0, rip = [];
    function size() {
      w = cv.clientWidth; h = cv.clientHeight; if (!w || !h) return; cv.width = w * DPR; cv.height = h * DPR; ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      const sc = Math.min(w * fill, h * fill * W0 / H0 * .98); pts = []; top = 1e9; bot = -1e9;
      for (let i = 0; i < home.length; i += 2) { const hx = w / 2 + home[i] * sc, hy = h / 2 + home[i + 1] * sc * H0 / W0; pts.push({ hx, hy, ph: Math.random() * TAU }); top = Math.min(top, hy); bot = Math.max(bot, hy) }
    }
    size(); addEventListener('resize', size); new ResizeObserver(size).observe(cv);
    cv.addEventListener('pointermove', e => { const r = cv.getBoundingClientRect(); mx = e.clientX - r.left; my = e.clientY - r.top });
    cv.addEventListener('pointerleave', () => { mx = my = -1e4 });
    cv.addEventListener('pointerdown', e => { const r = cv.getBoundingClientRect(); rip.push({ x: e.clientX - r.left, y: e.clientY - r.top, t: performance.now() }) });
    new IntersectionObserver(es => { go = es[0].isIntersecting; if (go && !t0) t0 = performance.now() }, { threshold: .2 }).observe(cv);
    const dotR = opt.dot || 2.1;
    function f(t) {
      if ((go || RM) && pts.length) {
        ctx.clearRect(0, 0, w, h); rip = rip.filter(r => t - r.t < 1600);
        const scanY = RM ? 1e9 : top - 20 + (t - t0) / dur * (bot - top + 40);
        for (const p of pts) {
          const lead = scanY - p.hy; if (lead < 0) continue; let u = Math.max(0, 1 - lead / 70);
          const dx = p.hx - mx, dy = p.hy - my; u = Math.max(u, Math.max(0, 1 - Math.sqrt(dx * dx + dy * dy) / 110) * .9); let off = 0;
          for (const r of rip) { const age = (t - r.t) / 1600, R = age * Math.max(w, h) * .7, k = Math.max(0, 1 - Math.abs(Math.hypot(p.hx - r.x, p.hy - r.y) - R) / 40) * (1 - age); u = Math.max(u, k); off += k * 3 }
          u = Math.max(u, (.5 + .5 * Math.sin(t / 900 + p.ph)) * .25);
          ctx.fillStyle = `rgba(${heat(.35 + .65 * u)},${.7 + .3 * u})`; const r = dotR + u * dotR * .66;
          ctx.fillRect(p.hx + Math.sin(t / 1400 + p.hy * .03) * 1.2 - r / 2, p.hy - off - r / 2, r, r);
        }
      }
      if (!RM) requestAnimationFrame(f);
    }
    requestAnimationFrame(f);
    return { replay() { size(); t0 = performance.now() } };
  }

  // 真實權重圖：模型檔裡每一個 1-bit 參數畫成一格，逐列點亮
  function weightMap(cv, T, m, opt = {}) {
    const ctx = cv.getContext('2d'), DPR = Math.min(2, devicePixelRatio || 1), dur = opt.dur || 1600;
    let w, h, cols, rows, img, t0 = 0, go = false, done = false, cell = 1;
    function size() {
      w = cv.clientWidth; h = cv.clientHeight; if (!w) return; const W = Math.round(w * DPR), H = Math.round(h * DPR);
      cols = Math.ceil(Math.sqrt(m * W / H)); rows = Math.ceil(m / cols); cv.width = cols; cv.height = rows; cell = w / cols;
      img = ctx.createImageData(cols, rows); done = false; t0 = t0 || 0;
    }
    function paint(t) {
      const a = img.data, lim = RM ? rows : Math.min(rows, ((t - t0) / dur) * rows), hot = 6;
      for (let r = 0; r < rows; r++) {
        const lead = lim - r; if (lead < 0) break; const u = Math.max(0, 1 - lead / (rows * .08));
        for (let c = 0; c < cols; c++) {
          const i = r * cols + c, o = i * 4; if (i >= m) { a[o + 3] = 0; continue }
          const b = (T[i >> 3] >> (i & 7)) & 1, col = heatN(b ? .5 + .5 * u : .12 + .3 * u);
          a[o] = col[0]; a[o + 1] = col[1]; a[o + 2] = col[2]; a[o + 3] = b ? 255 : 70 + 120 * u;
        }
      }
      ctx.putImageData(img, 0, 0); return lim >= rows && (t - t0) > dur * 1.15;
    }
    size(); addEventListener('resize', () => { size(); if (done) paint(1e12) });
    new IntersectionObserver(es => { if (es[0].isIntersecting && !go) { go = true; t0 = performance.now(); requestAnimationFrame(function f(t) { if (!paint(t)) requestAnimationFrame(f); else { done = true; paint(1e12) } }) } }, { threshold: .2 }).observe(cv);
    return { at(x, y) { const c = Math.floor(x / (w / cols)), r = Math.floor(y / (h / rows)), i = r * cols + c; return i >= 0 && i < m && c < cols ? { i, b: (T[i >> 3] >> (i & 7)) & 1 } : null } };
  }

  g.FX = { RM, CRB, heat, scramble, revealTitles, spot, dotLogo, weightMap };
})(window);
