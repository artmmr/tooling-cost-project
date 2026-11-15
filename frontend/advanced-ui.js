/* Detailed analysis: summary bar, assumptions summary, "Try this" scenarios, history, link and print. */
const AdvancedUI = (() => {
  const $ = id => document.getElementById(id);
  const HISTORY_KEY = "tooling-history-v1";
  const FREIGHT_DEFAULTS = {"road-load": 18000, "sea-load": 27000, "road-journeys": 2, "sea-journeys": 2};
  const COLLAPSE_QUERY = window.matchMedia?.("(max-width: 720px)");
  let lastResult = null;
  let lastReport = null;
  let pendingChange = null;   // {before, label, fromPrice} while a "Try this" recalculates
  let undoScenario = null;
  let toastTimer = null;

  /* --- Formatting ---------------------------------------------------- */

  function money0(euros) {
    const factor = currencyFactor();
    if (!factor || !Number.isFinite(euros)) return "—";
    return `${displayCurrency === "EUR" ? "€" : "$"}${fmtMoneyAmount(euros * factor)}`;
  }

  function toast(message) {
    const element = $("sb-toast");
    element.textContent = message;
    element.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { element.hidden = true; }, 4000);
  }

  /* --- Scenarios: capture, restore, try ----------------------------- */

  const value = id => $(id).value;

  function capture() {
    return {
      country: value("inp-country"), process: value("inp-process"), material: value("inp-workpiece-material"),
      detail: value("inp-material-detail"), l: value("inp-l"), w: value("inp-w"), h: value("inp-h"),
      t: value("inp-material-thickness"), qty: value("inp-expected-cycles"), sets: value("inp-pqty"),
      tol: value("inp-tolerance"), finish: value("inp-surface-finish"), cooling: value("inp-cooling"),
      sizing: value("inp-sizing-mode"), overrides: WorkbookUI.exportOverrides(), forcedFamily,
    };
  }

  function setField(id, next) {
    if (next == null || next === "") return;
    const element = $(id);
    if (element.tagName === "SELECT" && ![...element.options].some(o => o.value === String(next))) return;
    element.value = next;
    element.dispatchEvent(new Event(element.tagName === "SELECT" ? "change" : "input", {bubbles: true}));
  }

  /* Re-apply the part after a process change, which loads the process's example part. */
  function applyPart(scenario) {
    setField("inp-workpiece-material", scenario.material);
    setField("inp-material-detail", scenario.detail);
    if (WorkbookUI.current()) setField("inp-sizing-mode", scenario.sizing === "reference" ? "reference" : "part_scaled");
    for (const [id, key] of [["inp-l", "l"], ["inp-w", "w"], ["inp-h", "h"], ["inp-material-thickness", "t"],
                             ["inp-expected-cycles", "qty"], ["inp-tolerance", "tol"], ["inp-surface-finish", "finish"],
                             ["inp-cooling", "cooling"]]) {
      setField(id, scenario[key]);
    }
    if (scenario.sets && !WorkbookUI.current()) setField("inp-pqty", scenario.sets);
  }

  async function restore(scenario) {
    if (scenario.country !== value("inp-country")) {
      $("inp-country").value = scenario.country;
      await loadCountryDefaults(scenario.country);
    }
    if (scenario.process !== value("inp-process")) setField("inp-process", scenario.process);
    applyPart(scenario);
    setField("inp-pqty", scenario.sets);
    WorkbookUI.importOverrides(scenario.overrides);
    forcedFamily = scenario.forcedFamily;
    currentToolingMaterialFamily = null;
    await calculateAndRender();
  }

  async function tryOption(kind, option, label) {
    if (!lastResult) return;
    const before = capture();
    pendingChange = {before, label, fromPrice: lastResult.total_price};
    if (kind === "country") {
      $("inp-country").value = option;
      await loadCountryDefaults(option);
    } else if (kind === "process") {
      setField("inp-process", option);
      applyPart(before);
      if (WorkbookUI.current()) setField("inp-pqty", "1");
    } else if (kind === "material") {
      if (WorkbookUI.current()) {
        WorkbookUI.setAllMaterial(option);
      } else {
        forcedFamily = option;
        currentToolingMaterialFamily = null;
      }
    }
    await calculateAndRender();
    document.getElementById("summary-bar").scrollIntoView?.({block: "nearest"});
  }

  async function undo() {
    if (!undoScenario) return;
    const scenario = undoScenario;
    undoScenario = null;
    $("sb-change").hidden = true;
    pendingChange = null;
    await restore(scenario);
    toast("Previous inputs restored.");
  }

  /* --- Summary bar ---------------------------------------------------- */

  function onResult(result, report) {
    lastResult = result;
    lastReport = report;
    const bar = $("summary-bar");
    bar.hidden = false;
    measureBar();
    $("sb-price").textContent = money0(result.total_price);
    $("sb-range").textContent = `${money0(result.total_price * 0.8)} – ${money0(result.total_price * 1.3)}`;
    const life = report?.tool_life;
    $("sb-per-part").textContent = money0(report ? report.tooling_per_part : result.total_price / Number(value("inp-expected-cycles")));
    $("sb-lifetime").textContent = money0(life ? life.lifetime_cost : result.total_price);
    $("sb-life-note").textContent = life?.replacements ? `incl. ${life.replacements} replacement set${life.replacements > 1 ? "s" : ""}` : "no replacements";
    $("sb-state").textContent = "Up to date";
    $("sb-state").dataset.stale = "false";
    if (pendingChange) {
      undoScenario = pendingChange.before;
      $("sb-change-text").textContent = `${pendingChange.label}: ${money0(pendingChange.fromPrice)} → ${money0(result.total_price)}`;
      $("sb-change").hidden = false;
      pendingChange = null;
    }
    updateAssumptions();
    saveHistory(result);
  }

  function onStale(message) {
    if (!lastResult) return;
    $("sb-state").textContent = message === "Updating estimate…" ? "Updating…" : "Out of date";
    $("sb-state").dataset.stale = "true";
  }

  function measureBar() {
    const height = $("summary-bar").offsetHeight || 0;
    document.documentElement.style.setProperty("--summary-bar-height", `${height}px`);
  }

  /* --- Assumptions summary ------------------------------------------ */

  function freightEdited() {
    let count = 0;
    for (const [id, base] of Object.entries(FREIGHT_DEFAULTS)) {
      if (Number(value(id)) !== base) count++;
    }
    if (value("freight-allocation") !== "proportional") count++;
    for (const [id, base] of [["road-rate", 1400 / 250], ["sea-rate", 8000 / 19800 * 1.852]]) {
      if (Number.isFinite(canonicalMoney[id]) && Math.abs(canonicalMoney[id] - base) > 1e-6) count++;
    }
    return count;
  }

  function toolingEdited() {
    if (WorkbookUI.current() || !currentToolingDefaults) return 0;
    const pairs = [["inp-tool-density", "density_kg_m3"], ["inp-tool-mrr", "removal_rate_cm3_min"],
                   ["inp-milling-volume-factor", "milling_volume_factor"]];
    let count = pairs.filter(([id, key]) => Math.abs(Number(value(id)) - currentToolingDefaults[key]) > 1e-9).length;
    for (const [id, key] of [["inp-tool-price", "block_price_per_tonne"], ["inp-milling-tool-price", "milling_tool_price"],
                             ["inp-heat-treatment", "heat_treatment_eur_per_kg"]]) {
      if (Number.isFinite(canonicalMoney[id]) && Math.abs(canonicalMoney[id] - currentToolingDefaults[key]) > 1e-6) count++;
    }
    return count;
  }

  function updateAssumptions() {
    const country = $("inp-country").selectedOptions[0]?.textContent.trim() || "Country";
    const truck = Number(value("inp-truck")) || 0;
    const sea = Number(value("inp-sea")) || 0;
    const rate = Number(value("inp-fx"));
    const parts = [`${country} rates`, displayCurrency === "USD" && rate ? `USD at ${rate}` : displayCurrency,
                   truck || sea ? `freight ${fmt(truck, 0)} km${sea ? ` + ${fmt(sea, 0)} nm` : ""}` : "no freight"];
    $("assumptions-summary").textContent = parts.join(" · ");
    const edited = document.querySelectorAll("#assumptions input.modified").length + freightEdited() + toolingEdited()
      + (fxEdited ? 1 : 0) + WorkbookUI.overrideCount();
    const badge = $("assumptions-edited");
    badge.hidden = edited === 0;
    badge.textContent = `${edited} edited`;
  }

  /* --- Link, print, history ------------------------------------------ */

  function link() {
    const params = new URLSearchParams();
    const add = (key, id) => { const v = value(id); if (v !== "" && v != null) params.set(key, v); };
    add("country", "inp-country"); add("process", "inp-process"); add("material", "inp-workpiece-material");
    add("detail", "inp-material-detail"); add("l", "inp-l"); add("w", "inp-w"); add("h", "inp-h");
    add("t", "inp-material-thickness"); add("qty", "inp-expected-cycles"); add("sets", "inp-pqty");
    add("tol", "inp-tolerance"); add("finish", "inp-surface-finish"); add("cooling", "inp-cooling");
    add("truck", "inp-truck"); add("sea", "inp-sea");
    return `${location.origin}${location.pathname}?${params}`;
  }

  async function copyLink() {
    const url = link();
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copied. It opens these part inputs; edited rates and component settings are not included.");
    } catch {
      window.prompt("Copy this link:", url);
    }
  }

  function readHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch { return []; }
  }

  function saveHistory(result) {
    const entry = {
      url: link(), price: result.total_price, currency: displayCurrency, factor: currencyFactor() || 1, at: Date.now(),
      label: `${$("inp-process").selectedOptions[0]?.textContent.trim() || ""} · ${Number(value("inp-expected-cycles")).toLocaleString()} parts · ${value("inp-country")}`,
    };
    const items = [entry, ...readHistory().filter(item => item.url !== entry.url)].slice(0, 10);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(items)); } catch { /* History is optional. */ }
  }

  function renderHistory() {
    const items = readHistory();
    const panel = $("history-panel");
    panel.innerHTML = items.length
      ? `<p class="history-title">Recent estimates</p><ol>${items.map(item => `<li><a href="${escapeHtml(item.url)}">
          <span>${escapeHtml(item.label)}</span>
          <strong>${item.currency === "EUR" ? "€" : "$"}${fmtMoneyAmount(item.price * item.factor)}</strong>
          <small>${new Date(item.at).toLocaleString(undefined, {dateStyle: "short", timeStyle: "short"})}</small></a></li>`).join("")}</ol>
          <button type="button" id="history-clear" class="link-button">Clear history</button>`
      : `<p class="history-title">No saved estimates yet.</p>`;
    $("history-clear")?.addEventListener("click", () => {
      try { localStorage.removeItem(HISTORY_KEY); } catch { /* ignore */ }
      renderHistory();
    });
  }

  function toggleHistory(open) {
    const panel = $("history-panel");
    const show = open ?? panel.hidden;
    if (show) renderHistory();
    panel.hidden = !show;
    $("sb-history").setAttribute("aria-expanded", String(show));
  }

  /* --- Report navigation and phone layout -------------------------- */

  function setupReportNav() {
    const links = [...document.querySelectorAll("#report-nav a")];
    const targets = links.map(a => document.querySelector(a.getAttribute("href")));
    const mark = link => links.forEach(a => a.toggleAttribute("aria-current", a === link));
    let frame = 0;
    let lockedUntil = 0;
    /* The current section is the last one whose top has passed under the sticky bars; when two sections
       share a top edge (side-by-side cards) the first in the menu wins. */
    const update = () => {
      frame = 0;
      if (Date.now() < lockedUntil || $("report").hidden) return;
      const line = (parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--summary-bar-height")) || 0)
        + ($("report-nav").offsetHeight || 0) + 24;
      let best = null, bestTop = -Infinity;
      targets.forEach((target, i) => {
        if (!target) return;
        const top = Math.round(target.getBoundingClientRect().top);
        if (top <= line && top > bestTop) { best = links[i]; bestTop = top; }
      });
      const atEnd = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
      mark(atEnd && bestTop > -Infinity ? links.at(-1) : best);
    };
    window.addEventListener("scroll", () => { frame ||= requestAnimationFrame(update); }, {passive: true});
    links.forEach((a, i) => a.addEventListener("click", () => {
      const card = targets[i]?.closest(".collapsible") || targets[i]?.querySelector?.(".collapsible");
      if (card) expand(card, true);
      // Keep the clicked section highlighted while the smooth scroll settles.
      mark(a);
      lockedUntil = Date.now() + 900;
    }));
  }

  function expand(card, open) {
    card.classList.toggle("collapsed", !open);
    card.querySelector(".collapse-toggle")?.setAttribute("aria-expanded", String(open));
  }

  /* On phones every report card starts closed behind its heading. */
  function setupCollapsibles() {
    const cards = document.querySelectorAll("#report .result-card:not(.ai-card)");
    const apply = () => {
      const narrow = Boolean(COLLAPSE_QUERY?.matches);
      cards.forEach(card => {
        const heading = card.querySelector("h3");
        if (!heading) return;
        if (narrow && !card.classList.contains("collapsible")) {
          card.classList.add("collapsible");
          const button = document.createElement("button");
          button.type = "button";
          button.className = "collapse-toggle";
          button.setAttribute("aria-expanded", "false");
          button.textContent = heading.textContent;
          heading.replaceChildren(button);
          button.addEventListener("click", () => expand(card, card.classList.contains("collapsed")));
          expand(card, false);
        } else if (!narrow && card.classList.contains("collapsible")) {
          const button = heading.querySelector(".collapse-toggle");
          if (button) heading.textContent = button.textContent;
          card.classList.remove("collapsible", "collapsed");
        }
      });
    };
    apply();
    COLLAPSE_QUERY?.addEventListener?.("change", apply);
  }

  /* --- Wiring -------------------------------------------------------- */

  function init() {
    $("sb-edit").addEventListener("click", () => {
      document.querySelector('nav.tabs button[data-tab="calc"]').click();
      $("calc-heading").scrollIntoView({behavior: "smooth", block: "start"});
      setTimeout(() => $("inp-country").focus({preventScroll: true}), 400);
    });
    $("sb-copy").addEventListener("click", copyLink);
    $("sb-print").addEventListener("click", () => {
      document.querySelectorAll("#report details, .price-card details").forEach(d => d.setAttribute("open", ""));
      document.querySelectorAll("#report .collapsible").forEach(card => expand(card, true));
      window.print();
    });
    $("sb-history").addEventListener("click", event => { event.stopPropagation(); toggleHistory(); });
    document.addEventListener("click", event => {
      if (!$("history-panel").hidden && !event.target.closest(".history-wrap")) toggleHistory(false);
    });
    document.addEventListener("keydown", event => { if (event.key === "Escape") toggleHistory(false); });
    $("sb-undo").addEventListener("click", undo);
    document.querySelectorAll(".presets [data-qty]").forEach(button => button.addEventListener("click", () => {
      setField("inp-expected-cycles", button.dataset.qty);
    }));
    $("panel-calc").addEventListener("input", () => setTimeout(updateAssumptions, 0));
    $("panel-calc").addEventListener("change", () => setTimeout(updateAssumptions, 0));
    $("report").addEventListener("click", event => {
      const button = event.target.closest("[data-try-kind]");
      if (button) tryOption(button.dataset.tryKind, button.dataset.tryValue, button.dataset.tryLabel);
    });
    window.addEventListener("resize", measureBar);
    setupReportNav();
    setupCollapsibles();
    updateAssumptions();
  }

  return {init, onResult, onStale, tryOption, updateAssumptions, capture, restore};
})();
