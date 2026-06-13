/* Tiny dependency-free SVG line chart. Responsive, "nice" scale, supports an
   inverted axis (for ranking: #1 at the top) and per-point value labels.
     lineChart(container, [{label, value, tooltip}], {
       invert, domainMin, domainMax, ticks, pointLabels, format, emptyText });
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
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }

  window.lineChart = function (container, data, opts) {
    opts = opts || {};
    container.innerHTML = "";
    if (!data || !data.length) {
      const d = document.createElement("div");
      d.className = "empty";
      d.textContent = opts.emptyText || "Sin datos todavía.";
      container.appendChild(d);
      return;
    }

    const innerW = W - PAD.l - PAD.r;
    const innerH = H - PAD.t - PAD.b;
    const n = data.length;
    const invert = !!opts.invert;
    const fmt = opts.format || (v => v);

    const maxVal = Math.max(...data.map(p => p.value));
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
        stroke: "#26342b", "stroke-width": 1 }));
      svg.appendChild(el("text", { x: PAD.l - 6, y: yy + 3, "text-anchor": "end",
        fill: "#8aa394", "font-size": 10 }, fmt(v)));
    });

    const stepLbl = Math.ceil(n / 8);
    data.forEach((p, i) => {
      if (i % stepLbl === 0 || i === n - 1) {
        svg.appendChild(el("text", { x: x(i), y: H - PAD.b + 16, "text-anchor": "middle",
          fill: "#8aa394", "font-size": 10 }, p.label));
      }
    });

    // Area fill only for the upward (points) mode.
    if (n > 1 && !invert) {
      let d = `M ${x(0)} ${y(data[0].value)}`;
      data.forEach((p, i) => { d += ` L ${x(i)} ${y(p.value)}`; });
      d += ` L ${x(n - 1)} ${y(dmin)} L ${x(0)} ${y(dmin)} Z`;
      svg.appendChild(el("path", { d, fill: "rgba(212,175,55,.12)", stroke: "none" }));
    }
    if (n > 1) {
      let dl = `M ${x(0)} ${y(data[0].value)}`;
      data.forEach((p, i) => { if (i) dl += ` L ${x(i)} ${y(p.value)}`; });
      svg.appendChild(el("path", { d: dl, fill: "none", stroke: "#d4af37", "stroke-width": 2.5,
        "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }

    data.forEach((p, i) => {
      const last = i === n - 1;
      const g = el("g", {});
      g.appendChild(el("circle", { cx: x(i), cy: y(p.value), r: last ? 5 : 3.5,
        fill: last ? "#d4af37" : "#1f7a4d", stroke: "#0f1411", "stroke-width": 1.5 }));
      g.appendChild(el("title", {}, p.tooltip || `${p.label}: ${fmt(p.value)}`));
      svg.appendChild(g);

      if (opts.pointLabels) {
        // Above the point, but flip below if too close to the top edge.
        const above = y(p.value) - 9 > PAD.t + 6;
        svg.appendChild(el("text", {
          x: x(i), y: y(p.value) + (above ? -9 : 15), "text-anchor": "middle",
          fill: "#eef3ef", "font-size": 11, "font-weight": 700,
        }, fmt(p.value)));
      }
    });

    container.appendChild(svg);
  };
})();
