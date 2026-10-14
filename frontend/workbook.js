/* Detailed workbook processes share the same EUR API contract as the legacy UI. */
const WorkbookUI = (() => {
  let catalog = null, materials = {}, overrides = {}, lastBlocks = [], editorKey = "";
  const sizingFields = [
    ["nominal_length_mm", "Working length / diameter", "mm"],
    ["nominal_width_mm", "Working width", "mm"],
    ["nominal_depth_mm", "Working depth / axial length", "mm"],
    ["enlargement_ratio", "Linear tool enlargement", "%"],
    ["side_reserve_x_mm", "Side / radial reserve X", "mm"],
    ["side_reserve_y_mm", "Side reserve Y", "mm"],
    ["backing_mm", "Backing / mounting reserve", "mm"],
    ["allowance_mm", "Stock allowance per face", "mm"],
    ["rounding_mm", "Purchasing increment", "mm"],
    ["machining_volume_m3", "Total removal volume per piece", "cm³"],
  ];
  const materialFields = [
    ["density_kg_m3", "Density", "kg/m³"], ["block_price_per_tonne", "Material price", "€/t"],
    ["removal_rate_cm3_min", "Removal rate", "cm³/min"], ["milling_volume_factor", "Volume per cutter", "m³"],
    ["milling_tool_price", "Cutter price", "€"], ["heat_treatment_eur_per_kg", "Heat treatment", "€/kg"],
  ];
  const routeFields = [
    ["cnc_3_axis_share", "CNC 3-axis", "%"], ["cnc_5_axis_share", "CNC 5-axis", "%"],
    ["edm_share", "Electro-Discharge Machining", "%"], ["grinding_share", "Grinding", "%"],
  ];
  const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
  const current = () => catalog?.processes.find(p => p.code === document.getElementById("inp-process").value);
  const isMoney = key => ["block_price_per_tonne", "milling_tool_price", "heat_treatment_eur_per_kg", "purchased_unit_cost_eur"].includes(key);
  function inputField(id, key, label, unit = "", group = "") {
    return `<div class="field"><label for="block-${id}-${key}">${escape(label)} <span class="unit">${escape(unit)}</span></label>
      <input id="block-${id}-${key}" data-component="${id}" data-key="${key}" data-group="${group}" type="number" min="0" step="1" /></div>`;
  }
  async function init() {
    const response = await fetch(`${API_BASE_URL}/api/tooling-catalog`);
    if (!response.ok) throw new Error("The full tooling catalog is unavailable. Deploy the updated backend before this frontend.");
    catalog = await response.json();
    const materialResponse = await fetch(`${API_BASE_URL}/api/tooling-materials`);
    if (!materialResponse.ok) throw new Error("Could not load component costing profiles.");
    materials = await materialResponse.json();
    const select = document.getElementById("inp-process");
    select.innerHTML = `<optgroup label="Detailed tooling processes">${catalog.processes.map(p => `<option value="${p.code}">${escape(p.label)}</option>`).join("")}</optgroup>
      <optgroup label="Original broad-process estimates">${LISTS.processes.map(p => `<option value="${p.value}">${escape(p.label)}</option>`).join("")}</optgroup>`;
    document.getElementById("sizing-glossary").innerHTML = catalog.glossary.map(row => `<dt>${escape(row[0])}</dt><dd>${escape(row[1])} ${escape(row[2])}</dd>`).join("");
    document.getElementById("sizing-steps").innerHTML = catalog.sizing_steps.map(row => `<li><strong>${escape(row[0])}</strong>: ${escape(row[1])}. ${escape(row[2])}</li>`).join("");
    document.getElementById("sizing-checklist").innerHTML = catalog.review_checklist.map(row => `<li><strong>${escape(row[0])}</strong>: ${escape(row[1])}. ${escape(row[2])}</li>`).join("");
    document.getElementById("sizing-example").innerHTML = catalog.worked_example.map(row => `<tr><th scope="row">${escape(row[0])}</th><td>${escape(row[1])} ${escape(row[2])}</td><td>${escape(row[3])}</td></tr>`).join("");
    document.getElementById("use-reference-part").addEventListener("click", () => { loadPart(); reset(); scheduleCalculation(); });
    document.getElementById("reset-blocks").addEventListener("click", () => { reset(); scheduleCalculation(); });
    document.getElementById("block-editors").addEventListener("input", handleEdit);
    document.getElementById("block-editors").addEventListener("change", event => {
      if (event.target.tagName === "SELECT") handleEdit(event);
    });
    document.getElementById("block-editors").addEventListener("click", event => {
      const id = event.target.dataset.resetComponent;
      if (id) { delete overrides[id]; scheduleCalculation(); }
    });
    document.getElementById("inp-expected-cycles").addEventListener("input", syncBand);
    document.getElementById("inp-sizing-mode").addEventListener("change", () => {
      if (document.getElementById("inp-sizing-mode").value === "reference") loadPart();
      updateMode();
      reset();
    });
  }
  function reset() {
    overrides = {};
    editorKey = "";
    lastBlocks = [];
    document.getElementById("block-editors").replaceChildren();
    document.getElementById("block-modified").textContent = "Workbook defaults";
  }
  function loadPart() {
    const p = current();
    if (!p) return;
    ["length_mm", "width_mm", "height_mm"].forEach((key, i) => document.getElementById(["inp-l", "inp-w", "inp-h"][i]).value = p.reference_part[key]);
    document.getElementById("inp-material-thickness").value = p.reference_thickness_mm ?? 1;
  }
  function updateMode() {
    const reference = current() && document.getElementById("inp-sizing-mode").value === "reference";
    ["inp-l", "inp-w", "inp-h", "inp-material-thickness"].forEach(id => document.getElementById(id).disabled = Boolean(reference));
  }
  function onProcessChange() {
    reset();
    const p = current();
    document.getElementById("workbook-inputs").hidden = !p;
    document.getElementById("workbook-results").hidden = !p;
    document.getElementById("legacy-tooling-assumptions").hidden = Boolean(p);
    document.getElementById("quantity-label").textContent = p ? "Lifetime quantity (parts)" : "Expected production cycles";
    document.getElementById("sets-label").textContent = p ? "Identical working-tool sets" : "Parts per mold / tool";
    document.getElementById("quantity-band-label").textContent = p ? "Lifetime quantity band" : "Tool life band";
    document.getElementById("part-shape-note").textContent = p ? `${p.part_description}. Example part material: ${p.workpiece_grade}.` : "";
    document.getElementById("reference-scope").textContent = p?.scope || "";
    if (p) {
      fillSelect("inp-cycles", catalog.quantity_bands.map((b, i) => ({value: `q${i + 1}`, label: b.band})));
      loadPart();
      document.getElementById("inp-pqty").value = "1";
      document.getElementById("inp-sizing-mode").value = "part_scaled";
      const plastic = ["plastic_extrusion", "blow_molding", "compression_molding", "transfer_molding", "rotational_molding"];
      const composite = ["composite_molding", "pultrusion"];
      const options = composite.includes(p.code) ? [{value:"fiber_composite", label:"Fiber composite"}, ...PLASTIC_MATERIALS] : plastic.includes(p.code) ? PLASTIC_MATERIALS : [
        ...METAL_MATERIALS, {value:"cast_aluminum", label:"Casting / extrusion aluminum"},
        {value:"cast_iron", label:"Cast iron"}, {value:"metal_powder", label:"Metal powder / binder"},
      ];
      fillSelect("inp-workpiece-material", options);
      const preferred = {die_casting:"cast_aluminum", metal_extrusion:"cast_aluminum", sand_casting:"cast_iron", investment_casting:"stainless_steel",
        plastic_extrusion:"corrosive_polymer", compression_molding:"thermoset", transfer_molding:"thermoset",
        powder_metallurgy:"metal_powder", metal_injection_molding:"metal_powder", composite_molding:"fiber_composite", pultrusion:"fiber_composite", spinning:"aluminum_sheet"};
      document.getElementById("inp-workpiece-material").value = preferred[p.code] || (plastic.includes(p.code) ? "standard_thermoplastic" : "mild_steel");
      syncBand();
    } else {
      fillSelect("inp-cycles", LISTS.cycles);
      document.getElementById("inp-cycles").value = "up_to_10000";
    }
    document.getElementById("material-thickness-field").classList.toggle("field-muted", false);
    updateMode();
  }
  function syncBand() {
    if (!current()) return;
    const quantity = Number(document.getElementById("inp-expected-cycles").value);
    const index = catalog.quantity_bands.findIndex(b => quantity >= b.quantity_min && (b.quantity_max === null || quantity <= b.quantity_max));
    document.getElementById("inp-cycles").value = index < 0 ? "" : `q${index + 1}`;
  }
  function chooseBand() {
    if (!current()) return false;
    const index = Number(document.getElementById("inp-cycles").value.slice(1)) - 1;
    document.getElementById("inp-expected-cycles").value = catalog.quantity_bands[index].quantity_min;
    return true;
  }
  function addState(state) {
    if (!current()) return;
    state.expected_quantity = Number(document.getElementById("inp-expected-cycles").value);
    state.cycle_band = "up_to_10000"; // Deprecated compatibility field, not the V4 selector.
    state.sizing_mode = document.getElementById("inp-sizing-mode").value;
    state.block_overrides = Object.entries(overrides).map(([id, value]) => ({component_id:id, ...value}));
    delete state.tooling_material_assumptions;
    delete state.manufacturing_route;
    delete state.tooling_material_family;
    for (const component of Object.values(overrides)) {
      for (const value of Object.values(component)) {
        const values = typeof value === "object" ? Object.values(value) : [value];
        if (values.some(v => typeof v === "number" && !Number.isFinite(v))) throw new Error("Complete or clear the invalid component input before calculating.");
      }
    }
  }
  function handleEdit(event) {
    const field = event.target;
    const {component: id, key, group} = field.dataset;
    if (!id || (event.type === "input" && field.tagName === "SELECT")) return;
    const change = overrides[id] ||= {};
    if (key === "material_family") {
      change[key] = field.value;
      delete change.tooling_material_assumptions;
      delete change.manufacturing_route;
    } else if (key === "stock_form") {
      change[key] = field.value;
    } else {
      let value = field.value === "" ? undefined : Number(field.value);
      if (value !== undefined) {
        if (isMoney(key)) value /= currencyFactor() || NaN;
        if (key === "enlargement_ratio" || group === "manufacturing_route") value /= 100;
        if (key === "machining_volume_m3") value /= 1e6;
      }
      if (group) {
        const block = lastBlocks.find(b => b.component_id === id);
        const base = materials[change.material_family || block.material_family];
        const defaults = group === "manufacturing_route" ? base.route : Object.fromEntries(materialFields.map(([k]) => [k,base[k]]));
        change[group] ||= {...defaults};
        change[group][key] = value === undefined ? defaults[key] : value;
      } else if (value === undefined) delete change[key];
      else change[key] = value;
    }
    const route = change.manufacturing_route;
    const routeLabel = document.getElementById(`block-route-${id}`);
    if (route && routeLabel) routeLabel.textContent = `Route total: ${fmt(Object.values(route).reduce((a,b) => a+b,0)*100, 0)}%`;
    document.getElementById("block-modified").textContent = "Component inputs modified";
    scheduleCalculation();
  }
  function editor(block) {
    const id = block.component_id;
    const top = `<details class="component-editor"><summary>${escape(block.component)} <span id="block-state-${id}" class="summary-meta"></span></summary><div class="details-body">
      <p class="field-help">${escape(block.assumption)}</p><div class="form-grid two-col">${inputField(id,"pieces","Pieces per set")}`;
    if (block.purchased) return top + inputField(id,"purchased_unit_cost_eur","Supplier unit quote","€") + inputField(id,"purchased_unit_weight_kg","Shipping weight per unit","kg") + `</div><p class="field-help">A rated purchased assembly has no inferred milling stock. Unquoted cost and weight remain excluded.</p><button type="button" class="secondary-btn" data-reset-component="${id}">Restore this component</button></div></details>`;
    return top + `<div class="field"><label for="block-${id}-stock_form">Stock form</label><select id="block-${id}-stock_form" data-component="${id}" data-key="stock_form"><option>Rectangular block</option><option>Round billet</option></select></div>`
      + sizingFields.map(([key,label,unit]) => inputField(id,key,label,unit)).join("")
      + `</div><p id="block-machining-${id}" class="field-help"></p><div class="field"><label for="block-${id}-material_family">Costing material family (benchmark)</label><select id="block-${id}-material_family" data-component="${id}" data-key="material_family">${Object.entries(materials).map(([key,p]) => `<option value="${key}">${escape(p.name)}</option>`).join("")}</select></div>
      <div class="form-grid two-col">${materialFields.map(([key,label,unit]) => inputField(id,key,label,unit,"tooling_material_assumptions")).join("")}</div>
      <h4>Tooling manufacturing route</h4><div class="form-grid two-col">${routeFields.map(([key,label,unit]) => inputField(id,key,label,unit,"manufacturing_route")).join("")}</div>
      <p id="block-route-${id}" class="field-help"></p><button type="button" class="secondary-btn" data-reset-component="${id}">Restore this component</button></div></details>`;
  }
  function render(result) {
    document.getElementById("price-heading").textContent = result.calculation_basis === "workbook_v4" ? "Working-tool estimate" : "Tooling price";
    document.getElementById("estimate-scope").textContent = result.estimate_complete === false ? "Partial subtotal: a required assembly is missing price or shipping weight." : "";
    if (result.calculation_basis !== "workbook_v4") return;
    document.getElementById("block-counts").textContent = `${result.total_machined_blocks} machined blocks; ${result.total_purchased_assemblies} purchased assemblies. Maximum individual stock dimensions are not an assembled tool envelope.`;
    document.getElementById("grade-summary").textContent = `Grade candidates: ${result.grade_candidates}. Treatment: ${result.grade_treatment}. Scope: ${result.grade_scope}. ${result.selection_conditions}`;
    document.getElementById("cost-model-note").textContent = result.cost_model_note;
    renderList("estimate-warnings", result.estimate_warnings, "No additional warnings.");
    const key = current().code + result.tooling_blocks.map(b => b.component_id).join();
    if (key !== editorKey) {
      document.getElementById("block-editors").innerHTML = result.tooling_blocks.map(editor).join("");
      editorKey = key;
    }
    lastBlocks = result.tooling_blocks;
    refresh();
  }
  function refresh() {
    for (const block of lastBlocks) {
      const id = block.component_id;
      const change = overrides[id] || {};
      const chosenProfile = change.material_family ? materials[change.material_family] : null;
      const values = {pieces:block.pieces_per_set, stock_form:block.stock_form, material_family:block.material_family,
        ...block.sizing_inputs, ...block.material_assumptions, ...block.manufacturing_route,
        machining_volume_m3:block.machining_volume_m3 / block.pieces,
        purchased_unit_cost_eur:block.purchased_unit_cost_eur, purchased_unit_weight_kg:block.purchased_unit_weight_kg,
        ...(chosenProfile ? Object.fromEntries(materialFields.map(([k]) => [k,chosenProfile[k]])) : {}),
        ...(chosenProfile?.route || {}), ...change, ...change.tooling_material_assumptions, ...change.manufacturing_route};
      for (const [key, raw] of Object.entries(values)) {
        const field = document.getElementById(`block-${id}-${key}`);
        if (!field) continue;
        let value = raw;
        if (isMoney(key)) {
          field.disabled = !currencyFactor();
          if (value !== null) value = currencyFactor() ? value * currencyFactor() : null;
        }
        if (key === "enlargement_ratio" || key.endsWith("_share")) value *= 100;
        if (key === "machining_volume_m3") value *= 1e6;
        if (document.activeElement !== field) field.value = value == null ? "" : typeof value === "number" ? Number(value.toPrecision(12)) : value;
      }
      const modified = overrides[id] && Object.keys(overrides[id]).length > 0;
      document.getElementById(`block-state-${id}`).textContent = modified ? "Modified" : "Defaults";
      if (!block.purchased) {
        document.getElementById(`block-machining-${id}`).textContent = block.machining_basis;
        const route = change.manufacturing_route || chosenProfile?.route || block.manufacturing_route;
        document.getElementById(`block-route-${id}`).textContent = `Route total: ${fmt(Object.values(route).reduce((a,b) => a+b,0)*100,0)}%`;
        for (const key of ["nominal_width_mm", "side_reserve_y_mm"]) document.getElementById(`block-${id}-${key}`).disabled = block.stock_form === "Round billet";
      }
    }
    document.getElementById("block-editors").querySelectorAll(".unit").forEach(label => {
      if (!label.dataset.eurLabel && label.textContent.includes("€")) label.dataset.eurLabel = label.textContent;
      if (label.dataset.eurLabel) label.textContent = label.dataset.eurLabel.replace("€", displayCurrency);
    });
    document.getElementById("block-modified").textContent = Object.values(overrides).some(o => Object.keys(o).length) ? "Component inputs modified" : "Workbook defaults";
  }
  return {init, current, onProcessChange, chooseBand, addState, render, refresh, escape};
})();
