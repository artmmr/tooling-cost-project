"""Tool life and lifetime tooling cost.

A tool's working components (cavities, cores, punches, dies, pins, rollers,
patterns) wear out. When the lifetime quantity is larger than their typical life,
replacement sets are needed. Supports, carriers, holders and strippers normally
last the whole programme and are not replaced.

The life values are typical planning figures from tooling practice (cycles per
working set, including normal regrinding and polishing). Real life depends on
part geometry, alloy, temperature control, coating and maintenance, so the
result is a planning estimate, not a guarantee.
"""
from __future__ import annotations

from math import ceil

from pydantic import BaseModel, Field

from app.complete_tool import commercial_factor

# Roles that hold or guide the working components and are not normally replaced.
NON_WORKING_ROLES = ("SUPPORT", "STRIPPER", "HOLDER", "FLUID CHAMBER", "BLANK HOLDER")


CONTINUOUS = {"metal_extrusion", "plastic_extrusion", "pultrusion"}
CUTTING = {"punching_blanking", "progressive_die_stamping", "stamping", "fine_blanking"}
FILLED = {"glass_filled_thermoplastic", "mineral_filled_thermoplastic", "fiber_composite", "metal_powder"}

# Typical life of injection-type molds by tooling family (shots per cavity set).
MOLD_LIFE = {
    "aluminum_tooling": 50_000,
    "pre_hardened_mold_steel": 500_000,
    "hardened_mold_steel": 1_000_000,
    "corrosion_resistant_mold_steel": 1_000_000,
    "high_wear_cold_work_steel": 1_000_000,
    "carbide": 2_000_000,
    "cold_work_tool_steel": 300_000,
    "high_toughness_cold_work_steel": 300_000,
}
# Typical life of cutting and forming punches and dies, including regrinds (hits).
CUTTING_LIFE = {
    "cold_work_tool_steel": 1_000_000,
    "high_wear_cold_work_steel": 3_000_000,
    "high_toughness_cold_work_steel": 1_500_000,
    "hardened_mold_steel": 500_000,
    "pre_hardened_mold_steel": 100_000,
    "corrosion_resistant_mold_steel": 300_000,
    "aluminum_tooling": 5_000,
    "carbide": 10_000_000,
}
# Harder or stickier sheet shortens punch and die life.
SHEET_FACTOR = {"advanced_high_strength_steel": 0.4, "high_strength_steel": 0.6, "stainless_steel": 0.5}

# Fixed typical life per process where the tooling family matters less than the process.
PROCESS_LIFE = {
    "blow_molding": 2_000_000,
    "rotational_molding": 10_000,
    "investment_casting": 250_000,
    "sand_casting": 50_000,
    "powder_metallurgy": 500_000,
    "metal_injection_molding": 500_000,
    "bending": 1_000_000,
    "sheet_hydroforming": 200_000,
    "tube_hydroforming": 500_000,
    "spinning": 50_000,
    "thermoforming": 250_000,
}
DIE_CASTING_LIFE = {"copper_brass": 20_000}
DIE_CASTING_DETAIL_LIFE = {"zinc_die_casting": 500_000, "magnesium_complex_part": 200_000}
FORGING_LIFE = {"stainless_steel": 6_000, "cast_aluminum": 40_000, "aluminum_sheet": 40_000, "copper_brass": 25_000}
FORGING_DETAIL_LIFE = {"titanium_solid": 4_000}
# Forging trim punches and dies only shear the flash; they outlast the hot impression dies.
FORGING_TRIM_LIFE = 100_000


class LifeItem(BaseModel):
    component: str
    life: int
    replacements: int
    replacement_cost: float


class ToolLife(BaseModel):
    modelled: bool
    shots: int = 0
    life: int | None = None
    replacements: int = 0
    replacement_cost: float = 0
    lifetime_cost: float = 0
    lifetime_per_part: float = 0
    items: list[LifeItem] = Field(default_factory=list)
    basis: str = ""


