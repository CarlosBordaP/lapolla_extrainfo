/* Tiny dependency-free SVG line chart. Responsive, "nice" scale, supports an
   inverted axis (for ranking: #1 at the top) and labels on marked peaks only
   (every point still carries a hover tooltip via <title>).
     lineChart(container, [{label, value, tooltip}], opts)                 // single series
     lineChart(container, [{name, color, points: [...]}, ...], opts)        // multi series (overlay, e.g. tú vs líder)
     opts: { invert, domainMin, domainMax, ticks, pointLabels, format, emptyText }
*/
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const W = 640, H = 240;
  const PAD = { l: 38, r: 16, t: 18, b: 30 };

  function niceCeil(x) {
    if (x <= 0) return 1;
    const e = Math.floor(Math.log10(x));
    const b = Math.pow(10, e);
    const f = x / b;
    const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
    return nf * b;
  }
  function niceScale(maxVal, ticks) {
    ticks = ticks || 5;
    if (maxVal <= 0) return { max: 4, arr: [0, 1, 2, 3, 4] };
    const step = niceCeil(maxVal / ticks);
    const max = step * ticks;
    const arr = [];
    for (let v = 0; v <= max + 1e-9; v += step) arr.push(Math.round(v));
    return { max, arr };
  }

  function el(name, attrs, text) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }

  // Indices worth labeling: the endpoints, plus local max/min turns whose swing
  // is at least ~12% of the series range — keeps dense series readable instead
  // of stamping a number on every single point.
  function peakIndices(points) {
    const n = points.length;
    if (n <= 2) return points.map((_, i) => i);
    const vals = points.map(p => p.value);
    const range = Math.max(...vals) - Math.min(...vals) || 1;
    const thresh = range * 0.12;
    const idx = new Set([0, n - 1]);
    for (let i = 1; i < n - 1; i++) {
      const prev = vals[i - 1], cur = vals[i], next = vals[i + 1];
      const isMax = cur >= prev && cur >= next && (cur - Math.min(prev, next) >= thresh);
      const isMin = cur <= prev && cur <= next && (Math.max(prev, next) - cur >= thresh);
      if (isMax || isMin) idx.add(i);
    }
    return [...idx].sort((a, b) => a - b);
  }

  window.lineChart = function (container, seriesInput, opts) {
    opts = opts || {};
    container.innerHTML = "";

    const isMulti = Array.isArray(seriesInput) && seriesInput.length > 0 && Array.isArray(seriesInput[0].points);
    const series = (isMulti ? seriesInput : [{ points: seriesInput || [], color: "#f59e0b", dot: "#10b981", primary: true }])
      .filter(s => s.points && s.points.length);

    if (!series.length) {
      const d = document.createElement("div");
      d.className = "empty";
      d.textContent = opts.emptyText || "Sin datos todavía.";
      container.appendChild(d);
      return;
    }

    const data = series[0].points;
    const innerW = W - PAD.l - PAD.r;
    const innerH = H - PAD.t - PAD.b;
    const n = data.length;
    const invert = !!opts.invert;
    const fmt = opts.format || (v => v);

    const maxVal = Math.max(...series.flatMap(s => s.points.map(p => p.value)));
    const base = niceScale(maxVal);
    let dmin = opts.domainMin != null ? opts.domainMin : 0;
    let dmax = opts.domainMax != null ? opts.domainMax : base.max;
    if (dmax === dmin) dmax = dmin + 1;
    const ticks = opts.ticks || base.arr;

    const x = i => (n === 1 ? PAD.l + innerW / 2 : PAD.l + (innerW * i) / (n - 1));
    const frac = v => (v - dmin) / (dmax - dmin);
    const y = v => PAD.t + innerH * (invert ? frac(v) : 1 - frac(v));

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", style: "display:block" });

    ticks.forEach(v => {
      const yy = y(v);
      svg.appendChild(el("line", { x1: PAD.l, x2: W - PAD.r, y1: yy, y2: yy,
        stroke: "#2d3449", "stroke-width": 1 }));
      svg.appendChild(el("text", { x: PAD.l - 6, y: yy + 3, "text-anchor": "end",
        fill: "#9aa8c9", "font-size": 10 }, fmt(v)));
    });

    const stepLbl = Math.ceil(n / 8);
    data.forEach((p, i) => {
      if (i % stepLbl === 0 || i === n - 1) {
        svg.appendChild(el("text", { x: x(i), y: H - PAD.b + 16, "text-anchor": "middle",
          fill: "#9aa8c9", "font-size": 10 }, p.label));
      }
    });

    // Shaded area: between the two series when there's a comparison (e.g. tú
    // vs líder) — drawn first, underneath both lines — or from the lone
    // series down to the baseline, in upward (points) mode.
    if (series.length >= 2) {
      const a = series[0].points, b = series[1].points;
      const len = Math.min(a.length, b.length);
      if (len > 1) {
        let d = `M ${x(0)} ${y(a[0].value)}`;
        for (let i = 1; i < len; i++) d += ` L ${x(i)} ${y(a[i].value)}`;
        for (let i = len - 1; i >= 0; i--) d += ` L ${x(i)} ${y(b[i].value)}`;
        d += " Z";
        svg.appendChild(el("path", { d, fill: "rgba(245,158,11,.14)", stroke: "none" }));
      }
    } else if (series[0].points.length > 1 && !invert) {
      const pts = series[0].points;
      let d = `M ${x(0)} ${y(pts[0].value)}`;
      pts.forEach((p, i) => { d += ` L ${x(i)} ${y(p.value)}`; });
      d += ` L ${x(pts.length - 1)} ${y(dmin)} L ${x(0)} ${y(dmin)} Z`;
      svg.appendChild(el("path", { d, fill: "rgba(245,158,11,.12)", stroke: "none" }));
    }

    series.forEach((s, si) => {
      const pts = s.points;
      const primary = si === 0;
      const lineColor = s.color || (primary ? "#f59e0b" : "#4edea3");
      const dotColor = s.dot || lineColor;

      if (pts.length > 1) {
        let dl = `M ${x(0)} ${y(pts[0].value)}`;
        pts.forEach((p, i) => { if (i) dl += ` L ${x(i)} ${y(p.value)}`; });
        svg.appendChild(el("path", { d: dl, fill: "none", stroke: lineColor, "stroke-width": primary ? 2.5 : 2,
          "stroke-dasharray": s.dashed ? "5 4" : null, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      }

      const labeled = opts.pointLabels ? new Set(peakIndices(pts)) : new Set();
      pts.forEach((p, i) => {
        const last = i === pts.length - 1;
        const g = el("g", {});
        g.appendChild(el("circle", { cx: x(i), cy: y(p.value), r: last ? 5 : (primary ? 3.5 : 2.8),
          fill: last ? lineColor : dotColor, stroke: "#0b1326", "stroke-width": 1.5 }));
        g.appendChild(el("title", {}, p.tooltip || `${p.label}: ${fmt(p.value)}`));
        svg.appendChild(g);

        if (labeled.has(i)) {
          // Above the point, but flip below if too close to the top edge. The
          // secondary series sits further out so its labels don't collide with
          // the primary series' labels when both peak near the same x.
          const off = primary ? 9 : 17;
          const above = y(p.value) - off > PAD.t + 6;
          svg.appendChild(el("text", {
            x: x(i), y: y(p.value) + (above ? -off : off + 6), "text-anchor": "middle",
            fill: primary ? "#dae2fd" : lineColor, "font-size": 9, "font-weight": 700,
          }, fmt(p.value)));
        }
      });
    });

    container.appendChild(svg);

    if (isMulti && series.length > 1) {
      const legend = document.createElement("div");
      legend.style.cssText = "display:flex; gap:1rem; justify-content:center; margin-top:.3rem; font-size:.78rem;";
      legend.innerHTML = series.map(s =>
        `<span style="display:inline-flex; align-items:center; gap:.35rem; color:#9aa8c9">
           <span style="width:.6rem; height:.6rem; border-radius:50%; background:${s.color || (s.primary ? "#f59e0b" : "#4edea3")}; display:inline-block"></span>${s.name || ""}</span>`
      ).join("");
      container.appendChild(legend);
    }
  };
})();
