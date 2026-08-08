/**
 * Tooling cost model — ported from Excel workbook logic (Overview + Useful Data + Transport).
 * Constants match the extracted .xlsx values.
 */

const LISTS = {
  cycles: ["1- 0 to 10000", "2 - 10000 to 100000", "3 - 100000 to 250000"],
  processes: [
    "1 - Plastic Molding",
    "1 - Plastic Injection",
    "1 - Foaming",
    "1 -Thermoforming",
    "2 - Metal Molding",
    "2 - Stamping",
    "2 - Forming",
    "2 - Deep Drawing",
  ],
  toolingMaterial: ["1 - Aluminum", "2 - Steel", "3 - Hard Steel"],
  productionQtyIndex: Array.from({ length: 30 }, (_, i) => i + 1),
  cooling: ["Yes", "No"],
};

/** Useful Data sheet equivalents */
const UD = {
  H: [, , , , 42.672, 10.6934, 3.7338, 2.333625, 1.8669], // row index 1-based: H4..H8
  I: [, , , , 2710, 8960, 7850, 8000, 7900],
  P: [, , , , 2700, 9500, 800, 1300, 1400],
  O: [, , , , , , , , , , , , , , 0.010125, 0.0025372767857142855, 0.0008859374999999999, 0.0005537109375, 0.00044296875],
  Pmach: [, , , , , , , , , , , , , , 40, 50, 60, 75, 80],
  machineHr: 150,
  operatorHr: 40,
};

const LISTS_D2 = "1 - Aluminum";
const LISTS_D3 = "2 - Steel";
const LISTS_D4 = "3 - Hard Steel";

/** Transport! sheet — E2/F2 road, E6/F6 sea (matches workbook formulas) */
const TRANSPORT = {
  roadE2: (1400 / 250) * 100,
  roadF2: 18000,
  seaE6: (8000 / (11000 * 1.8)) * 1000,
  seaF6: 27000,
};

function firstDigit(str) {
  const m = String(str).match(/\d/);
  return m ? parseInt(m[0], 10) : NaN;
}

function toolingMaterialFromInputs(cyclesStr, processStr) {
  const c9 = firstDigit(cyclesStr);
  const c10 = firstDigit(processStr);
  // IFS matrix from Overview!C12
  if (c9 === 1 && c10 === 1) return LISTS_D2;
  if (c9 === 1 && c10 === 2) return LISTS_D2;
  if (c9 === 1 && c10 === 3) return LISTS_D3;
  if (c9 === 2 && c10 === 1) return LISTS_D2;
  if (c9 === 2 && c10 === 2) return LISTS_D2;
  if (c9 === 2 && c10 === 3) return LISTS_D4;
  if (c9 === 3 && c10 === 1) return LISTS_D3;
  if (c9 === 3 && c10 === 2) return LISTS_D4;
  if (c9 === 3 && c10 === 3) return LISTS_D4;
  return LISTS_D2;
}

/** Excel ROUNDUP(..., 0) — smallest integer ≥ x (workbook evaluates C17 as integer, e.g. 2) */
function roundUpInt(n) {
  return Math.ceil(n - 1e-12);
}

function ifsMaterial(c12, aluminum, steel, hard) {
  if (c12 === LISTS_D4) return hard;
  if (c12 === LISTS_D3) return steel;
  return aluminum;
}

function compute(state) {
  const c2 = state.cycles;
  const c3 = state.process;
  const c5 = state.productionQtyIndex;
  const c6 = state.truckKm;
  const c7 = state.seaKm;
  const c8 = state.cooling;
  const e4 = state.partL;
  const f4 = state.partW;
  const g4 = state.partH;

  const c9 = firstDigit(c2);
  const c10 = firstDigit(c3);
  const c12 = toolingMaterialFromInputs(c2, c3);
  const c11 = firstDigit(c12);

  const e13 = e4 * c5 + 150 * 2;
  const f13 = f4 + 150 * 2;
  const g13 = (g4 / 2) * 3 * 2;

  const c14 =
    c11 === 1
      ? e13 * f13 * g13 * 1e-9 * UD.I[4]
      : c11 === 2
        ? e13 * f13 * g13 * 1e-9 * UD.I[6]
        : e13 * f13 * g13 * 1e-9 * UD.I[8];

  const c15 =
    ((e13 + 5) * (f13 + 5) * (g13 + 5) - e13 * f13 * g13) / 1e9;
  const c16 = ((e4 * f4 * g4) / 1e9) * c5;

  const volPart = c16 + c15;
  const c17 = roundUpInt(
    ifsMaterial(
      c12,
      volPart / UD.O[14],
      volPart / UD.O[17],
      volPart / UD.O[18],
    ),
  );

  const hRow = c11 === 1 ? 4 : c11 === 2 ? 6 : 8;
  const hr = (UD.machineHr + UD.operatorHr) / 60;
  const c18 =
    (c16 * 1e6 / UD.H[hRow]) * c5 +
    c15 * 1e6 / UD.H[hRow];

  const pRow = c11 === 1 ? 4 : c11 === 2 ? 6 : 8;
  const c19 = c14 * (UD.P[pRow] / 1000) * 2 * 1.4;

  const c20 = c19 * 1.5 - c19;

  const c21 = (c15 * 1e6 / UD.H[hRow]) * hr * 1.25;

  const c22 = (c16 * 1e6 / UD.H[hRow]) * hr * 1.25 * c5;

  const c23 = ifsMaterial(
    c12,
    c17 * UD.Pmach[14],
    c17 * UD.Pmach[16],
    c17 * UD.Pmach[18],
  );

  let c24 = 0;
  if (c8 === "Yes") {
    if (c14 > 0 && c14 < 5000) c24 = 5000;
    else if (c14 > 500 && c14 < 1000) c24 = 7500;
    else if (c14 > 1000 && c14 < 2000) c24 = 10000;
    else if (c14 > 2000 && c14 < 3000) c24 = 15000;
    else if (c14 > 3000 && c14 < 50000) c24 = 20000;
  } else if (c8 === "No") {
    c24 = 0;
  }

  const sumPart =
    c19 + c22 + c24 + c20 + c21 + c23;
  const c25 = (sumPart * 1.2 - sumPart);
  const c26 = (c19 + c20 + c21 + c22 + c23 + c24) * 1.05 - (c19 + c20 + c21 + c22 + c23 + c24);

  const c27 =
    (c6 / 100) * TRANSPORT.roadE2 * (c14 / TRANSPORT.roadF2) * 2 +
    (c7 / 1000) * TRANSPORT.seaE6 * (c14 / TRANSPORT.seaF6) * 2;

  const c28 =
    (c19 + c20 + c21 + c22 + c23 + c24 + c25 + c26 + c27) * 1.1;

  return {
    c9,
    c10,
    c11,
    c12,
    e13,
    f13,
    g13,
    c14,
    c15,
    c16,
    c17,
    c18,
    c19,
    c20,
    c21,
    c22,
    c23,
    c24,
    c25,
    c26,
    c27,
    c28,
  };
}

