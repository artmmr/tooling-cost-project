/* Shared by every page: API address, option lists, formatting and the theme switch. */
const API_BASE_URL =
  globalThis.TOOLING_API_BASE_URL || "https://tooling-cost-project.onrender.com";

const LISTS = {
  cycles: [
    {value: "up_to_10000", label: "Up to 10,000 cycles"},
    {value: "10000_to_100000", label: "10,000 to 100,000 cycles"},
    {value: "100000_to_250000", label: "100,000 to 250,000 cycles"},
  ],
  // Original broad-process estimates (the detailed workbook processes come from the API).
  processes: [
    {value: "plastic_molding", label: "Plastic Molding"},
    {value: "plastic_injection", label: "Plastic Injection"},
    {value: "foaming", label: "Foaming"},
    {value: "thermoforming", label: "Thermoforming"},
    {value: "metal_molding", label: "Metal Molding"},
    {value: "stamping", label: "Stamping"},
    {value: "forming", label: "Forming"},
    {value: "deep_drawing", label: "Deep Drawing"},
  ],
  partsPerMold: Array.from({length: 30}, (_, i) => i + 1),
  cooling: [
    {value: "false", label: "No"},
    {value: "true", label: "Yes"},
  ],
};

const PLASTIC_PROCESSES = new Set(["plastic_molding", "plastic_injection", "foaming", "thermoforming"]);
const METAL_PROCESSES = new Set(["metal_molding", "stamping", "forming", "deep_drawing"]);

const PLASTIC_MATERIALS = [
  {value: "standard_thermoplastic", label: "Standard thermoplastic"},
  {value: "glass_filled_thermoplastic", label: "Glass-filled thermoplastic"},
  {value: "mineral_filled_thermoplastic", label: "Mineral-filled thermoplastic"},
  {value: "corrosive_polymer", label: "Corrosive / aggressive polymer"},
  {value: "thermoset", label: "Thermoset"},
  {value: "elastomer", label: "Elastomer"},
  {value: "other", label: "Other"},
];

const METAL_MATERIALS = [
  {value: "mild_steel", label: "Mild steel"},
  {value: "high_strength_steel", label: "High-strength steel"},
  {value: "advanced_high_strength_steel", label: "Advanced high-strength steel (AHSS)"},
  {value: "stainless_steel", label: "Stainless steel"},
  {value: "aluminum_sheet", label: "Aluminum"},
  {value: "copper_brass", label: "Copper / brass"},
  {value: "other", label: "Other"},
];

const CYCLE_DEFAULTS = {up_to_10000: 5000, "10000_to_100000": 50000, "100000_to_250000": 150000};

const EUROPEAN_COUNTRIES = new Set(["DE", "FR", "AT", "CZ", "SK", "HU", "PL", "ES", "IT"]);

/* Part materials offered for each detailed (workbook) process, and the default choice. */
const WORKBOOK_PLASTIC = ["plastic_extrusion", "blow_molding", "compression_molding", "transfer_molding", "rotational_molding"];
const WORKBOOK_COMPOSITE = ["composite_molding", "pultrusion"];
const WORKBOOK_PREFERRED_MATERIAL = {
  die_casting: "cast_aluminum", metal_extrusion: "cast_aluminum", sand_casting: "cast_iron", investment_casting: "stainless_steel",
  plastic_extrusion: "corrosive_polymer", compression_molding: "thermoset", transfer_molding: "thermoset",
  powder_metallurgy: "metal_powder", metal_injection_molding: "metal_powder", composite_molding: "fiber_composite",
  pultrusion: "fiber_composite", spinning: "aluminum_sheet",
};

function workbookMaterials(code) {
  if (WORKBOOK_COMPOSITE.includes(code)) return [{value: "fiber_composite", label: "Fiber composite"}, ...PLASTIC_MATERIALS];
  if (WORKBOOK_PLASTIC.includes(code)) return PLASTIC_MATERIALS;
  return [
    ...METAL_MATERIALS,
    {value: "cast_aluminum", label: "Casting / extrusion aluminum"},
    {value: "cast_iron", label: "Cast iron"},
    {value: "metal_powder", label: "Metal powder / binder"},
  ];
}

function workbookPreferredMaterial(code) {
  return WORKBOOK_PREFERRED_MATERIAL[code] || (WORKBOOK_PLASTIC.includes(code) ? "standard_thermoplastic" : "mild_steel");
}

