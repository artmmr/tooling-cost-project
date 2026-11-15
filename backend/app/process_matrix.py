"""Industrialisation Process & Tooling Matrix (TCE workbook).

For each part material and form, the matrix names the production route and the
tooling grade for six lifetime-quantity bands. This module:

* reads the versioned JSON produced by ``scripts/import_process_matrix.py``;
* maps a request to a matrix row (chosen explicitly, or derived from the part
  material and process);
* translates each route into calculator process codes so alternatives can be
  priced, and each tooling note into the matrix's tool grades and the app's
  tooling-material cost families.

The translation tables below are the only interpretation layer; the matrix text
itself is shown to the user unchanged.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------
# Data
# ---------------------------------------------------------


@lru_cache(maxsize=1)
def matrix() -> dict:
    path = Path(__file__).with_name("data") / "process_matrix.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["schema_version"] != 1 or len(data["bands"]) != 6 or not data["rows"]:
        raise RuntimeError("Process matrix data is missing or incompatible. Deploy app/data/process_matrix.json.")
    return data


def row(row_id: str) -> dict | None:
    return next((r for r in matrix()["rows"] if r["id"] == row_id), None)


def band_index(quantity: int) -> int:
    for i, band in enumerate(matrix()["bands"]):
        if quantity >= band["quantity_min"] and (band["quantity_max"] is None or quantity <= band["quantity_max"]):
            return i
    return 0


# ---------------------------------------------------------
# Part material <-> matrix row
# ---------------------------------------------------------

# Costing material used by the calculator when a matrix row is chosen.
ROW_WORKPIECE = {
    "carbon_steel_sheet_metal": "mild_steel", "carbon_steel_solid": "mild_steel",
    "stainless_steel_sheet_metal": "stainless_steel", "stainless_steel_solid": "stainless_steel",
    "aluminium_complex_part": "cast_aluminum", "aluminium_profile": "cast_aluminum",
    "magnesium_complex_part": "cast_aluminum", "zinc_die_casting": "cast_aluminum",
    "copper_sheet_metal": "copper_brass", "copper_solid": "copper_brass", "brass_sheet_solid": "copper_brass",
    "silver_part_jewelry_contact": "copper_brass", "gold_part_jewelry_contact": "copper_brass",
    "titanium_solid": "other",
    "pp_pe_thermoplastic": "standard_thermoplastic", "abs_thermoplastic": "standard_thermoplastic",
    "pa_nylon_thermoplastic": "standard_thermoplastic", "pom_thermoplastic": "standard_thermoplastic",
    "pc_thermoplastic": "standard_thermoplastic", "pvc_corrosive_thermoplastic": "corrosive_polymer",
    "epdm_elastomer": "elastomer", "silicone_lsr_elastomer": "elastomer", "pu_epoxy_resin_thermoset": "thermoset",
}

SHEET_PROCESSES = {"bending", "punching_blanking", "fine_blanking", "progressive_die_stamping", "tube_hydroforming",
                   "sheet_hydroforming", "spinning", "stamping", "forming", "deep_drawing"}


def auto_row_id(workpiece_material: str, process: str) -> str | None:
    """Best matrix row for an app part material, or None when the matrix does not cover it."""
    sheet = process in SHEET_PROCESSES
    if workpiece_material in {"mild_steel", "high_strength_steel", "advanced_high_strength_steel"}:
        return "carbon_steel_sheet_metal" if sheet else "carbon_steel_solid"
    if workpiece_material == "stainless_steel":
        return "stainless_steel_sheet_metal" if sheet else "stainless_steel_solid"
    if workpiece_material == "cast_aluminum":
        return "aluminium_profile" if process == "metal_extrusion" else "aluminium_complex_part"
    if workpiece_material == "copper_brass":
        # The matrix covers brass sheet and solid (stamping, forging), not brass castings.
        return "brass_sheet_solid" if sheet or process == "closed_die_forging" else None
    return {
        "standard_thermoplastic": "pp_pe_thermoplastic",
        "glass_filled_thermoplastic": "pa_nylon_thermoplastic",
        "mineral_filled_thermoplastic": "pa_nylon_thermoplastic",
        "corrosive_polymer": "pvc_corrosive_thermoplastic",
        "elastomer": "epdm_elastomer",
        "thermoset": "pu_epoxy_resin_thermoset",
        "fiber_composite": "pu_epoxy_resin_thermoset",
    }.get(workpiece_material)


# ---------------------------------------------------------
# Route text -> calculator processes
# ---------------------------------------------------------

PLASTIC_ROWS = {"pp_pe_thermoplastic", "abs_thermoplastic", "pa_nylon_thermoplastic", "pom_thermoplastic",
                "pc_thermoplastic", "pvc_corrosive_thermoplastic"}
SOFT_MOLD_ROWS = {"epdm_elastomer", "silicone_lsr_elastomer", "pu_epoxy_resin_thermoset"}
DIE_CAST_ROWS = {"magnesium_complex_part", "zinc_die_casting"}
INVESTMENT_ROWS = {"carbon_steel_solid", "stainless_steel_solid", "silver_part_jewelry_contact", "gold_part_jewelry_contact"}

# Segments that are machining, cutting or additive routes: no dedicated forming tool (fixtures at most).
MACHINING = re.compile(r"^(cnc|laser( cutting)?|cutting|(metal )?3d( printing| prototype)?|fdm|mjf|sls|lost wax)$")
# Ordered: the first matching pattern wins for each route segment.
ROUTE_PATTERNS = [
    (r"progressive stamping", "progressive_die_stamping"),
    (r"\bstamping\b", "punching_blanking"),
    (r"bending", "bending"),
    (r"soft tool", "punching_blanking"),
    (r"\bforg", "closed_die_forging"),
    (r"hpdc|die casting", "die_casting"),
    (r"investment casting", "investment_casting"),
    (r"\brtm\b", "composite_molding"),
    (r"compression", "compression_molding"),
    (r"\blsr\b|injection", "plastic_injection"),
]
NO_TOOLING = re.compile(r"\bno (hard tooling|dedicated tooling|tooling|mold)\b", re.I)
GRAVITY = "Gravity / low-pressure casting (permanent mold)"


def _segment(row_id: str, segment: str) -> tuple[str, str | None]:
    """Classify one route segment: ("machining", None), ("process", code), ("unpriced", label) or ("unknown", None)."""
    if MACHINING.match(segment):
        return "machining", None
    if "extrusion" in segment:
        return "process", "plastic_extrusion" if row_id in PLASTIC_ROWS else "metal_extrusion"
    if "gravity casting" in segment or "low-pressure casting" in segment:
        return "unpriced", GRAVITY
    if "prototype casting" in segment:
        return "unpriced", "Prototype casting in a soft mold"
    if re.search(r"3d mold", segment) or (segment == "casting" and row_id in SOFT_MOLD_ROWS):
        return "unpriced", "Casting in a 3D-printed or resin mold"
    if segment == "casting":
        if row_id in DIE_CAST_ROWS:
            return "process", "die_casting"
        if row_id in INVESTMENT_ROWS:
            return "process", "investment_casting"
        return "unpriced", "Casting"
    for pattern, code in ROUTE_PATTERNS:
        if re.search(pattern, segment):
            return "process", code
    if re.search(r"(prototype|soft) mold", segment):
        if row_id in PLASTIC_ROWS:
            return "process", "plastic_injection"
        if row_id in SOFT_MOLD_ROWS:
            return "process", "compression_molding"
        return "unpriced", "Prototype casting mold"
    return "unknown", None


def route_processes(row_id: str, route: str, tooling: str, previous: list[str] | None = None) -> dict:
    """Interpret one matrix cell.

    Returns ``codes`` (calculator processes that can be priced), ``unpriced`` (named
    routes the calculator has no model for), ``no_tooling`` (the route needs no
    dedicated forming tool: machining, cutting or 3D printing, with fixtures at most)
    and ``unknown`` (segments the rules do not recognise).
    """
    codes: list[str] = []
    unpriced: list[str] = []
    unknown: list[str] = []
    machining = 0
    text = route.lower()
    if text.startswith("high volume") and previous:
        codes = list(previous)
        text = ""
    segments = [part.strip() for part in re.split(r"\s*/\s*|\s*\+\s*|\s+or\s+", text) if part.strip()]
    for segment in segments:
        kind, value = _segment(row_id, segment)
        if kind == "process":
            codes.append(value)
        elif kind == "unpriced":
            unpriced.append(value)
        elif kind == "machining":
            machining += 1
        else:
            unknown.append(segment)
    no_tooling = bool(NO_TOOLING.search(tooling)) or (bool(segments) and machining == len(segments))
    if no_tooling:
        codes, unpriced = [], []
    return {"codes": list(dict.fromkeys(codes)), "unpriced": list(dict.fromkeys(unpriced)),
            "no_tooling": no_tooling, "unknown": unknown}


# ---------------------------------------------------------
# Tooling text -> tool grades and cost families
# ---------------------------------------------------------

GRADE_FAMILY = {
    "Tooling resin": None,
    "Aluminium 7075": "aluminum_tooling",
    "C45 / mild steel": "pre_hardened_mold_steel",  # cost proxy: no unhardened carbon-steel profile exists
    "P20 / 1.2311": "pre_hardened_mold_steel",
    "1.2738 / P20 + Ni": "pre_hardened_mold_steel",
    "1.2083 / 420": "corrosion_resistant_mold_steel",
    "1.2083 ESR": "corrosion_resistant_mold_steel",
    "H11 / 1.2343": "hardened_mold_steel",
    "H13 / 1.2344": "hardened_mold_steel",
    "Premium H13 / ESR": "hardened_mold_steel",
    "D2 / 1.2379": "cold_work_tool_steel",
    "PM Tool Steel": "high_wear_cold_work_steel",
    "WC-Co Carbide": "carbide",
}


def tooling_grades(tooling: str) -> list[str]:
    """Matrix tool grades named in a tooling note, in the order they appear."""
    text = tooling
    found: list[tuple[int, str]] = []

    def hit(pattern, grade):
        match = re.search(pattern, text, re.I)
        if match:
            found.append((match.start(), grade))
        return bool(match)

    if re.search(r"1\.2083", text) and "ESR" in text:
        hit(r"1\.2083", "1.2083 ESR")
    else:
        hit(r"1\.2083|\b420\b|stainless mold steel", "1.2083 / 420")
    if not hit(r"premium H13|H13 / ESR", "Premium H13 / ESR"):
        hit(r"H13|1\.2344", "H13 / 1.2344")
    hit(r"H11|1\.2343", "H11 / 1.2343")
    hit(r"\bD2\b|1\.2379", "D2 / 1.2379")
    hit(r"\bPM\b", "PM Tool Steel")
    hit(r"carbide", "WC-Co Carbide")
    hit(r"1\.2738", "1.2738 / P20 + Ni")
    hit(r"\bP20\b|1\.2311", "P20 / 1.2311")
    hit(r"C45|mild-steel|mild steel|steel fixtures", "C45 / mild steel")
    hit(r"7075|\bAl\b|Al mold", "Aluminium 7075")
    hit(r"resin", "Tooling resin")
    if re.search(r"\bmold steel\b", text) and not any(g in ("P20 / 1.2311", "1.2083 / 420", "1.2083 ESR") for _, g in found):
        found.append((text.lower().index("mold steel"), "P20 / 1.2311"))
    return [grade for _, grade in sorted(dict((g, (p, g)) for p, g in found).values())]


def grade_details(name: str) -> dict | None:
    return next((g for g in matrix()["grades"] if g["name"] == name), None)


# ---------------------------------------------------------
# Advice for one request
# ---------------------------------------------------------

class MatrixGrade(BaseModel):
    name: str
    typical_use: str
    hardness: str
    note: str
    family: str | None = None


class MatrixBand(BaseModel):
    band: str
    route: str
    tooling: str
    is_current: bool = False
    processes: list[str] = Field(default_factory=list)
    unpriced: list[str] = Field(default_factory=list)
    no_tooling: bool = False
    grades: list[str] = Field(default_factory=list)


class MatrixAdvice(BaseModel):
    covered: bool
    row_id: str | None = None
    material: str = ""
    form: str = ""
    chosen_by: str = "auto"  # "auto" (from the part material) or "user"
    band: str = ""
    route: str = ""
    tooling: str = ""
    comment: str = ""
    no_tooling: bool = False
    current_process_listed: bool = False
    current_process_band: str | None = None
    bands: list[MatrixBand] = Field(default_factory=list)
    grades: list[MatrixGrade] = Field(default_factory=list)
    message: str = ""


def interpret_row(entry: dict) -> list[dict]:
    """Route and grade interpretation for every band of a matrix row."""
    out, previous = [], None
    for cell in entry["bands"]:
        parsed = route_processes(entry["id"], cell["route"], cell["tooling"], previous)
        parsed["grades"] = tooling_grades(cell["tooling"])
        out.append(parsed)
        previous = parsed["codes"] or previous
    return out


def advice(request) -> MatrixAdvice:
    quantity = request.expected_quantity or request.expected_cycles
    process = request.process.value
    chosen = getattr(request, "part_material_detail", None)
    row_id = chosen or auto_row_id(request.workpiece_material.value, process)
    entry = row(row_id) if row_id else None
    if entry is None:
        return MatrixAdvice(covered=False, message=(
            "The process matrix does not cover this part material. Choose the closest material grade and form "
            "to see its recommended route."))
    current = band_index(quantity)
    parsed = interpret_row(entry)
    bands = [
        MatrixBand(band=b["band"], route=cell["route"], tooling=cell["tooling"], is_current=i == current,
                   processes=p["codes"], unpriced=p["unpriced"], no_tooling=p["no_tooling"], grades=p["grades"])
        for i, (b, cell, p) in enumerate(zip(matrix()["bands"], entry["bands"], parsed))
    ]
    aliases = {"stamping": "punching_blanking", "plastic_molding": "plastic_injection", "metal_molding": "die_casting",
               "forming": "sheet_hydroforming", "deep_drawing": "sheet_hydroforming"}
    code = aliases.get(process, process)
    listed_in = [b.band for b in bands if code in b.processes]
    grades = []
    for name in bands[current].grades:
        details = grade_details(name)
        if details:
            grades.append(MatrixGrade(name=name, typical_use=details["typical_use"], hardness=details["hardness"],
                                      note=details["note"], family=GRADE_FAMILY.get(name)))
    return MatrixAdvice(
        covered=True, row_id=entry["id"], material=entry["material"], form=entry["form"],
        chosen_by="user" if chosen else "auto", band=bands[current].band, route=bands[current].route,
        tooling=bands[current].tooling, comment=entry["comment"], no_tooling=bands[current].no_tooling,
        current_process_listed=code in bands[current].processes,
        current_process_band=None if code in bands[current].processes else (listed_in[0] if listed_in else None),
        bands=bands, grades=grades,
    )


def public_matrix() -> dict:
    data = matrix()
    return {
        "bands": data["bands"],
        "rows": [{"id": r["id"], "material": r["material"], "form": r["form"], "workpiece_material": ROW_WORKPIECE.get(r["id"])}
                 for r in data["rows"]],
    }