function fmt(n, decimals = 2) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function readState() {
  return {
    cycles: document.getElementById("inp-cycles").value,
    process: document.getElementById("inp-process").value,
    productionQtyIndex: parseInt(document.getElementById("inp-pqty").value, 10),
    truckKm: parseFloat(document.getElementById("inp-truck").value),
    seaKm: parseFloat(document.getElementById("inp-sea").value),
    cooling: document.getElementById("inp-cooling").value,
    partL: parseFloat(document.getElementById("inp-l").value),
    partW: parseFloat(document.getElementById("inp-w").value),
    partH: parseFloat(document.getElementById("inp-h").value),
  };
}

function render() {
  const s = readState();
  const r = compute(s);

  document.getElementById("out-c12").textContent = r.c12;
  document.getElementById("out-c13").textContent = `${fmt(r.e13, 0)} × ${fmt(r.f13, 0)} × ${fmt(r.g13, 0)} mm`;

  const rows = [
    ["Tooling weight [kg]", r.c14],
    ["Tooling machining volume outside [m³]", r.c15],
    ["Tooling machining volume inside [m³]", r.c16],
    ["Milling time index (rounded)", r.c17],
    ["Volume removed / tool lifetime [min]", r.c18],
    ["Tooling material cost", r.c19],
    ["Tooling sales incl. margin", r.c20],
    ["Raw material transformation cost", r.c21],
    ["Tooling machining cost inside", r.c22],
    ["Tooling handling cost", r.c23],
    ["Cooling system cost", r.c24],
    ["Subtotal margin line", r.c25],
    ["Additional margin line", r.c26],
    ["Transport & packaging", r.c27],
  ];

  const tbody = document.querySelector("#out-main tbody");
  tbody.innerHTML = rows
    .map(
      ([label, val]) =>
        `<tr><th>${label}</th><td class="num">${fmt(val)}</td></tr>`,
    )
    .join("");

  document.getElementById("out-total").textContent = fmt(r.c28);
}

function fillSelect(id, options) {
  const el = document.getElementById(id);
  el.innerHTML = options.map((o) => `<option>${o}</option>`).join("");
}

function init() {
  fillSelect("inp-cycles", LISTS.cycles);
  fillSelect("inp-process", LISTS.processes);
  fillSelect(
    "inp-pqty",
    LISTS.productionQtyIndex.map(String),
  );
  fillSelect("inp-cooling", LISTS.cooling);

  // Defaults aligned with sample rows in the workbook
  document.getElementById("inp-cycles").value = "2 - 10000 to 100000";
  document.getElementById("inp-process").value = "2 - Stamping";
  document.getElementById("inp-pqty").value = "2";
  document.getElementById("inp-truck").value = "1700";
  document.getElementById("inp-sea").value = "19800";
  document.getElementById("inp-cooling").value = "No";
  document.getElementById("inp-l").value = "300";
  document.getElementById("inp-w").value = "300";
  document.getElementById("inp-h").value = "40";

  [
    "inp-cycles",
    "inp-process",
    "inp-pqty",
    "inp-truck",
    "inp-sea",
    "inp-cooling",
    "inp-l",
    "inp-w",
    "inp-h",
  ].forEach((id) => {
    document.getElementById(id).addEventListener("input", render);
    document.getElementById(id).addEventListener("change", render);
  });

  document.querySelectorAll("nav.tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll("nav.tabs button").forEach((b) => {
        b.setAttribute("aria-selected", b.dataset.tab === tab);
      });
      document.querySelectorAll(".panel").forEach((p) => {
        p.classList.toggle("active", p.id === `panel-${tab}`);
      });
    });
  });

  render();
}

document.addEventListener("DOMContentLoaded", init);
