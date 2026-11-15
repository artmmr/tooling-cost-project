"""From working blocks to a complete tool.

The block calculators price raw stock and the bulk removal of material. A
toolmaker's quote also contains work that does not scale with removed volume:

* construction hours for each working component: CAM programming, setups,
  semi-finishing and finishing, EDM and electrodes, cooling, ejector and guide
  holes, gating and venting, and bench fitting;
* tool design and engineering;
* a mould base or die set (when the calculator has not sized the carriers) and
  standard parts (guides, bushes, ejectors, screws, springs, locating rings);
* assembly and a tryout on the production machine.

The hours below are planning benchmarks per process, calibrated (Nov 2026) so
that each process's reference part, priced in Germany, lands inside a typical
European toolmaker price range for a complete tool (see
tests/test_complete_tool.py for the ranges). Construction and design hours grow
with the square root of the part span. Validate against real quotations and
adjust EFFORT when quotes are available.
Hot runners and machine-specific automation are not included.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Effort:
    design_base_h: float        # tool-level design and engineering
    design_per_component_h: float
    build_per_component_h: float  # construction hours per working component (P20 baseline)
    tryout_h: float             # press / machine tryout and sampling
    mold: bool = False          # cavity tools: polishing and finish matter
    base_share: float | None = None  # tool base share when carriers are not sized (None: default)
    fitting: bool = True        # bench fitting and assembly of several components


EFFORT = {
    # Sheet-metal cutting and forming
    "bending": Effort(0.7, 0.3, 1, 0, base_share=0, fitting=False),
    "punching_blanking": Effort(2, 0.5, 2, 0.8),
    "fine_blanking": Effort(14.5, 2.5, 11, 5),
    "progressive_die_stamping": Effort(29.5, 2, 7.5, 9),
    "stamping": Effort(53, 9, 26.5, 17.5),
    "forming": Effort(12, 4, 16, 6),
    "deep_drawing": Effort(16, 4, 18, 8),
    "sheet_hydroforming": Effort(11, 3, 12.5, 5.5),
    "tube_hydroforming": Effort(14.5, 2.5, 12.5, 5.5),
    "spinning": Effort(0.8, 0.4, 1, 0.4, base_share=0, fitting=False),
    # Casting, forging and extrusion
    "die_casting": Effort(29, 7.5, 19, 11.5, mold=True),
    "metal_molding": Effort(29, 7.5, 19, 11.5, mold=True),
    "sand_casting": Effort(2, 0.6, 2, 0.6, base_share=0.1),
    "investment_casting": Effort(4.5, 1.5, 5.5, 1.5, mold=True, base_share=0.15),
    "closed_die_forging": Effort(4, 1, 4, 1.5),
    "metal_extrusion": Effort(2, 0.5, 1.5, 1, base_share=0.1),
    # Plastics, rubber and composites
    "plastic_injection": Effort(12, 3, 11, 3, mold=True),
    "plastic_molding": Effort(12, 3, 11, 3, mold=True),
    "foaming": Effort(6, 2, 6.5, 2, mold=True),
    "thermoforming": Effort(3, 1.5, 5, 1.5, mold=True),
    "compression_molding": Effort(11, 3, 13, 3.5, mold=True),
    "transfer_molding": Effort(9, 1.5, 4.5, 3, mold=True),
    "blow_molding": Effort(5.5, 1.5, 7, 3, mold=True),
    "rotational_molding": Effort(3.5, 1.5, 4, 1.5, mold=True, base_share=0.1),
    "plastic_extrusion": Effort(4, 1, 4, 2, base_share=0.1),
    "composite_molding": Effort(7, 2.5, 10.5, 2.5, mold=True, base_share=0.1),
    "pultrusion": Effort(6, 1.5, 6, 2, base_share=0.1),
    # Powder processes
    "powder_metallurgy": Effort(10, 1.5, 5.5, 3.5),
    "metal_injection_molding": Effort(32, 6, 22, 12, mold=True),
}

# Construction hours relative to pre-hardened steel: aluminium machines much faster,
# hardened and wear-resistant grades need hard milling, EDM and grinding.
MACHINABILITY = {
    "aluminum_tooling": 0.55,
    "pre_hardened_mold_steel": 1.0,
    "hardened_mold_steel": 1.3,
    "corrosion_resistant_mold_steel": 1.35,
    "cold_work_tool_steel": 1.3,
    "high_wear_cold_work_steel": 1.5,
    "high_toughness_cold_work_steel": 1.4,
    "carbide": 3.0,
}
TOLERANCE = {"standard": 1.0, "precision": 1.2, "high_precision": 1.45}
FINISH = {"standard": 1.0, "high": 1.25, "optical": 1.7}

# Average electrical load while each machine type runs (kW).
MACHINE_KW = {"cnc_3_axis_share": 12, "cnc_5_axis_share": 18, "edm_share": 8, "grinding_share": 10}

STANDARD_PARTS_SHARE = 0.10   # guides, bushes, ejectors, screws, springs
TOOL_BASE_SHARE = 0.25        # mould base / die set when carriers are not sized as blocks
FITTING_BASE_H = 4
FITTING_PER_COMPONENT_H = 2


def effort(process: str) -> Effort:
    return EFFORT.get(process, Effort(16, 4, 16, 6))


CONTINUOUS = {"metal_extrusion", "plastic_extrusion", "pultrusion"}


def part_span(process: str, part) -> float:
    """Size that drives tool effort: the cross-section for extrusion-type dies (cut length is irrelevant)."""
    if process in CONTINUOUS:
        return max(part.width_mm, part.height_mm)
    return max(part.length_mm, part.width_mm)


def size_factor(span_mm: float | None, low: float = 0.6, high: float = 3.0) -> float:
    """Effort grows with the square root of the part span (100 mm reference part = 1)."""
    if not span_mm or span_mm <= 0:
        return 1.0
    return min(high, max(low, (span_mm / 100) ** 0.5))


def build_hours(process: str, family: str | None, tolerance: str, finish: str, span_mm: float | None = None) -> float:
    """Construction hours for one working component."""
    e = effort(process)
    hours = (e.build_per_component_h * MACHINABILITY.get(family or "", 1.0) * TOLERANCE.get(tolerance, 1.0)
             * size_factor(span_mm))
    if e.mold:
        hours *= FINISH.get(finish, 1.0)
    return hours


def machine_hour_rate(assumptions, route: dict) -> float:
    """Toolroom hour: machines on the route plus the attending toolmaker."""
    machine = sum(getattr(assumptions, key.replace("_share", "_rate")) * share for key, share in route.items())
    return machine / assumptions.machine_efficiency + assumptions.assembly_rate / assumptions.operator_efficiency


def energy_cost(assumptions, route: dict, machine_hours: float) -> float:
    kw = sum(MACHINE_KW[key] * share for key, share in route.items())
    return machine_hours * kw * assumptions.electricity_eur_kwh


def tool_level(process: str, working_components: int, has_carriers: bool, tolerance: str,
               working_cost: float, assumptions, sets: int = 1, span_mm: float | None = None) -> dict:
    """Design, tool base, standard parts, assembly and tryout for the whole tool."""
    e = effort(process)
    # Design is done once: identical sets do not add design per component.
    distinct = working_components / max(1, sets)
    design_h = ((e.design_base_h + e.design_per_component_h * distinct) * TOLERANCE.get(tolerance, 1.0)
                * size_factor(span_mm, 0.7, 2.0))
    fitting_h = (FITTING_BASE_H + FITTING_PER_COMPONENT_H * working_components) if working_components and e.fitting else 0
    toolmaker = assumptions.assembly_rate / assumptions.operator_efficiency
    # Tryout: toolmaker plus a production machine, priced at the 3-axis machine rate as a proxy.
    tryout = e.tryout_h * sets * (toolmaker + assumptions.cnc_3_axis_rate)
    base = e.base_share if e.base_share is not None else TOOL_BASE_SHARE
    share = (STANDARD_PARTS_SHARE if e.fitting else 0) + (0 if has_carriers else base)
    return {
        "design_hours": design_h,
        "design_cost": design_h * assumptions.engineering_rate,
        "assembly_tryout_cost": fitting_h * toolmaker + tryout,
        "standard_parts_cost": share * working_cost,
        "standard_parts_note": ("Standard parts (guides, bushes, ejectors, fasteners)" if has_carriers
                                else "Mould base or die set and standard parts"),
    }


def commercial(base_cost: float, assumptions) -> tuple[float, float]:
    """Overhead on the cost base, then the supplier margin on cost plus overhead."""
    overhead = base_cost * assumptions.overhead_rate
    margin = (base_cost + overhead) * assumptions.margin_rate
    return overhead, margin


def commercial_factor(assumptions) -> float:
    return (1 + assumptions.overhead_rate) * (1 + assumptions.margin_rate)