def typical_life(process: str, family: str | None, workpiece: str, detail: str | None = None) -> int | None:
    """Typical cycles per working set, or None where life is not counted in parts."""
    if process in CONTINUOUS:
        return None
    if process in {"die_casting", "metal_molding"}:
        return DIE_CASTING_DETAIL_LIFE.get(detail) or DIE_CASTING_LIFE.get(workpiece, 100_000)
    if process == "closed_die_forging":
        return FORGING_DETAIL_LIFE.get(detail) or FORGING_LIFE.get(workpiece, 10_000)
    if process in CUTTING or process in {"forming", "deep_drawing"}:
        life = CUTTING_LIFE.get(family or "", 1_000_000) * SHEET_FACTOR.get(workpiece, 1.0)
        return int(life * (0.4 if process == "fine_blanking" else 1.0))
    if process in PROCESS_LIFE:
        return PROCESS_LIFE[process]
    if process == "composite_molding":
        return 3_000 if family == "aluminum_tooling" else 10_000
    # Injection, compression, transfer and foam molding.
    life = MOLD_LIFE.get(family or "", 500_000)
    if process in {"compression_molding", "transfer_molding"} and family == "pre_hardened_mold_steel":
        life = 250_000
    if workpiece in FILLED or workpiece == "thermoset":
        life //= 2
    return life


def _working(role: str) -> bool:
    role = (role or "").upper()
    return not any(word in role for word in NON_WORKING_ROLES)


def estimate(request, result, family: str | None = None) -> ToolLife:
    """Lifetime tooling cost for one calculation result.

    ``family`` forces one tooling family for every block (used when pricing
    material alternatives of a broad-process tool).
    """
    process = request.process.value
    quantity = request.expected_quantity or request.expected_cycles
    workpiece = request.workpiece_material.value
    detail = getattr(request, "part_material_detail", None)
    # Detailed processes: identical sets run in parallel. Broad processes: cavities share one tool.
    shots = ceil(quantity / max(1, request.parts_per_mold))
    if process in CONTINUOUS:
        return ToolLife(modelled=False, shots=shots, lifetime_cost=result.total_price,
                        lifetime_per_part=result.total_price / quantity,
                        basis="Extrusion and pultrusion die life is measured in length or tonnes of product, not parts, so replacements are not estimated.")
    items = []
    factor = commercial_factor(request.assumptions)
    workbook = result.calculation_basis == "workbook_v4"
    if workbook:
        for block in result.tooling_blocks:
            if block.purchased or not _working(block.role) or block.cost_before_commercial is None:
                continue
            life = typical_life(process, family or block.material_family, workpiece, detail)
            if process == "closed_die_forging" and "trim" in block.component.lower():
                life = FORGING_TRIM_LIFE
            replacements = max(0, ceil(shots / life) - 1) if life else 0
            items.append(LifeItem(component=block.component, life=life or 0, replacements=replacements,
                                  replacement_cost=replacements * block.cost_before_commercial * factor))
    else:
        life = typical_life(process, family or result.recommended_material_family, workpiece, detail)
        replacements = max(0, ceil(shots / life) - 1) if life else 0
        items.append(LifeItem(component="Cavity and core inserts", life=life or 0, replacements=replacements,
                              replacement_cost=replacements * result.working_components_cost * factor))
    replacement_cost = sum(i.replacement_cost for i in items)
    lifetime = result.total_price + replacement_cost
    lives = [i.life for i in items if i.life]
    return ToolLife(
        modelled=True, shots=shots, life=min(lives) if lives else None,
        replacements=max((i.replacements for i in items), default=0),
        replacement_cost=replacement_cost, lifetime_cost=lifetime, lifetime_per_part=lifetime / quantity,
        items=items,
        basis=("Working components (cavities, cores, punches, dies), including their construction hours, are replaced when the cycles per tool exceed their typical life; "
               "carriers and holders are kept. Life values are typical planning figures including normal regrinding; "
               "geometry, alloy, temperature control, coating and maintenance change them."),
    )
