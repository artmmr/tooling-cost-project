/* Quick price: a few inputs, standard assumptions, one price. */
(() => {
  const $ = id => document.getElementById(id);
  const MONEY_KEYS = ["engineering_rate", "assembly_rate", "cnc_3_axis_rate", "cnc_5_axis_rate", "edm_rate", "grinding_rate", "electricity_eur_kwh"];
  const ASSUMPTION_KEYS = ["engineering_rate", "assembly_rate", "cnc_3_axis_rate", "cnc_5_axis_rate", "edm_rate", "grinding_rate",
    "electricity_eur_kwh", "machine_efficiency", "operator_efficiency", "overhead_rate", "margin_rate"];
  const RANGE_LOW = 0.8, RANGE_HIGH = 1.3;
  const countryCache = {};
  const touched = new Set();
  let catalog = null;
  let calculated = false;
  let revision = 0;
  let timer = null;
  let active = null;
  let ecbRequest = null;
  // Display currency of the latest result and its conversion from the API's euros.
  let shown = {currency: "EUR", factor: 1};

  const workbookProcess = code => catalog?.processes.find(p => p.code === code);
  const euros = value => `${shown.currency === "USD" ? "$" : "€"}${fmtMoneyAmount(value * shown.factor)}`;

  async function ecbRate() {
    ecbRequest ||= fetchJson("/api/fx/eur-usd").catch(error => {
      ecbRequest = null;
      throw error;
    });
    return ecbRequest;
  }

  function setStatus(text, isError = false) {
    $("b-status").textContent = text;
    $("b-status").classList.toggle("err", isError);
  }

  function setState(text, stale) {
    $("b-state").textContent = text;
    $("b-state").dataset.stale = stale ? "true" : "false";
  }

  async function countryProfile(code) {
    countryCache[code] ||= fetchJson(`/api/countries/${code}`).catch(error => {
      delete countryCache[code];
      throw error;
    });
    return countryCache[code];
  }

  function onProcessChange() {
    const code = $("b-process").value;
    const definition = workbookProcess(code);
    const {options, preferred} = materialsForProcess(code, Boolean(definition));
    const previous = $("b-material").value;
    fillSelect("b-material", options);
    $("b-material").value = options.some(o => o.value === previous) && touched.has("b-material") ? previous : preferred;
    $("b-sets-label").textContent = definition ? "Identical tools" : "Cavities per tool";
    $("b-process-note").textContent = definition ? `Reference part for this process: ${definition.part_description}.` : "";
    // Until the visitor types their own part, show the process's reference part so a first estimate works.
    if (definition && !["b-l", "b-w", "b-h"].some(id => touched.has(id))) {
      $("b-l").value = definition.reference_part.length_mm;
      $("b-w").value = definition.reference_part.width_mm;
      $("b-h").value = definition.reference_part.height_mm;
    }
    if (definition && !touched.has("b-t")) $("b-t").value = definition.reference_thickness_mm ?? 1;
  }

  function readInputs() {
    const number = id => Number.parseFloat($(id).value);
    const values = {
      country: $("b-country").value, process: $("b-process").value, material: $("b-material").value,
      l: number("b-l"), w: number("b-w"), h: number("b-h"), t: number("b-t"),
      qty: Number($("b-qty").value), sets: Number($("b-sets").value), detail: $("b-detail").value,
    };
    const checks = [["b-l", values.l > 0, "Length must be greater than zero."], ["b-w", values.w > 0, "Width must be greater than zero."],
      ["b-h", values.h > 0, "Height must be greater than zero."], ["b-t", values.t > 0, "Thickness must be greater than zero."],
      ["b-qty", Number.isInteger(values.qty) && values.qty > 0, "Quantity must be a positive whole number."],
      ["b-sets", Number.isInteger(values.sets) && values.sets >= 1 && values.sets <= 30, "Use a whole number of tools from 1 to 30."]];
    for (const [id, ok, message] of checks) {
      $(id).setAttribute("aria-invalid", ok ? "false" : "true");
      if (!ok) {
        const error = new Error(message);
        error.field = id;
        throw error;
      }
    }
    return values;
  }

  /* China and India are costed in USD: convert their rates to the API's euros with the ECB rate. */
  function buildRequest(values, profile, rate) {
    const assumptions = Object.fromEntries(ASSUMPTION_KEYS.map(key => [key, profile[key]]));
    if (profile.currency === "USD") MONEY_KEYS.forEach(key => assumptions[key] /= rate.rate);
    const request = {
      process: values.process, parts_per_mold: values.sets, manufacturing_country: values.country,
      expected_cycles: values.qty, cycle_band: legacyBandFor(values.qty),
      workpiece_material: values.material, material_thickness_mm: values.t,
      tolerance_level: "standard", surface_finish: "standard", abrasive_material: false, corrosive_environment: false,
      truck_distance_km: 0, sea_distance_nm: 0, includes_cooling: false,
      part: {length_mm: values.l, width_mm: values.w, height_mm: values.h},
      assumptions,
    };
    if (rate) request.eur_to_usd = rate.rate;
    if (values.detail) request.part_material_detail = values.detail;
    if (workbookProcess(values.process)) {
      request.expected_quantity = values.qty;
      request.cycle_band = "up_to_10000"; // Deprecated field; the workbook uses the lifetime quantity.
      request.sizing_mode = "part_scaled";
    }
    return request;
  }

  function advancedLink(values) {
    const params = new URLSearchParams({
      country: values.country, process: values.process, material: values.material,
      l: values.l, w: values.w, h: values.h, t: values.t, qty: values.qty, sets: values.sets,
      tol: "standard", finish: "standard", truck: 0, sea: 0,
    });
    if (values.detail) params.set("detail", values.detail);
    return `advanced.html?${params}`;
  }

  function render(report, values) {
    const base = report.base;
    $("b-currency").textContent = shown.currency === "USD" ? "$" : "€";
    $("b-price").textContent = fmtMoneyAmount(base.total_price * shown.factor);
    $("b-currency-note").textContent = shown.currency === "USD"
      ? `Costed in US dollars. EUR benchmarks (tool steel, heat treatment) converted at the ${shown.source}: 1 EUR = ${shown.factor} USD, ${shown.date}.`
      : "Costed in euros.";
    $("b-range").textContent = `Likely range ${euros(base.total_price * RANGE_LOW)} – ${euros(base.total_price * RANGE_HIGH)}`
      + (base.estimate_complete === false ? ". Partial: a purchased assembly needs a supplier quote." : "");
    const life = report.tool_life;
    $("b-per-part").textContent = `${euros(report.tooling_per_part)} over ${values.qty.toLocaleString()} parts`
      + (life?.replacements ? `, incl. ${life.replacements} replacement set${life.replacements > 1 ? "s" : ""} (lifetime ${euros(life.lifetime_cost)})` : "");
    $("b-tool-material").textContent = base.recommended_material || base.tooling_material || "—";
    $("b-concept").textContent = base.tooling_concept || base.tooling_material || "—";
    const top = report.cost_drivers.slice(0, 4);
    const max = Math.max(...top.map(d => d.amount), 1);
    $("b-drivers").innerHTML = top.map(d => `
      <div class="bar-row">
        <div class="bar-label"><span>${escapeHtml(d.label)}</span><strong>${euros(d.amount)} · ${fmt(d.share * 100, 0)}%</strong></div>
        <div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${Math.max(1.5, d.amount / max * 100).toFixed(1)}%"></div></div>
      </div>`).join("");
    const matrix = report.matrix;
    $("b-matrix").hidden = !matrix?.covered;
    if (matrix?.covered) {
      $("b-matrix-route").textContent = `${matrix.route} · ${matrix.tooling}`;
      $("b-matrix-note").textContent = `Process matrix, ${matrix.material.toLowerCase()} (${matrix.form.toLowerCase()}), ${matrix.band} parts.`
        + (matrix.current_process_listed ? " This matches your process."
          : ` Your process is not the matrix route at this quantity${matrix.current_process_band ? `; it is used from ${matrix.current_process_band} parts` : ""}.`);
      $("b-matrix").dataset.match = matrix.current_process_listed ? "true" : "false";
    }
    $("b-advanced").href = advancedLink(values);
  }

  async function calculate() {
    clearTimeout(timer);
    const current = ++revision;
    active?.abort();
    const controller = new AbortController();
    active = controller;
    let values;
    try {
      values = readInputs();
    } catch (error) {
      setStatus(error.message, true);
      setState(calculated ? "Out of date" : "Not calculated", true);
      return;
    }
    $("b-submit").disabled = true;
    setStatus("Calculating…");
    setState("Updating…", true);
    try {
      const profile = await countryProfile(values.country);
      let rate = null;
      try {
        rate = await ecbRate();
      } catch {
        // EUR countries can still be priced; USD countries cannot.
        if (profile.currency === "USD") {
          throw new Error(`${profile.name} is costed in US dollars, and the exchange rate could not be loaded. Try again, or enter your own rate in the detailed analysis.`);
        }
      }
      const report = await fetchJson("/api/advanced-report", {
        method: "POST", signal: controller.signal, headers: {"Content-Type": "application/json"},
        body: JSON.stringify(buildRequest(values, profile, rate)),
      });
      if (current !== revision) return;
      shown = profile.currency === "USD"
        ? {currency: "USD", factor: rate.rate, date: rate.date, source: rate.source}
        : {currency: "EUR", factor: 1};
      render(report, values);
      calculated = true;
      setState("Up to date", false);
      setStatus("Price updated. Changes recalculate automatically.");
    } catch (error) {
      if (error.name === "AbortError" || current !== revision) return;
      setState(calculated ? "Out of date" : "Not calculated", true);
      setStatus(error.message || "Could not calculate the price.", true);
    } finally {
      if (current === revision) $("b-submit").disabled = false;
    }
  }

  function scheduleCalculation() {
    if (!calculated) return;
    setState("Out of date", true);
    clearTimeout(timer);
    timer = setTimeout(calculate, 500);
  }

  async function init() {
    try {
      setStatus("Loading countries and processes… The first load can take up to a minute while the server wakes up.");
      const [countries, tooling] = await Promise.all([fetchJson("/api/countries"), fetchJson("/api/tooling-catalog")]);
      try {
        await ProcessMatrix.load();
        ProcessMatrix.fill("b-detail");
      } catch {
        // The server still derives the matrix row from the part material.
      }
      catalog = tooling;
      fillSelect("b-country", countries.map(c => ({value: c.code, label: c.name})));
      $("b-country").value = "DE";
      const select = $("b-process");
      select.innerHTML = `<optgroup label="Detailed tooling processes">${catalog.processes.map(p => `<option value="${escapeHtml(p.code)}">${escapeHtml(p.label)}</option>`).join("")}</optgroup>
        <optgroup label="Broad-process estimates">${LISTS.processes.map(p => `<option value="${p.value}">${escapeHtml(p.label)}</option>`).join("")}</optgroup>`;
      select.value = "die_casting";
      $("b-qty").value = 10000;
      $("b-sets").value = 1;
      onProcessChange();
      setStatus("Ready. Enter your part and select Get price.");
      $("b-submit").disabled = false;
    } catch (error) {
      setStatus(`Could not load the estimator: ${error.message}`, true);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("basic-form").addEventListener("submit", event => {
      event.preventDefault();
      calculate();
    });
    $("b-detail").addEventListener("change", () => {
      if (ProcessMatrix.syncWorkpiece("b-detail", "b-material")) touched.add("b-material");
      scheduleCalculation();
    });
    $("b-process").addEventListener("change", () => {
      onProcessChange();
      scheduleCalculation();
    });
    for (const id of ["b-country", "b-material", "b-l", "b-w", "b-h", "b-t", "b-qty", "b-sets"]) {
      const element = $(id);
      element.addEventListener(element.tagName === "SELECT" ? "change" : "input", () => {
        touched.add(id);
        scheduleCalculation();
      });
    }
    init();
  });
})();
