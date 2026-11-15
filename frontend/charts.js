/* Report charts: one stacked cost bar and the cost-per-part curve. Plain SVG/HTML, no library. */
const CostCharts = (() => {
  /* Cost groups keep a fixed colour slot (colour follows the group, never its rank). */
  const GROUPS = [
    {key: "steel", label: "Tool steel", slot: 1, keys: ["material", "heat"]},
    {key: "machining", label: "Machining and construction", slot: 2, keys: ["machining", "construction", "cutters", "energy"]},
    {key: "design", label: "Design", slot: 3, keys: ["design"]},
    {key: "base", label: "Tool base and standard parts", slot: 4, keys: ["base"]},
    {key: "tryout", label: "Assembly, tryout and cooling", slot: 5, keys: ["tryout", "cooling"]},
    {key: "commercial", label: "Overhead and margin", slot: 6, keys: ["commercial"]},
    {key: "other", label: "Transport and purchased parts", slot: "other", keys: ["transport", "purchased"]},
  ];

  let tooltip = null;
  function tip() {
    if (!tooltip) {
      tooltip = document.createElement("div");
      tooltip.className = "chart-tooltip";
      tooltip.setAttribute("role", "status");
      tooltip.hidden = true;
      document.body.append(tooltip);
    }
    return tooltip;
  }
  function showTip(html, x, y) {
    const t = tip();
    t.innerHTML = html;
    t.hidden = false;
    const box = t.getBoundingClientRect();
    const left = Math.min(Math.max(8, x + 14), window.innerWidth - box.width - 8);
    const top = y - box.height - 12 < 8 ? y + 16 : y - box.height - 12;
    t.style.transform = `translate(${left}px, ${top}px)`;
  }
  function hideTip() {
    if (tooltip) tooltip.hidden = true;
  }
  function bindHover(element, html) {
    element.addEventListener("pointermove", event => showTip(html, event.clientX, event.clientY));
    element.addEventListener("pointerleave", hideTip);
    element.addEventListener("focus", () => {
      const r = element.getBoundingClientRect();
      showTip(html, r.left + r.width / 2, r.top);
    });
    element.addEventListener("blur", hideTip);
  }

  function stacked(container, drivers, money) {
    const byKey = Object.fromEntries(drivers.map(d => [d.key, d.amount]));
    const groups = GROUPS.map(g => ({...g, amount: g.keys.reduce((sum, k) => sum + (byKey[k] || 0), 0)}))
      .filter(g => g.amount > 0.005);
    const total = groups.reduce((sum, g) => sum + g.amount, 0) || 1;
    const share = g => g.amount / total * 100;
    container.innerHTML = `
      <div class="stack-bar" role="img" aria-label="Cost split: ${groups.map(g => `${g.label} ${share(g).toFixed(0)}%`).join(", ")}">
        ${groups.map(g => `<span class="stack-seg" tabindex="0" data-slot="${g.slot}" style="flex-basis:${share(g).toFixed(2)}%"></span>`).join("")}
      </div>
      <table class="legend-table">
        <tbody>${groups.map(g => `<tr>
          <th scope="row"><span class="swatch" data-slot="${g.slot}" aria-hidden="true"></span>${escapeHtml(g.label)}</th>
          <td class="num">${money(g.amount)}</td><td class="num muted-num">${share(g).toFixed(0)}%</td></tr>`).join("")}</tbody>
      </table>`;
    container.querySelectorAll(".stack-seg").forEach((segment, i) => {
      const g = groups[i];
      bindHover(segment, `<strong>${escapeHtml(g.label)}</strong><span>${money(g.amount)} · ${share(g).toFixed(1)}%</span>`);
    });
  }

  const shortQty = q => q >= 1e6 ? `${+(q / 1e6).toFixed(1)}M` : q >= 1e3 ? `${+(q / 1e3).toFixed(1)}k` : String(q);

  /* Lifetime tooling cost per part against quantity, both on log scales (values span several decades). */
  function perPart(container, options, money) {
    const points = options.filter(o => o.per_part > 0).map(o => ({...o}));
    if (points.length < 2) { container.innerHTML = ""; return; }
    const W = 640, H = 230, m = {l: 64, r: 16, t: 18, b: 34};
    const xs = points.map(p => Math.log10(p.quantity));
    const ys = points.map(p => Math.log10(p.per_part));
    const x0 = Math.min(...xs) - 0.15, x1 = Math.max(...xs) + 0.15;
    const y0 = Math.floor(Math.min(...ys)), y1 = Math.ceil(Math.max(...ys));
    const X = v => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r);
    const Y = v => H - m.b - (v - y0) / ((y1 - y0) || 1) * (H - m.t - m.b);
    // Axis money without trailing zeros (€10, €0.1).
    const axisMoney = v => money(v).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
    // Quantity labels: drop one that would collide with its neighbour (your quantity wins).
    const showLabel = points.map(() => true);
    points.forEach((p, i) => {
      const j = i - 1;
      if (j < 0 || Math.abs(X(xs[i]) - X(xs[j])) >= 34) return;
      if (points[i].is_current) showLabel[j] = false; else showLabel[i] = false;
    });
    const grid = [];
    for (let e = y0; e <= y1; e++) {
      grid.push(`<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${Y(e)}" y2="${Y(e)}"/>
        <text class="axis" x="${m.l - 8}" y="${Y(e) + 4}" text-anchor="end">${axisMoney(10 ** e)}</text>`);
    }
    const path = points.map((p, i) => `${i ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join(" ");
    container.innerHTML = `
      <p class="chart-title">Tooling cost per part by quantity <span>(lifetime, log scales)</span></p>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tooling cost per part falls from ${money(points[0].per_part)} at ${shortQty(points[0].quantity)} parts to ${money(points.at(-1).per_part)} at ${shortQty(points.at(-1).quantity)} parts">
        ${grid.join("")}
        <path class="line" d="${path}"/>
        ${points.map((p, i) => `
          <g class="pt${p.is_current ? " current" : ""}" tabindex="0">
            <circle class="hit" cx="${X(xs[i])}" cy="${Y(ys[i])}" r="14"/>
            <circle class="dot" cx="${X(xs[i])}" cy="${Y(ys[i])}" r="${p.is_current ? 6 : 4.5}"/>
            ${showLabel[i] ? `<text class="axis" x="${X(xs[i])}" y="${H - m.b + 18}" text-anchor="middle">${shortQty(p.quantity)}</text>` : ""}
            ${p.is_current ? `<text class="callout" x="${X(xs[i])}" y="${Y(ys[i]) - 12}" text-anchor="middle">Your quantity</text>` : ""}
          </g>`).join("")}
      </svg>`;
    container.querySelectorAll(".pt").forEach((g, i) => {
      const p = points[i];
      bindHover(g, `<strong>${p.quantity.toLocaleString()} parts</strong><span>${money(p.per_part)} per part</span>`
        + `<span>Lifetime ${money(p.lifetime_price ?? p.price)}${p.replacements ? ` · ${p.replacements} replacement set${p.replacements > 1 ? "s" : ""}` : ""}</span>`);
    });
  }

  return {stacked, perPart};
})();
