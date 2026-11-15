"""Advanced production report built around one calculation request.

Everything here is deterministic. The report reuses the tooling calculator to
price alternatives (tooling materials, part processes, countries, quantity
bands) and adds rule-based engineering guidance. The optional AI summary in
``app.summary`` only rewrites these computed facts; it never adds numbers.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.calculator import calculate
from app.country_profiles import COUNTRY_PROFILES, assumptions_in_eur
from app.fx import eur_usd_or_none
from app.tool_life import ToolLife, estimate as tool_life_estimate
from app.process_matrix import GRADE_FAMILY, MatrixAdvice, advice as matrix_advice, row as matrix_row
from app.models import CalculationRequest, CalculationResponse, CostAssumptions, CycleBand, ProcessType
from app.tooling_catalog import catalog, is_workbook_process
from app.tooling_materials import TOOLING_MATERIALS

Fit = Literal["strong", "suitable", "limited", "not_recommended"]
FIT_ORDER = {"strong": 0, "suitable": 1, "limited": 2, "not_recommended": 3}
FIT_FROM_SCORE = {3: "strong", 2: "suitable", 1: "limited", 0: "not_recommended"}


# =========================================================
# Response contract
# =========================================================

class CostDriver(BaseModel):
    key: str
    label: str
    amount: float
    share: float


class MaterialOption(BaseModel):
    lifetime_price: float | None = None
    replacements: int = 0
    family: str
    name: str
    fit: Fit
    price: float | None = None
    is_current: bool = False
    heat_treatment: bool = False
    reasons: list[str] = Field(default_factory=list)


class ProcessOption(BaseModel):
    lifetime_price: float | None = None
    replacements: int = 0
    process: str
    label: str
    fit: Fit
    tooling_price: float | None = None
    tooling_per_part: float | None = None
    piece_cost: str
    tolerance: str
    economic_quantity: str
    is_current: bool = False
    strengths: str
    limits: str
    notes: list[str] = Field(default_factory=list)


class CountryOption(BaseModel):
    code: str
    name: str
    currency: str = "EUR"
    price: float | None = None
    is_current: bool = False


class QuantityOption(BaseModel):
    lifetime_price: float | None = None
    replacements: int = 0
    band: str
    quantity: int
    concept: str = ""
    price: float | None = None
    per_part: float | None = None
    is_current: bool = False


class RiskItem(BaseModel):
    risk: str
    explanation: str
    mitigation: str


class AdvancedReport(BaseModel):
    base: CalculationResponse
    tool_life: ToolLife
    matrix: MatrixAdvice
    quantity: int
    tooling_per_part: float
    cost_drivers: list[CostDriver]
    material_options: list[MaterialOption]
    material_basis: str
    process_options: list[ProcessOption]
    country_options: list[CountryOption]
    country_basis: str
    quantity_options: list[QuantityOption]
    risks: list[RiskItem]
    design_notes: list[str]
    production_steps: list[str]
    method_notes: list[str]


# =========================================================
# Reference tables (general engineering practice, planning level)
# =========================================================

SHEET = {"mild_steel", "high_strength_steel", "advanced_high_strength_steel", "stainless_steel", "aluminum_sheet", "copper_brass"}
THERMOPLASTICS = {"standard_thermoplastic", "glass_filled_thermoplastic", "mineral_filled_thermoplastic", "corrosive_polymer"}
ABRASIVE = {"glass_filled_thermoplastic", "mineral_filled_thermoplastic", "thermoset", "fiber_composite", "metal_powder"}
HARD_SHEET = {"high_strength_steel", "advanced_high_strength_steel", "stainless_steel"}

# materials, economic quantity (min, max or None), piece cost, tolerance, strengths, limits, shape caveat
PROCESS_PROFILES: dict[str, dict] = {
    "bending": dict(materials=SHEET, qty=(1, 100_000), piece="medium", tol="±0.2 mm",
                    strengths="Very low tooling cost; standard punches and dies cover most bends.",
                    limits="Only bent sheet shapes; each bend adds handling time."),
    "punching_blanking": dict(materials=SHEET, qty=(1_000, None), piece="low", tol="±0.1 mm",
                              strengths="Fast, cheap flat parts in high volume.",
                              limits="Flat profiles only; sheared edge has burr and fracture zone."),
    "fine_blanking": dict(materials=SHEET - {"advanced_high_strength_steel"}, qty=(10_000, None), piece="low", tol="±0.02 mm",
                          strengths="Clean, square, fully sheared edges without secondary machining.",
                          limits="Expensive tools and triple-action presses; thickness usually ≤ 15 mm.", max_thickness=15),
    "progressive_die_stamping": dict(materials=SHEET, qty=(50_000, None), piece="very low", tol="±0.05 mm",
                                     strengths="Lowest piece cost for formed sheet parts at high volume.",
                                     limits="High tooling cost and long lead time; design changes are costly."),
    "sheet_hydroforming": dict(materials=SHEET, qty=(100, 50_000), piece="medium", tol="±0.1 mm",
                               strengths="Deep or complex shapes with a single-sided tool.",
                               limits="Slow cycle; needs a hydroforming press."),
    "tube_hydroforming": dict(materials=SHEET - {"copper_brass"}, qty=(10_000, None), piece="medium", tol="±0.1 mm",
                              strengths="Light, stiff hollow tubular parts in one piece.",
                              limits="Tubular parts only; long process development.", shape="Only for tubular parts."),
    "spinning": dict(materials=SHEET, qty=(1, 5_000), piece="high", tol="±0.25 mm",
                     strengths="Very low tooling cost for round shells.",
                     limits="Rotationally symmetric parts only; slower per part.", shape="Only for round, rotationally symmetric parts."),
    "die_casting": dict(materials={"cast_aluminum", "copper_brass"}, qty=(5_000, None), piece="low", tol="±0.1 mm",
                        strengths="Thin walls, good surface and low piece cost at volume.",
                        limits="Non-ferrous alloys only; expensive hot-work dies; porosity limits welding and heat treatment.",
                        min_wall=1.0),
    "sand_casting": dict(materials={"cast_aluminum", "cast_iron", "stainless_steel", "copper_brass", "mild_steel"}, qty=(1, 5_000),
                         piece="medium", tol="±1.0 mm",
                         strengths="Cheapest tooling; any size; almost any castable alloy.",
                         limits="Rough surface and loose tolerances; functional faces need machining.", min_wall=3.0),
    "investment_casting": dict(materials={"cast_aluminum", "stainless_steel", "mild_steel", "high_strength_steel", "copper_brass", "cast_iron"},
                               qty=(100, 50_000), piece="high", tol="±0.15 mm",
                               strengths="Complex near-net shapes in almost any alloy, including steels.",
                               limits="High piece cost; practical size limit around 500 mm.", min_wall=1.5, max_size=500),
    "closed_die_forging": dict(materials={"mild_steel", "high_strength_steel", "stainless_steel", "aluminum_sheet", "cast_aluminum", "copper_brass"},
                               qty=(1_000, None), piece="medium", tol="±0.5 mm",
                               strengths="Highest strength and fatigue resistance from grain flow.",
                               limits="Draft angles and flash; functional surfaces need machining."),
    "metal_extrusion": dict(materials={"cast_aluminum", "aluminum_sheet", "copper_brass"}, qty=(1_000, None), piece="very low", tol="±0.2 mm",
                            strengths="Cheap dies for constant cross-sections in aluminium or brass.",
                            limits="Constant cross-section only; parts are cut from long lengths.", profile=True),
    "powder_metallurgy": dict(materials={"metal_powder"}, qty=(10_000, None), piece="low", tol="±0.05 mm",
                              strengths="Net-shape parts with almost no material waste.",
                              limits="Limited height and no undercuts in the pressing direction; residual porosity."),
    "metal_injection_molding": dict(materials={"metal_powder", "stainless_steel"}, qty=(10_000, None), piece="medium", tol="±0.3 %",
                                    strengths="Small, very complex metal parts.",
                                    limits="Best below about 100 mm and 100 g; sintering shrinkage must be compensated.", max_size=100),
    "plastic_injection": dict(materials=THERMOPLASTICS | {"elastomer"}, qty=(5_000, None), piece="low", tol="±0.05 mm",
                              strengths="Lowest piece cost and highest detail for plastic parts at volume.",
                              limits="Expensive molds; uniform wall thickness and draft are required."),
    "compression_molding": dict(materials={"thermoset", "fiber_composite", "elastomer"}, qty=(1_000, 100_000), piece="medium", tol="±0.1 mm",
                                strengths="Robust thermoset and composite parts with simple tools.",
                                limits="Longer cycles; flash must be trimmed."),
    "transfer_molding": dict(materials={"thermoset", "elastomer"}, qty=(5_000, None), piece="medium", tol="±0.05 mm",
                             strengths="Precise thermoset parts and over-molded inserts.",
                             limits="Material waste in the transfer pot and runners."),
    "blow_molding": dict(materials={"standard_thermoplastic"}, qty=(5_000, None), piece="low", tol="±0.3 mm",
                         strengths="Cheap hollow containers and ducts.",
                         limits="Hollow parts only; wall thickness varies.", shape="Only for hollow parts."),
    "rotational_molding": dict(materials={"standard_thermoplastic"}, qty=(100, 10_000), piece="high", tol="±0.5 mm",
                               strengths="Low tooling cost for large, hollow, stress-free parts.",
                               limits="Long cycles and loose tolerances.", shape="Only for hollow parts."),
    "thermoforming": dict(materials=THERMOPLASTICS, qty=(100, 10_000), piece="medium", tol="±0.5 mm",
                          strengths="Low tooling cost for thin shells and covers.",
                          limits="One-sided detail only; walls thin out in corners."),
    "plastic_extrusion": dict(materials=THERMOPLASTICS | {"elastomer"}, qty=(1_000, None), piece="very low", tol="±0.2 mm",
                              strengths="Cheap continuous profiles.",
                              limits="Constant cross-section only.", profile=True),
    "composite_molding": dict(materials={"fiber_composite"}, qty=(10, 5_000), piece="high", tol="±0.2 mm",
                              strengths="Very light, stiff parts.",
                              limits="Labour-intensive layup and long cure cycles."),
    "pultrusion": dict(materials={"fiber_composite"}, qty=(1_000, None), piece="low", tol="±0.2 mm",
                       strengths="Continuous composite profiles at low cost.",
                       limits="Constant cross-section only.", profile=True),
}
# Broad legacy processes map onto the closest detailed profile for display.
LEGACY_ALIASES = {"plastic_molding": "plastic_injection", "foaming": "plastic_injection", "metal_molding": "die_casting",
                  "stamping": "progressive_die_stamping", "forming": "sheet_hydroforming", "deep_drawing": "sheet_hydroforming"}

HOT = {"die_casting", "closed_die_forging", "metal_extrusion", "metal_molding"}
CUTTING = {"punching_blanking", "fine_blanking", "progressive_die_stamping", "stamping"}
FORMING = {"bending", "sheet_hydroforming", "tube_hydroforming", "spinning", "forming", "deep_drawing"}
POWDER = {"powder_metallurgy", "metal_injection_molding"}
# Sheet parts and bulk parts are not interchangeable even in the same alloy.
SHEET_PROCESSES = CUTTING | FORMING

FAMILY_NOTES = {
    "aluminum_tooling": "Fast to machine and cheap, so lead time is short. Soft, so it wears quickly.",
    "pre_hardened_mold_steel": "P20 or 4140 type, supplied hardened. Machined directly with no heat-treatment distortion.",
    "hardened_mold_steel": "H13 type hot-work steel. Withstands heat cycling and high cavity pressure once hardened.",
    "corrosion_resistant_mold_steel": "Stainless mold steel. Resists corrosive melts and humidity, and polishes to a high finish.",
    "cold_work_tool_steel": "D2 or A2 type. Hard, wear-resistant cutting and forming edges for cold processes.",
    "high_wear_cold_work_steel": "Powder-metallurgy tool steel or carbide. Keeps sharp edges against abrasive or very strong materials.",
    "high_toughness_cold_work_steel": "Tough cold-work grade. Resists chipping and cracking under shock loads.",
    "carbide": "Sintered tungsten carbide. Extreme wear life for punches, dies and liners, but brittle and shaped only by EDM and grinding.",
}

RISK_HELP = {
    "abrasive wear": ("Fillers or hard particles gradually wear tool surfaces and move part dimensions.",
                      "Use wear-resistant inserts in high-wear areas, and add nitriding or PVD coating. Plan insert replacement."),
    "corrosion": ("Chemical attack damages the tool surface and spoils part quality.",
                  "Use stainless mold steel or chrome plating, and vent gases well."),
    "surface degradation": ("Tool surfaces deteriorate, so parts lose finish quality.",
                            "Specify polishing grade, coating and a maintenance interval at order."),
    "long-term wear": ("Repeated cycles wear the tool and raise maintenance cost.",
                       "Choose a harder grade for long runs, and keep spare inserts for wear parts."),
    "dimensional drift": ("Wear or deformation slowly moves parts out of tolerance.",
                          "Add SPC checks on critical dimensions, and design replaceable inserts at critical features."),
    "galling": ("Workpiece material sticks to the tool, causing scratches and seizure.",
                "Use coated or PM tool steel, polish forming radii, and specify proper lubrication."),
    "chipping": ("Small pieces break off cutting edges under load.",
                 "Use a tougher grade, add edge preparation, and set the right cutting clearance."),
    "cracking": ("Repeated or severe loads crack the tool.",
                 "Use generous radii, prestressed inserts and proper tempering. Avoid sharp internal corners."),
    "plastic deformation": ("High contact pressure permanently deforms the tool.",
                            "Increase working hardness, or use a stronger grade at high-load areas."),
    "high mechanical loading": ("High forces stress punches, dies and forming surfaces.",
                                "Validate the tool with press-force simulation, and size support plates and guides generously."),
    "soldering": ("Molten aluminium bonds to the die steel, tearing the part surface and building up on cores.",
                  "Nitride or PVD-coat the cavity, keep draft on cores, use die release spray and control die temperature."),
    "erosion": ("Fast metal flow at the gates and opposite them washes away die steel.",
                "Size gates for lower velocity, use replaceable gate inserts, and coat high-flow areas."),
    "thermal fatigue": ("Heat cycling causes surface heat-checking cracks.",
                        "Use premium H13 with proper tempering, apply die spray, and preheat the die."),
}


# =========================================================
# Helpers
# =========================================================

def _quantity(request: CalculationRequest) -> int:
    return request.expected_quantity or request.expected_cycles


def _legacy_band(quantity: int) -> CycleBand:
    if quantity <= 10_000:
        return CycleBand.UP_TO_10K
    if quantity <= 100_000:
        return CycleBand.FROM_10K_TO_100K
    return CycleBand.FROM_100K_TO_250K


def _safe_price(request: CalculationRequest, **kwargs) -> CalculationResponse | None:
    try:
        return calculate(request, **kwargs)
    except (ValueError, KeyError, ZeroDivisionError):
        return None


def _profile_key(process: str) -> str:
    return LEGACY_ALIASES.get(process, process)


def _process_label(process: str) -> str:
    for p in catalog()["processes"]:
        if p["code"] == process:
            return p["label"]
    return process.replace("_", " ").capitalize()


def _for_process(request: CalculationRequest, process: str) -> CalculationRequest:
    """The same part, quantity and costs, made with another process (default tool sizing)."""
    quantity = _quantity(request)
    update = dict(process=ProcessType(process), block_overrides=[], sizing_mode="part_scaled",
                  tooling_material_family=None, tooling_material_assumptions=None, manufacturing_route=None, force_tooling_material=False)
    if is_workbook_process(process):
        update.update(expected_quantity=quantity)
    else:
        update.update(expected_quantity=None, expected_cycles=quantity, cycle_band=_legacy_band(quantity))
    return request.model_copy(update=update)


# =========================================================
# Sections
# =========================================================

def cost_drivers(base: CalculationResponse) -> list[CostDriver]:
    groups = [
        ("material", "Tooling material", base.material_cost + base.transformation_cost),
        ("machining", "Bulk machining", base.outside_machining_cost + base.inside_machining_cost),
        ("construction", "Construction (programming, finishing, EDM, fitting)", base.construction_cost),
        ("design", "Design and engineering", base.design_cost),
        ("base", "Tool base and standard parts", base.standard_parts_cost),
        ("tryout", "Assembly and tryout", base.assembly_tryout_cost),
        ("energy", "Machine energy", base.energy_cost),
        ("cutters", "Cutting tools", base.milling_tool_cost),
        ("heat", "Heat treatment", base.heat_treatment_cost),
        ("cooling", "Cooling system", base.cooling_cost),
        ("purchased", "Purchased assemblies", base.purchased_assemblies_cost),
        ("transport", "Transport", base.transport_cost),
        ("commercial", "Overhead and supplier margin", base.overhead_cost + base.margin + base.handling_cost + base.final_markup),
    ]
    total = sum(amount for _, _, amount in groups) or 1
    drivers = [CostDriver(key=k, label=l, amount=a, share=a / total) for k, l, a in groups if a > 0.005]
    return sorted(drivers, key=lambda d: -d.amount)


def _material_score(family: str, request: CalculationRequest) -> tuple[int, list[str]]:
    process = request.process.value
    material = request.workpiece_material.value
    quantity = _quantity(request)
    abrasive = request.abrasive_material or material in ABRASIVE
    corrosive = request.corrosive_environment or material == "corrosive_polymer"
    reasons: list[str] = []

    if process in HOT:
        score = {"hardened_mold_steel": 3, "high_toughness_cold_work_steel": 1, "pre_hardened_mold_steel": 1}.get(family, 0)
        if family == "hardened_mold_steel":
            reasons.append("Hot-work steel is the standard for molten metal or hot billets: it resists heat checking.")
        elif family == "pre_hardened_mold_steel":
            reasons.append("Only for holders and support plates. Hot cavities lose hardness quickly.")
        elif family in {"aluminum_tooling", "corrosion_resistant_mold_steel", "cold_work_tool_steel", "high_wear_cold_work_steel"}:
            reasons.append("Not rated for repeated contact with hot metal.")
    elif process in CUTTING:
        score = {"cold_work_tool_steel": 3, "high_wear_cold_work_steel": 2, "high_toughness_cold_work_steel": 2,
                 "pre_hardened_mold_steel": 1, "hardened_mold_steel": 1}.get(family, 0)
        if family == "high_wear_cold_work_steel" and (quantity > 100_000 or material in HARD_SHEET or abrasive):
            score = 3
            reasons.append("Keeps cutting edges sharp at high volume or with strong and stainless sheet.")
        if family == "cold_work_tool_steel" and quantity > 1_000_000:
            score = 2
            reasons.append("Edges need frequent regrinding at this volume.")
        if family == "high_toughness_cold_work_steel" and material == "advanced_high_strength_steel":
            score = 3
            reasons.append("Advanced high-strength steel chips brittle punch edges, so toughness matters.")
        if family == "pre_hardened_mold_steel":
            reasons.append("Suitable for die shoes and plates, not for cutting edges.")
        if family == "aluminum_tooling":
            reasons.append("Too soft for cutting edges.")
    elif process in FORMING:
        score = {"cold_work_tool_steel": 3, "high_wear_cold_work_steel": 2, "high_toughness_cold_work_steel": 2,
                 "pre_hardened_mold_steel": 2, "hardened_mold_steel": 1, "aluminum_tooling": 1}.get(family, 0)
        if family == "aluminum_tooling":
            if quantity <= 1_000 and material in {"aluminum_sheet", "copper_brass", "mild_steel"}:
                reasons.append("Fine for prototypes and short runs of soft sheet.")
            else:
                score = 0
                reasons.append("Wears and deforms quickly at this volume or sheet strength.")
        if family == "pre_hardened_mold_steel" and quantity > 10_000:
            score = 1
            reasons.append("Forming radii wear quickly beyond about 10,000 parts.")
        if family in {"high_wear_cold_work_steel", "high_toughness_cold_work_steel"} and material in HARD_SHEET:
            score = 3
            reasons.append("Strong or stainless sheet causes galling and high contact pressure, which this grade handles.")
    elif process in POWDER:
        score = {"high_wear_cold_work_steel": 3, "hardened_mold_steel": 2, "cold_work_tool_steel": 2,
                 "corrosion_resistant_mold_steel": 1, "high_toughness_cold_work_steel": 1}.get(family, 0)
        if process == "metal_injection_molding" and family == "hardened_mold_steel":
            score = 3
            reasons.append("Hardened mold steel handles the abrasive metal feedstock at injection pressure.")
        if family == "high_wear_cold_work_steel":
            reasons.append("Metal powder is highly abrasive, so dies and punches need a wear-resistant grade.")
    else:  # molding: plastics, composites, wax patterns, sand patterns
        score = {"aluminum_tooling": 3, "pre_hardened_mold_steel": 3, "hardened_mold_steel": 2,
                 "corrosion_resistant_mold_steel": 2, "high_wear_cold_work_steel": 1}.get(family, 0)
        if family == "aluminum_tooling":
            if quantity > 100_000 or abrasive:
                score = 1
                reasons.append("Wears quickly at high volume or with filled materials.")
            elif quantity > 10_000:
                score = 2
                reasons.append("Usable up to about 100,000 parts with care. Steel is safer.")
            else:
                reasons.append("The cheapest, fastest option for low volume.")
        if family == "pre_hardened_mold_steel" and (quantity > 500_000 or abrasive):
            score = 2
            reasons.append("Consider hardened inserts at high-wear areas.")
        if family == "hardened_mold_steel" and (quantity > 100_000 or abrasive):
            score = 3
            reasons.append("Long life and resistance to filled or abrasive materials.")
        if family == "corrosion_resistant_mold_steel" and (corrosive or request.surface_finish.value == "optical"):
            score = 3
            reasons.append("Needed for corrosive melts or optical finishes.")
        if family == "high_wear_cold_work_steel" and abrasive:
            score = 2
            reasons.append("Use it as wear inserts at gates and high-flow areas.")
        if family == "cold_work_tool_steel":
            reasons.append("Not intended for mold cavities.")
        if process == "sand_casting" and family == "aluminum_tooling":
            reasons.append("Common choice for sand-casting patterns and core boxes.")

    if family == "carbide":
        if process in CUTTING:
            score = 3 if quantity > 5_000_000 or (quantity > 1_000_000 and (material in HARD_SHEET or abrasive)) else 2 if quantity > 500_000 else 1
            reasons.append("Pays off over millions of hits; usually used as inserts in a steel die rather than as solid blocks.")
        elif process == "powder_metallurgy":
            score = 3
            reasons.append("Standard for compaction die liners: metal powder is highly abrasive.")
        elif process == "metal_injection_molding":
            score = 1
            reasons.append("Only for small wear inserts at gates.")
        else:
            score = 0
            reasons.append("Too brittle for impact, thermal cycling or large cavities.")
    if corrosive and family not in {"corrosion_resistant_mold_steel"} and score >= 2 and process not in CUTTING | FORMING:
        score -= 1
        reasons.append("Needs coating or plating against corrosion.")
    return score, reasons


def _matrix_families(advice: MatrixAdvice) -> dict[str, list[str]]:
    """Cost families named by the matrix for the current band, with the grades behind each.

    Only when the matrix route is the selected process: a grade the matrix names for
    stamping must not be recommended for a die-casting die.
    """
    families: dict[str, list[str]] = {}
    for grade in advice.grades if advice.covered and advice.current_process_listed else []:
        if grade.family:
            families.setdefault(grade.family, []).append(grade.name)
    return families


def material_options(request: CalculationRequest, base: CalculationResponse,
                     advice: MatrixAdvice | None = None) -> tuple[list[MaterialOption], str]:
    recommended = _matrix_families(advice) if advice else {}
    workbook = base.calculation_basis == "workbook_v4"
    machined = [b for b in base.tooling_blocks if not b.purchased]
    used = {b.material_family for b in machined if b.material_family}
    options = []
    if workbook:
        base_life = tool_life_estimate(request, base)
        options.append(MaterialOption(
            family="workbook_mix", name="Workbook mix (as estimated)", fit="strong", price=base.total_price, is_current=True,
            lifetime_price=base_life.lifetime_cost, replacements=base_life.replacements,
            heat_treatment=base.heat_treatment_cost > 0,
            reasons=[f"Each component uses its own benchmark material: {', '.join(sorted(TOOLING_MATERIALS[f].name for f in used))}."]
                    if used else [],
        ))
    for family, profile in TOOLING_MATERIALS.items():
        score, reasons = _material_score(family, request)
        if family in recommended:
            grades = recommended[family]
            score = 3
            details = {g.name: g for g in advice.grades}
            reasons.insert(0, f"Process matrix recommends {' / '.join(grades)} for {advice.band} parts of "
                              f"{advice.material.lower()} ({advice.form.lower()}): {details[grades[0]].hardness}.")
            if "C45 / mild steel" in grades:
                reasons.append("Priced with pre-hardened steel as a cost proxy; unhardened C45 is cheaper.")
        elif recommended and score == 3:
            score = 2
            reasons.append("Suitable, but not the grade the process matrix names for this quantity.")
        price = None
        if score > 0:
            if workbook:
                existing = {o.component_id: o for o in request.block_overrides}
                overrides = []
                for block in machined:
                    current = existing.get(block.component_id)
                    data = current.model_dump(exclude_none=True) if current else {"component_id": block.component_id}
                    data.pop("tooling_material_assumptions", None)
                    data.pop("manufacturing_route", None)
                    data["material_family"] = family
                    overrides.append(data)
                overrides += [o for o in request.block_overrides if o.component_id not in {b.component_id for b in machined}]
                variant = CalculationRequest.model_validate({**request.model_dump(), "block_overrides": [
                    o if isinstance(o, dict) else o.model_dump(exclude_none=True) for o in overrides]})
                result = _safe_price(variant)
                life = tool_life_estimate(variant, result) if result else None
            else:
                same = family == (base.costing_material_family or base.recommended_material_family)
                result = base if same else _safe_price(request.model_copy(update=dict(
                    tooling_material_family=None, tooling_material_assumptions=None, manufacturing_route=None, force_tooling_material=False)),
                    force_material_family=family)
                life = tool_life_estimate(request, result, family=family) if result else None
            price = result.total_price if result else None
        options.append(MaterialOption(
            family=family, name=profile.name, fit=FIT_FROM_SCORE[score], price=price,
            lifetime_price=life.lifetime_cost if price is not None and life else None,
            replacements=life.replacements if price is not None and life else 0,
            is_current=not workbook and family == (base.costing_material_family or base.recommended_material_family),
            heat_treatment=profile.requires_heat_treatment,
            reasons=[FAMILY_NOTES[family], *reasons],
        ))
    options.sort(key=lambda o: (not o.is_current, FIT_ORDER[o.fit],
                                o.lifetime_price if o.lifetime_price is not None else float("inf")))
    basis = ("Each alternative prices every machined block in that one material, keeping the same sizes. "
             "Real tools usually mix grades: plates in pre-hardened steel, working inserts in a harder grade."
             if workbook else
             "Each alternative is the same tool priced with that material's benchmark price, machinability and heat treatment.")
    return options, basis


def process_options(request: CalculationRequest, base: CalculationResponse,
                    advice: MatrixAdvice | None = None) -> list[ProcessOption]:
    quantity = _quantity(request)
    material = request.workpiece_material.value
    current = request.process.value
    dims = sorted([request.part.length_mm, request.part.width_mm, request.part.height_mm], reverse=True)
    elongated = dims[0] >= 5 * dims[1]
    current_key = _profile_key(current)
    sheet_part = current_key in SHEET_PROCESSES
    candidates = [p for p, prof in PROCESS_PROFILES.items()
                  if material in prof["materials"] and (p in SHEET_PROCESSES) == sheet_part]
    if current_key not in candidates and current_key in PROCESS_PROFILES:
        candidates.append(current_key)

    # The process matrix (TCE workbook) is the primary source when it covers the material.
    covered = bool(advice and advice.covered)
    matrix_now: set[str] = set()
    matrix_near: dict[str, str] = {}
    if covered:
        index = next(i for i, b in enumerate(advice.bands) if b.is_current)
        matrix_now = set(advice.bands[index].processes)
        for j in (index - 1, index + 1):
            if 0 <= j < len(advice.bands):
                for code in advice.bands[j].processes:
                    matrix_near.setdefault(code, advice.bands[j].band)
        candidates += [c for c in [*matrix_now, *matrix_near] if c in PROCESS_PROFILES and c not in candidates]

    options = []
    for key in candidates:
        prof = PROCESS_PROFILES[key]
        is_current = key == current_key
        notes: list[str] = []
        score = 3
        low, high = prof["qty"]
        if quantity < low:
            score -= 2 if quantity < low / 10 else 1
            notes.append(f"Usually economic from about {low:,} parts. Tooling dominates below that.")
        if high is not None and quantity > high:
            score -= 2 if quantity > high * 10 else 1
            notes.append(f"Usually used up to about {high:,} parts. Piece cost or tool wear rises beyond that.")
        if prof.get("profile") and not elongated:
            score = 0
            notes.append("Needs a long part with a constant cross-section.")
        if prof.get("max_size") and dims[0] > prof["max_size"]:
            score -= 2
            notes.append(f"The part is larger than the usual {prof['max_size']} mm limit.")
        if prof.get("max_thickness") and request.material_thickness_mm > prof["max_thickness"]:
            score -= 2
            notes.append(f"Sheet thicker than {prof['max_thickness']} mm is beyond the usual range.")
        if prof.get("min_wall") and request.material_thickness_mm < prof["min_wall"]:
            score -= 1
            notes.append(f"Walls thinner than about {prof['min_wall']} mm are hard to fill or cast.")
        if prof.get("shape"):
            score = min(score, 2)
            notes.append(prof["shape"])
        if material not in prof["materials"] and key not in matrix_now and key not in matrix_near:
            score = 0
            notes.append("The selected part material is not normally made this way.")
        score = max(score, 0)
        if covered:
            subject = f"{advice.material.lower()} ({advice.form.lower()})"
            if key in matrix_now:
                score = 3 if not prof.get("profile") or elongated else score
                notes.insert(0, f"Process matrix: the route for {advice.band} parts of {subject} ({advice.route}; tooling {advice.tooling}).")
            elif key in matrix_near:
                score = min(max(score, 1), 2)
                notes.insert(0, f"Process matrix: recommended for {matrix_near[key]} parts of {subject}, a neighbouring quantity band.")
            else:
                score = min(score, 1)
                listed = [b.band for b in advice.bands if key in b.processes]
                notes.insert(0, f"Process matrix: used for {subject} at {', '.join(listed)} parts, not at your quantity."
                             if listed else f"Not a route in the process matrix for {subject}.")
        variant = request if is_current else _for_process(request, key)
        if is_current:
            result = base
        else:
            result = _safe_price(variant) if score > 0 else None
        price = result.total_price if result else None
        life = tool_life_estimate(variant, result) if result else None
        if life and life.replacements:
            notes.append(f"About {life.replacements} replacement set(s) of working components over {quantity:,} parts "
                         f"(typical life about {life.life:,} cycles).")
        options.append(ProcessOption(
            process=key, label=_process_label(key) if key != "plastic_injection" else "Plastic injection molding",
            fit=FIT_FROM_SCORE[score], tooling_price=price,
            tooling_per_part=life.lifetime_per_part if life else None,
            lifetime_price=life.lifetime_cost if life else None, replacements=life.replacements if life else 0,
            piece_cost=prof["piece"], tolerance=prof["tol"],
            economic_quantity=f"{low:,}+" if high is None else f"{low:,}–{high:,}",
            is_current=is_current, strengths=prof["strengths"], limits=prof["limits"], notes=notes,
        ))
    if covered:
        options += _matrix_route_options(advice, quantity)
    options.sort(key=lambda o: (not o.is_current, FIT_ORDER[o.fit],
                                o.lifetime_price if o.lifetime_price is not None else
                                (o.tooling_price if o.tooling_price is not None else float("inf"))))
    return options[:8]


def _matrix_route_options(advice: MatrixAdvice, quantity: int) -> list[ProcessOption]:
    """Matrix routes the calculator cannot price: no dedicated tool, or no cost model."""
    out = []
    index = next(i for i, b in enumerate(advice.bands) if b.is_current)
    for j in (index, index - 1, index + 1):
        if not 0 <= j < len(advice.bands):
            continue
        band = advice.bands[j]
        fit = "strong" if j == index else "suitable"
        where = f"Process matrix: the route for {band.band} parts" + ("" if j == index else ", a neighbouring quantity band")
        if band.no_tooling and not any(o.process == "no_dedicated_tooling" for o in out):
            out.append(ProcessOption(
                process="no_dedicated_tooling", label=f"{band.route} — no dedicated tool", fit=fit,
                tooling_price=0, tooling_per_part=0, piece_cost="high", tolerance="Machining tolerances",
                economic_quantity=band.band, strengths="No tooling investment or tool lead time, and design changes cost nothing.",
                limits="The highest cost per part; usually economic only for small quantities.",
                notes=[f"{where}. Tooling: {band.tooling}."],
            ))
        for label in band.unpriced:
            if not any(o.label == label for o in out):
                out.append(ProcessOption(
                    process="matrix:" + label.lower().replace(" ", "_"), label=label, fit=fit, piece_cost="—",
                    tolerance="—", economic_quantity=band.band, strengths=advice.comment or "Listed in the process matrix.",
                    limits="This app has no cost model for this route, so the tooling is not priced.",
                    notes=[f"{where}. Tooling: {band.tooling}."],
                ))
    return out


def country_options(request: CalculationRequest, base: CalculationResponse) -> list[CountryOption]:
    out = []
    fx = None
    for code, profile in COUNTRY_PROFILES.items():
        is_current = code == request.manufacturing_country
        price = None
        if is_current:
            price = base.total_price
        else:
            if profile["currency"] == "USD" and fx is None:
                fx = request.eur_to_usd or eur_usd_or_none() or 0
            try:
                assumptions = CostAssumptions(**assumptions_in_eur(code, fx))
            except ValueError:
                assumptions = None  # No exchange rate: the USD country cannot be compared.
            if assumptions is not None:
                result = _safe_price(request.model_copy(update=dict(manufacturing_country=code, assumptions=assumptions)))
                price = result.total_price if result else None
        out.append(CountryOption(code=code, name=profile["name"], currency=profile["currency"], price=price, is_current=is_current))
    return sorted(out, key=lambda c: c.price if c.price is not None else float("inf"))


def quantity_options(request: CalculationRequest, base: CalculationResponse) -> list[QuantityOption]:
    quantity = _quantity(request)
    out = []
    if base.calculation_basis == "workbook_v4":
        process = request.process.value
        grades = [g for g in catalog()["grades"] if g["process"] == process]
        for grade in grades:
            current = grade["quantity_min"] <= quantity and (grade["quantity_max"] is None or quantity <= grade["quantity_max"])
            # Price at the band's upper end (or the user's quantity) to show the lowest per-part cost of the band.
            # Open-ended bands are shown at a round ten times their minimum (e.g. 1,000,000).
            q = quantity if current else (grade["quantity_max"] or int(float(f"{grade['quantity_min'] * 10:.1g}")))
            variant = request.model_copy(update=dict(expected_quantity=q))
            result = base if current else _safe_price(variant)
            life = tool_life_estimate(variant, result) if result else None
            out.append(QuantityOption(band=grade["band"], quantity=q, concept=grade["concept"],
                                      price=result.total_price if result else None,
                                      lifetime_price=life.lifetime_cost if life else None,
                                      replacements=life.replacements if life else 0,
                                      per_part=life.lifetime_per_part if life else None, is_current=current))
    else:
        for band, q, label in [(CycleBand.UP_TO_10K, 10_000, "Up to 10,000"), (CycleBand.FROM_10K_TO_100K, 100_000, "10,000–100,000"),
                               (CycleBand.FROM_100K_TO_250K, 250_000, "100,000–250,000")]:
            current = band == request.cycle_band
            q2 = request.expected_cycles if current else q
            variant = request.model_copy(update=dict(cycle_band=band, expected_cycles=q2))
            result = base if current else _safe_price(variant)
            life = tool_life_estimate(variant, result) if result else None
            out.append(QuantityOption(band=label, quantity=q2, price=result.total_price if result else None,
                                      lifetime_price=life.lifetime_cost if life else None,
                                      replacements=life.replacements if life else 0,
                                      per_part=life.lifetime_per_part if life else None, is_current=current))
    return out


def risk_items(request: CalculationRequest, base: CalculationResponse) -> list[RiskItem]:
    modes = list(base.failure_modes)
    if request.process.value in HOT and "thermal fatigue" not in modes:
        modes.insert(0, "thermal fatigue")
    if request.process.value in {"die_casting", "metal_molding"}:
        for mode in ("soldering", "erosion"):
            if mode not in modes and (mode == "erosion" or request.workpiece_material.value in {"cast_aluminum", "aluminum_sheet"}):
                modes.append(mode)
    if (request.abrasive_material or request.workpiece_material.value in ABRASIVE) and "abrasive wear" not in modes:
        modes.append("abrasive wear")
    if request.workpiece_material.value in {"stainless_steel", "aluminum_sheet"} and request.process.value in CUTTING | FORMING and "galling" not in modes:
        modes.append("galling")
    items = []
    for mode in modes:
        explanation, mitigation = RISK_HELP.get(mode, ("Review this risk against the tool design.", "Discuss with the toolmaker."))
        items.append(RiskItem(risk=mode, explanation=explanation, mitigation=mitigation))
    return items


def design_notes(request: CalculationRequest, base: CalculationResponse, quantities: list[QuantityOption],
                 advice: MatrixAdvice | None = None) -> list[str]:
    notes = []
    if advice and advice.covered:
        if not advice.current_process_listed:
            when = (f" The matrix uses your process from {advice.current_process_band} parts."
                    if advice.current_process_band else "")
            notes.append(f"For {advice.band} parts of {advice.material.lower()} ({advice.form.lower()}), the process matrix "
                         f"recommends {advice.route}"
                         + (f" ({advice.tooling})" if advice.no_tooling else f" with {advice.tooling} tooling")
                         + f", not your selected process.{when}")
        if advice.comment:
            notes.append(f"Process matrix guidance for {advice.material.lower()}: {advice.comment}")
    dims = sorted([request.part.length_mm, request.part.width_mm, request.part.height_mm], reverse=True)
    process = request.process.value
    if request.tolerance_level.value == "high_precision":
        notes.append("High-precision tolerances need grinding or EDM finishing and closer inspection. "
                     "Apply them only to functional features, and use ±0.1 mm or looser elsewhere.")
    elif request.tolerance_level.value == "precision":
        notes.append("Precision tolerances add finishing passes. Check which features really need them.")
    if request.surface_finish.value == "optical":
        notes.append("Optical finish needs a polishable, corrosion-resistant steel and diamond polishing. "
                     "Polishing is not included in this estimate, so get a quote.")
    elif request.surface_finish.value == "high":
        notes.append("A high finish needs extra polishing time, which is not priced separately here.")
    if dims[0] > 600:
        notes.append(f"The part is {dims[0]:,.0f} mm long. Large blocks limit the choice of toolmakers and machines, so check capacity early.")
    if process in {"die_casting", "plastic_injection", "plastic_molding", "compression_molding", "transfer_molding", "metal_injection_molding"}:
        notes.append("Add draft angles (typically 1–2°) and keep wall thickness uniform. This avoids sink marks, porosity and sticking.")
    if process in {"sheet_hydroforming", "deep_drawing"} and dims[2] > 0.5 * dims[1]:
        notes.append("The draw is deep relative to the part width. It may need several draw stages or an intermediate anneal.")
    if process in CUTTING | FORMING and request.material_thickness_mm > 6:
        notes.append(f"{request.material_thickness_mm:g} mm sheet needs high press forces. Confirm press tonnage and stripper design.")
    if request.parts_per_mold > 1:
        notes.append(f"{request.parts_per_mold} identical tool sets are priced. A shared multi-cavity tool is often cheaper; ask the toolmaker.")
    # Data-driven: is the quantity just past a band boundary that makes the tool much more expensive?
    current = next((q for q in quantities if q.is_current), None)
    cheaper = [q for q in quantities if q.price is not None and q.quantity < (current.quantity if current else 0)]
    if current and current.price and cheaper:
        prev = cheaper[-1]
        if prev.price < current.price * 0.85:
            notes.append(f"Your quantity puts the tool in the {current.band} band. A tool for {prev.band} parts would cost about "
                         f"{(1 - prev.price / current.price) * 100:.0f}% less. Consider a cheaper tool now and a second tool later, "
                         "if the volume is uncertain.")
    if not notes:
        notes.append("No specific design-for-manufacturing issue was flagged by these rules.")
    return notes


def build_report(request: CalculationRequest) -> AdvancedReport:
    if request.part_material_detail and matrix_row(request.part_material_detail) is None:
        raise ValueError(f"Unknown material grade and form '{request.part_material_detail}'.")
    base = calculate(request)
    quantity = _quantity(request)
    advice = matrix_advice(request)
    materials, material_basis = material_options(request, base, advice)
    quantities = quantity_options(request, base)
    life = tool_life_estimate(request, base)
    return AdvancedReport(
        base=base,
        tool_life=life,
        matrix=advice,
        quantity=quantity,
        tooling_per_part=life.lifetime_per_part,
        cost_drivers=cost_drivers(base),
        material_options=materials,
        material_basis=material_basis,
        process_options=process_options(request, base, advice),
        country_options=country_options(request, base),
        country_basis=("Other countries use their default labour and machine rates. Your rate edits apply only to the selected country. "
                       "Transport distances are kept the same. China and India are costed in US dollars and converted at the "
                       "EUR/USD rate shown on the page."),
        quantity_options=quantities,
        risks=risk_items(request, base),
        design_notes=design_notes(request, base, quantities, advice),
        production_steps=base.recommended_operations,
        method_notes=[
            "Process comparison shows tooling cost only. Piece cost (cycle time, material, labour) is not modelled; "
            "the piece-cost level is a general guide.",
            "Fit ratings come from the process matrix and general engineering rules. Tool life uses typical planning values, "
            "not a validated life calculation for your geometry.",
            "Complete-tool estimate: working components, construction hours, design, tool base and standard parts, assembly "
            "and tryout. Hours are planning benchmarks calibrated to typical European toolmaker prices; hot runners and "
            "machine-specific automation are not included.",
        ],
    )
