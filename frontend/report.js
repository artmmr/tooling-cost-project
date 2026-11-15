/* Advanced production report: alternatives, risks, advice and the optional AI summary. */
const ReportUI = (() => {
  const FIT_LABELS = {strong: "Best fit", suitable: "Suitable", limited: "Limited", not_recommended: "Not recommended"};
  let reportSupported = true;
  let lastReport = null;
  let lastState = null;
  let summaryRequest = null;

  const $ = id => document.getElementById(id);
  const cur = () => (typeof displayCurrency === "string" ? displayCurrency : "EUR");
  const factor = () => (typeof currencyFactor === "function" ? currencyFactor() : 1) || 1;
  function price(euros) {
    if (euros == null || !Number.isFinite(euros)) return "—";
    return `${cur() === "EUR" ? "€" : "$"}${fmtMoneyAmount(euros * factor())}`;
  }
  function delta(value, reference) {
    if (value == null || reference == null || !reference) return "";
    const pct = (value / reference - 1) * 100;
    if (Math.abs(pct) < 0.5) return `<span class="delta same">same price</span>`;
    return `<span class="delta ${pct < 0 ? "down" : "up"}">${pct < 0 ? "−" : "+"}${fmt(Math.abs(pct), 0)}%</span>`;
  }
  const fitBadge = fit => `<span class="fit-badge" data-fit="${fit}">${FIT_LABELS[fit] || fit}</span>`;

  /* --- Request ------------------------------------------------------ */

  async function request(state, signal) {
    if (reportSupported) {
      try {
        const report = await fetchJson("/api/advanced-report", {
          method: "POST", signal, headers: {"Content-Type": "application/json"}, body: JSON.stringify(state),
        });
        return {result: report.base, report};
      } catch (error) {
        // An older backend without the report still prices the tool.
        if (error.status !== 404) throw error;
        reportSupported = false;
      }
    }
    return {result: await requestCalculation(state, signal), report: null};
  }

  /* --- Render ------------------------------------------------------- */

  function markStale() {
    if (!lastReport) return;
    const chip = $("report-state");
    chip.textContent = "Out of date";
    chip.dataset.stale = "true";
  }

  function bars(container, rows) {
    const max = Math.max(...rows.map(r => r.value || 0), 1);
    container.innerHTML = rows.map(r => `
      <div class="bar-row${r.current ? " current" : ""}">
        <div class="bar-label"><span>${escapeHtml(r.label)}</span><strong>${r.text}</strong></div>
        <div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${Math.max(1.5, (r.value || 0) / max * 100).toFixed(1)}%"></div></div>
      </div>`).join("");
  }

  function materialCard(option, reference) {
    return `<article class="option-card${option.is_current ? " current" : ""}">
      <header><h4>${escapeHtml(option.name)}</h4>${fitBadge(option.fit)}</header>
      <p class="option-price">${option.price == null ? "<span class=\"muted\">Not priced</span>" : price(option.price)} ${option.is_current ? "<span class=\"current-tag\">Current estimate</span>" : delta(option.price, reference)}</p>
      ${option.lifetime_price != null && option.replacements ? `<p class="option-meta">Lifetime ${price(option.lifetime_price)}: ${option.replacements} replacement set${option.replacements > 1 ? "s" : ""} over this quantity</p>` : ""}
      ${option.heat_treatment ? `<p class="option-meta">Needs heat treatment</p>` : ""}
      <ul>${option.reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
    </article>`;
  }

  function processCard(option, reference) {
    return `<article class="option-card${option.is_current ? " current" : ""}">
      <header><h4>${escapeHtml(option.label)}</h4>${fitBadge(option.fit)}</header>
      <p class="option-price">${option.tooling_price == null ? "<span class=\"muted\">Not priced</span>" : price(option.tooling_price)} ${option.is_current ? "<span class=\"current-tag\">Your process</span>" : delta(option.tooling_price, reference)}</p>
      <dl class="option-facts">
        <div><dt>Tooling per part</dt><dd>${price(option.tooling_per_part)}</dd></div>
        <div><dt>Lifetime tooling</dt><dd>${price(option.lifetime_price ?? option.tooling_price)}</dd></div>
        <div><dt>Piece cost</dt><dd>${escapeHtml(option.piece_cost)}</dd></div>
        <div><dt>Typical tolerance</dt><dd>${escapeHtml(option.tolerance)}</dd></div>
        <div><dt>Economic quantity</dt><dd>${escapeHtml(option.economic_quantity)}</dd></div>
      </dl>
      <p class="option-text"><strong>Strengths:</strong> ${escapeHtml(option.strengths)}</p>
      <p class="option-text"><strong>Limits:</strong> ${escapeHtml(option.limits)}</p>
      ${option.notes.length ? `<ul class="option-notes">${option.notes.map(n => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : ""}
    </article>`;
  }

  function render(report, state) {
    const section = $("report");
    lastReport = report;
    lastState = state;
    resetSummary();
    if (!report) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    const chip = $("report-state");
    chip.textContent = "Up to date";
    chip.dataset.stale = "false";

    const base = report.base;
    $("rk-price").textContent = price(base.total_price);
    $("rk-price-note").textContent = base.tooling_concept || "Complete-tool estimate";
    $("rk-per-part").textContent = price(report.tooling_per_part);
    const life = report.tool_life;
    $("rk-per-part-note").textContent = life?.replacements
      ? `Lifetime cost over ${report.quantity.toLocaleString()} parts, including ${life.replacements} replacement set${life.replacements > 1 ? "s" : ""}`
      : `Spread over ${report.quantity.toLocaleString()} parts`;
    renderLife(life, report.quantity);
    const best = report.material_options.filter(o => o.fit === "strong" && o.price != null)
      .sort((a, b) => (a.lifetime_price ?? a.price) - (b.lifetime_price ?? b.price))[0];
    if (best?.family === "workbook_mix") {
      // The workbook's own grade selection is the best fit: name the grades, not the costing mix.
      $("rk-material").textContent = base.grade_candidates || base.recommended_material || "—";
      $("rk-material-note").textContent = base.grade_treatment ? `Treatment: ${base.grade_treatment}` : "Used in this estimate";
    } else {
      $("rk-material").textContent = best ? best.name : "—";
      $("rk-material-note").textContent = best ? (best.is_current ? "Used in this estimate" : `${price(best.price)} for the tool`) : "";
    }
    const cheapest = report.country_options.find(c => c.price != null);
    const current = report.country_options.find(c => c.is_current);
    $("rk-country").textContent = cheapest ? cheapest.name : "—";
    $("rk-country-note").textContent = cheapest && current && !cheapest.is_current
      ? `${price(cheapest.price)}, ${fmt((1 - cheapest.price / current.price) * 100, 0)}% below ${current.name}`
      : "Your selected country";

    bars($("rp-drivers"), report.cost_drivers.map(d => ({label: d.label, value: d.amount, text: `${price(d.amount)} · ${fmt(d.share * 100, 0)}%`})));

    $("rp-quantity").innerHTML = report.quantity_options.map(q => `
      <tr class="${q.is_current ? "current" : ""}">
        <th scope="row">${escapeHtml(q.band)}${q.is_current ? ' <span class="current-tag">Your quantity</span>' : ""}
          <span>${q.concept ? escapeHtml(q.concept) + " · " : ""}priced at ${q.quantity.toLocaleString()} parts</span></th>
        <td class="num">${price(q.price)}</td>
        <td class="num">${price(q.lifetime_price)}${q.replacements ? `<span>+${q.replacements} set${q.replacements > 1 ? "s" : ""}</span>` : ""}</td>
        <td class="num">${price(q.per_part)}</td>
      </tr>`).join("");

    const reference = report.material_options.find(o => o.is_current)?.price ?? base.total_price;
    const shown = report.material_options.filter(o => o.fit !== "not_recommended");
    const hidden = report.material_options.filter(o => o.fit === "not_recommended");
    $("rp-material-basis").textContent = report.material_basis;
    $("rp-materials").innerHTML = shown.map(o => materialCard(o, reference)).join("");
    $("rp-materials-hidden").innerHTML = hidden.map(o => materialCard(o, reference)).join("");
    $("rp-materials-hidden").closest("details").hidden = !hidden.length;
    $("rp-materials-hidden-summary").textContent = `Not recommended for this process (${hidden.length})`;

    renderMatrix(report.matrix);
    $("rp-processes").innerHTML = report.process_options.map(o => processCard(o, base.total_price)).join("");

    const rate = Number(lastState?.eur_to_usd);
    $("rp-country-basis").textContent = report.country_basis
      + (rate > 0 ? ` Rate used: 1 EUR = ${rate} USD. All prices are shown in ${cur()}.` : "");
    const unpriced = report.country_options.filter(c => c.price == null).map(c => c.name);
    if (unpriced.length) $("rp-country-basis").textContent += ` Not compared without an exchange rate: ${unpriced.join(", ")}.`;
    bars($("rp-countries"), report.country_options.filter(c => c.price != null).map(c => ({
      label: c.currency === "USD" ? `${c.name} (costed in USD)` : c.name, value: c.price, current: c.is_current,
      text: `${price(c.price)}${c.is_current ? "" : " " + delta(c.price, current?.price)}`,
    })));

    $("rp-risks").innerHTML = report.risks.map(r => `
      <div><dt>${escapeHtml(sentenceCase(r.risk))}</dt><dd>${escapeHtml(r.explanation)}</dd><dd class="mitigation"><strong>Reduce it:</strong> ${escapeHtml(r.mitigation)}</dd></div>`).join("")
      || "<div><dd>No specific elevated risk was identified by these rules.</dd></div>";
    $("rp-design").innerHTML = report.design_notes.map(n => `<li>${escapeHtml(n)}</li>`).join("");
    $("rp-method").innerHTML = report.method_notes.map(n => `<li>${escapeHtml(n)}</li>`).join("");
  }

  function renderLife(life, quantity) {
    if (!life) return;
    $("rl-life").textContent = life.modelled && life.life ? `${life.life.toLocaleString()} cycles` : "Not counted in parts";
    $("rl-life-note").textContent = life.modelled ? `Your run: ${life.shots.toLocaleString()} cycles per tool` : "";
    $("rl-replacements").textContent = life.modelled ? String(life.replacements) : "—";
    $("rl-replacements-note").textContent = life.replacements ? `${price(life.replacement_cost)} for replacement working parts` : "The first tool should last the whole run";
    $("rl-lifetime").textContent = price(life.lifetime_cost);
    $("rl-lifetime-note").textContent = `${price(life.lifetime_per_part)} per part over ${quantity.toLocaleString()} parts`;
    $("rl-items").innerHTML = life.items.filter(i => i.life).map(i =>
      `<li><strong>${escapeHtml(i.component)}</strong>: about ${i.life.toLocaleString()} cycles${i.replacements ? `, replaced ${i.replacements} time${i.replacements > 1 ? "s" : ""} (${price(i.replacement_cost)})` : ", no replacement needed"}.</li>`).join("");
    $("rl-basis").textContent = life.basis;
  }

  function renderMatrix(matrix) {
    const chip = $("rp-matrix-chip");
    $("rp-matrix-body").hidden = !matrix?.covered;
    if (!matrix?.covered) {
      chip.textContent = "Not covered";
      chip.dataset.match = "";
      $("rp-matrix-summary").textContent = matrix?.message || "The process matrix is not available.";
      return;
    }
    const subject = `${matrix.material} — ${matrix.form}`;
    chip.textContent = matrix.current_process_listed ? "Matches your process" : "Different from your process";
    chip.dataset.match = matrix.current_process_listed ? "true" : "false";
    $("rp-matrix-summary").innerHTML = `<strong>${escapeHtml(subject)}</strong>`
      + ` <span class="muted">(${matrix.chosen_by === "user" ? "chosen by you" : "matched from the part material; choose another under Material grade and form"})</span><br>`
      + `For ${escapeHtml(matrix.band)} parts: <strong>${escapeHtml(matrix.route)}</strong>`
      + (matrix.no_tooling ? ` (${escapeHtml(matrix.tooling)}).` : ` with <strong>${escapeHtml(matrix.tooling)}</strong> tooling.`)
      + (matrix.comment ? ` ${escapeHtml(matrix.comment)}` : "");
    const process = document.getElementById("inp-process")?.value;
    const aliases = {stamping: "punching_blanking", plastic_molding: "plastic_injection", metal_molding: "die_casting",
      forming: "sheet_hydroforming", deep_drawing: "sheet_hydroforming"};
    const code = aliases[process] || process;
    $("rp-matrix-bands").innerHTML = matrix.bands.map(b => `
      <tr class="${b.is_current ? "current" : ""}">
        <th scope="row">${escapeHtml(b.band)}${b.is_current ? ' <span class="current-tag">Your quantity</span>' : ""}</th>
        <td>${escapeHtml(b.route)}${b.processes.includes(code) ? ' <span class="current-tag">Your process</span>' : ""}${b.no_tooling ? '<span>No dedicated tool</span>' : ""}</td>
        <td>${escapeHtml(b.tooling)}</td>
      </tr>`).join("");
    $("rp-matrix-grades").innerHTML = matrix.grades.map(g => `
      <div><dt>${escapeHtml(g.name)}</dt><dd>${escapeHtml(g.typical_use)} · ${escapeHtml(g.hardness)}</dd>${g.note ? `<dd>${escapeHtml(g.note)}</dd>` : ""}</div>`).join("")
      || `<div><dd>No dedicated tool grade at this quantity${matrix.no_tooling ? ": the matrix recommends a route without a dedicated tool." : "."}</dd></div>`;
  }

  /* --- AI summary ---------------------------------------------------- */

  function resetSummary() {
    summaryRequest?.abort();
    summaryRequest = null;
    $("ai-output").hidden = true;
    $("ai-btn").disabled = false;
    $("ai-btn").textContent = "Write AI summary";
    const status = $("ai-status");
    status.classList.remove("err");
    status.textContent = "Writes a short summary of this report. It uses only the figures calculated here, and takes about 5–15 seconds.";
  }

  async function writeSummary() {
    if (!lastReport || !lastState) return;
    if ($("report-state").dataset.stale === "true") {
      $("ai-status").textContent = "Wait for the report to update first.";
      return;
    }
    const controller = new AbortController();
    summaryRequest = controller;
    const button = $("ai-btn");
    const status = $("ai-status");
    button.disabled = true;
    button.textContent = "Writing…";
    status.classList.remove("err");
    status.textContent = "Writing the summary…";
    try {
      const body = {request: lastState, currency: cur()};
      if (cur() === "USD") body.eur_to_usd = factor();
      const summary = await fetchJson("/api/advanced-report/summary", {
        method: "POST", signal: controller.signal, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
      });
      if (summaryRequest !== controller) return;
      $("ai-headline").textContent = summary.headline;
      $("ai-recommendations").innerHTML = summary.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join("");
      $("ai-watch").innerHTML = summary.watch_outs.map(r => `<li>${escapeHtml(r)}</li>`).join("");
      $("ai-model").textContent = `Written by ${summary.model} from the figures in this report${summary.cached ? " (saved copy)" : ""}. Check it before relying on it.`;
      $("ai-output").hidden = false;
      status.textContent = "";
      button.textContent = "Summary written";
    } catch (error) {
      if (error.name === "AbortError" || summaryRequest !== controller) return;
      status.classList.add("err");
      status.textContent = error.status === 404
        ? "This server does not offer AI summaries yet."
        : `Could not write the summary: ${error.message}`;
      button.disabled = false;
      button.textContent = "Try again";
    } finally {
      if (summaryRequest === controller) summaryRequest = null;
    }
  }

  /* --- Prefill from the quick-price page ---------------------------- */

  async function applyUrlPrefill() {
    const params = new URLSearchParams(location.search);
    if (!params.has("process")) return false;
    const set = (id, value) => {
      if (value == null || value === "") return;
      const element = $(id);
      if (element.tagName === "SELECT" && ![...element.options].some(o => o.value === value)) return;
      element.value = value;
      element.dispatchEvent(new Event(element.tagName === "SELECT" ? "change" : "input", {bubbles: true}));
    };
    const country = params.get("country");
    const countrySelect = $("inp-country");
    if (country && country !== countrySelect.value && [...countrySelect.options].some(o => o.value === country)) {
      countrySelect.value = country;
      await loadCountryDefaults(country);
    }
    set("inp-process", params.get("process"));
    set("inp-workpiece-material", params.get("material"));
    set("inp-material-detail", params.get("detail"));
    if (WorkbookUI.current()) set("inp-sizing-mode", "part_scaled");
    set("inp-l", params.get("l"));
    set("inp-w", params.get("w"));
    set("inp-h", params.get("h"));
    set("inp-material-thickness", params.get("t"));
    const quantity = params.get("qty");
    set("inp-expected-cycles", quantity);
    if (quantity && !WorkbookUI.current()) set("inp-cycles", legacyBandFor(Number(quantity)));
    set("inp-pqty", params.get("sets"));
    set("inp-tolerance", params.get("tol"));
    set("inp-surface-finish", params.get("finish"));
    set("inp-truck", params.get("truck"));
    set("inp-sea", params.get("sea"));
    await calculateAndRender();
    return true;
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("ai-btn").addEventListener("click", writeSummary);
  });

  return {request, render, markStale, applyUrlPrefill};
})();