/* Material choices for any process code (detailed or broad). */
function materialsForProcess(code, isWorkbook) {
  if (isWorkbook) return {options: workbookMaterials(code), preferred: workbookPreferredMaterial(code)};
  return PLASTIC_PROCESSES.has(code)
    ? {options: PLASTIC_MATERIALS, preferred: "standard_thermoplastic"}
    : {options: METAL_MATERIALS, preferred: "mild_steel"};
}

function legacyBandFor(quantity) {
  if (quantity <= 10000) return "up_to_10000";
  if (quantity <= 100000) return "10000_to_100000";
  return "100000_to_250000";
}

/* =========================================================
   Formatting
   ========================================================= */

function fmt(number, decimals = 2) {
  if (typeof number !== "number" || Number.isNaN(number)) return "—";
  return number.toLocaleString(undefined, {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
}

/* Whole units for large amounts, cents for small ones such as cost per part. */
function fmtMoneyAmount(number) {
  if (typeof number !== "number" || !Number.isFinite(number)) return "—";
  return fmt(number, Math.abs(number) >= 100 ? 0 : Math.abs(number) >= 1 ? 2 : 3);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[char]);
}

function fillSelect(id, options) {
  document.getElementById(id).innerHTML = options
    .map(option => typeof option === "object"
      ? `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`
      : `<option value="${escapeHtml(option)}">${escapeHtml(option)}</option>`)
    .join("");
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // Keep the default message.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

/* =========================================================
   Theme
   ========================================================= */

const Theme = (() => {
  const KEY = "tooling-theme";
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  function stored() {
    try { return localStorage.getItem(KEY); } catch { return null; }
  }
  function effective() {
    return document.documentElement.dataset.theme || (media?.matches ? "dark" : "light");
  }
  function apply(theme) {
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      const dark = effective() === "dark";
      button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
      button.title = button.getAttribute("aria-label");
      button.dataset.current = dark ? "dark" : "light";
    });
  }
  function toggle() {
    const next = effective() === "dark" ? "light" : "dark";
    try { localStorage.setItem(KEY, next); } catch { /* Theme still applies for this visit. */ }
    apply(next);
  }
  apply(stored());
  media?.addEventListener?.("change", () => apply(stored()));
  document.addEventListener("DOMContentLoaded", () => {
    apply(stored());
    document.querySelectorAll("[data-theme-toggle]").forEach(button => button.addEventListener("click", toggle));
  });
  return {apply, toggle, effective};
})();

/* =========================================================
   Process matrix: material grade and form selector
   ========================================================= */

const ProcessMatrix = (() => {
  let request = null;
  let data = null;
  async function load() {
    request ||= fetchJson("/api/process-matrix").then(result => (data = result)).catch(error => {
      request = null;
      throw error;
    });
    return request;
  }
  /* Grouped options: "Automatic" first, then each matrix material and form. */
  function fill(selectId) {
    const select = document.getElementById(selectId);
    const groups = {};
    for (const row of data?.rows || []) {
      const group = row.workpiece_material && /thermoplastic|corrosive_polymer/.test(row.workpiece_material) ? "Thermoplastics"
        : ["elastomer", "thermoset"].includes(row.workpiece_material) ? "Elastomers and thermosets" : "Metals";
      (groups[group] ||= []).push(row);
    }
    select.innerHTML = `<option value="">Automatic (from part material)</option>` + Object.entries(groups).map(([label, rows]) =>
      `<optgroup label="${escapeHtml(label)}">${rows.map(r => `<option value="${escapeHtml(r.id)}">${escapeHtml(`${r.material} — ${r.form}`)}</option>`).join("")}</optgroup>`).join("");
  }
  /* The costing material that goes with a matrix row, when the current process offers it. */
  function syncWorkpiece(detailId, materialId) {
    const row = data?.rows.find(r => r.id === document.getElementById(detailId).value);
    const material = document.getElementById(materialId);
    if (row?.workpiece_material && [...material.options].some(o => o.value === row.workpiece_material)
        && material.value !== row.workpiece_material) {
      material.value = row.workpiece_material;
      return true;
    }
    return false;
  }
  return {load, fill, syncWorkpiece, rows: () => data?.rows || []};
})();
