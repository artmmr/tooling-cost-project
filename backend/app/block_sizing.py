from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class BlockSizingRule:
    component: str
    role: str
    pieces_per_tool_set: int
    stock_form: str
    reference_part: str
    material_note: str
    heating_cooling: str
    reference_l_mm: float
    reference_w_mm: float
    reference_h_mm: float
    envelope_l_mm: float
    envelope_w_mm: float
    envelope_h_mm: float
    enlargement: float
    reserve_x_mm: float
    reserve_y_mm: float
    backing_mm: float
    allowance_mm: float
    rounding_increment_mm: float
    assumption: str


@dataclass(frozen=True)
class ToolingBlockComponent:
    component: str
    role: str
    pieces: int
    stock_form: str
    material_note: str
    heating_cooling: str
    raw_length_mm: float
    raw_width_mm: float | None
    raw_height_mm: float
    finished_length_mm: float
    finished_width_mm: float | None
    finished_height_mm: float
    raw_volume_m3: float
    finished_volume_m3: float
    working_volume_m3: float
    assumption: str

    @property
    def raw_stock_label(self) -> str:
        if self.stock_form == "Round billet":
            return f"Ø{self.raw_length_mm:.0f} × {self.raw_height_mm:.0f} mm"

        return (
            f"{self.raw_length_mm:.0f} × "
            f"{(self.raw_width_mm or 0):.0f} × "
            f"{self.raw_height_mm:.0f} mm"
        )


@dataclass(frozen=True)
class ToolingSizingResult:
    quantity_band: str
    tooling_concept: str
    sizing_basis: str
    components: list[ToolingBlockComponent]
    gross_length_mm: float
    gross_width_mm: float
    gross_height_mm: float
    raw_volume_m3: float
    finished_volume_m3: float
    working_volume_m3: float


def _round_up(value: float, increment: float) -> float:
    return ceil(value / increment) * increment


def _quantity_band(quantity: int) -> str:
    if quantity <= 20:
        return "1-20"
    if quantity <= 100:
        return "21-100"
    if quantity <= 1_000:
        return "101-1,000"
    if quantity <= 10_000:
        return "1,001-10,000"
    if quantity <= 100_000:
        return "10,001-100,000"
    return "Above 100,000"


TOOLING_CONCEPTS = {
    "plastic_injection": {
        "1-20": "Single-cavity insert in a reusable base",
        "21-100": "Single-cavity insert in a reusable base",
        "101-1,000": "Dedicated cavity and core inserts",
        "1,001-10,000": "Production mold with cooling and slides as needed",
        "10,001-100,000": "Optimized production mold with replaceable inserts",
        "Above 100,000": "Durable multi-cavity mold with planned insert replacement",
    },
    "plastic_molding": {
        "1-20": "Simple compression mold set",
        "21-100": "Simple compression mold set",
        "101-1,000": "Dedicated mold set",
        "1,001-10,000": "Production mold with heating or cooling provisions",
        "10,001-100,000": "Production mold with replaceable wear areas",
        "Above 100,000": "Automated production mold with planned replacement inserts",
    },
    "foaming": {
        "1-20": "Prototype aluminum foam mold",
        "21-100": "Simple aluminum foam mold",
        "101-1,000": "Dedicated foam mold",
        "1,001-10,000": "Production foam mold with venting and temperature control",
        "10,001-100,000": "Production foam mold with replaceable wear areas",
        "Above 100,000": "Automated production foam mold",
    },
    "thermoforming": {
        "1-20": "Prototype forming tool",
        "21-100": "Simple forming tool",
        "101-1,000": "Dedicated forming tool",
        "1,001-10,000": "Production forming tool with trim support",
        "10,001-100,000": "Production tool with replaceable trim details",
        "Above 100,000": "Automated production forming and trim tooling",
    },
    "metal_molding": {
        "1-20": "Single-cavity insert in reusable base",
        "21-100": "Single-cavity insert in reusable base",
        "101-1,000": "Dedicated single-cavity die",
        "1,001-10,000": "Production die with cooling and slides",
        "10,001-100,000": "Optimized production die",
        "Above 100,000": "Replaceable cavity inserts; multiple cavities if justified",
    },
    "stamping": {
        "1-20": "Simple dedicated die set",
        "21-100": "Simple progressive die inserts",
        "101-1,000": "Dedicated progressive die",
        "1,001-10,000": "Production progressive die",
        "10,001-100,000": "Progressive die with replaceable wear inserts",
        "Above 100,000": "Automated progressive die with planned insert replacement",
    },
    "forming": {
        "1-20": "Standard or simple dedicated forming tools",
        "21-100": "Standard or simple dedicated forming tools",
        "101-1,000": "Dedicated profile tools",
        "1,001-10,000": "Dedicated production forming tools",
        "10,001-100,000": "Replaceable working inserts",
        "Above 100,000": "Automated tooling with wear inserts",
    },
    "deep_drawing": {
        "1-20": "Simple punch and die set",
        "21-100": "Dedicated punch and die set",
        "101-1,000": "Dedicated draw die with binder",
        "1,001-10,000": "Production draw die with wear inserts",
        "10,001-100,000": "Optimized draw die with replaceable details",
        "Above 100,000": "Automated draw die set with planned replacement details",
    },
}


RULES = {
    "plastic_injection": [
        BlockSizingRule(
            component="Cavity insert",
            role="FEMALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Block with holes",
            material_note="P20 / H13 / corrosion-resistant mold steel",
            heating_cooling="Mold temperature control; cooling layout must be checked in CAD",
            reference_l_mm=60,
            reference_w_mm=40,
            reference_h_mm=15,
            envelope_l_mm=60,
            envelope_w_mm=40,
            envelope_h_mm=7.5,
            enlargement=0.005,
            reserve_x_mm=30,
            reserve_y_mm=30,
            backing_mm=30,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Transfer-molding style split cavity used as the closest current-process proxy.",
        ),
        BlockSizingRule(
            component="Core insert",
            role="MALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Block with holes",
            material_note="P20 / H13 / corrosion-resistant mold steel",
            heating_cooling="Mold temperature control; cooling layout must be checked in CAD",
            reference_l_mm=60,
            reference_w_mm=40,
            reference_h_mm=15,
            envelope_l_mm=60,
            envelope_w_mm=40,
            envelope_h_mm=7.5,
            enlargement=0.005,
            reserve_x_mm=25,
            reserve_y_mm=25,
            backing_mm=30,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Matched core half; exact parting line, ejectors and runners are not included.",
        ),
    ],
    "plastic_molding": [
        BlockSizingRule(
            component="Cavity half",
            role="FEMALE",
            pieces_per_tool_set=2,
            stock_form="Rectangular block",
            reference_part="Open hemisphere",
            material_note="P20 / aluminum / corrosion-resistant mold steel",
            heating_cooling="Heating or cooling depends on polymer and cycle time",
            reference_l_mm=100,
            reference_w_mm=100,
            reference_h_mm=50,
            envelope_l_mm=100,
            envelope_w_mm=100,
            envelope_h_mm=25,
            enlargement=0.006,
            reserve_x_mm=35,
            reserve_y_mm=35,
            backing_mm=35,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Two female halves are assumed for a split mold body.",
        ),
    ],
    "foaming": [
        BlockSizingRule(
            component="Foam mold half",
            role="FEMALE",
            pieces_per_tool_set=2,
            stock_form="Rectangular block",
            reference_part="Foamed part envelope",
            material_note="Aluminum tooling plate or cast aluminum",
            heating_cooling="Vent and temperature-control details are process-specific",
            reference_l_mm=100,
            reference_w_mm=100,
            reference_h_mm=50,
            envelope_l_mm=100,
            envelope_w_mm=100,
            envelope_h_mm=25,
            enlargement=0.01,
            reserve_x_mm=35,
            reserve_y_mm=35,
            backing_mm=30,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Foam tooling is approximated as a split female mold.",
        ),
    ],
    "thermoforming": [
        BlockSizingRule(
            component="Forming plug",
            role="MALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Shallow formed part",
            material_note="Aluminum / tooling board depending on volume",
            heating_cooling="Vacuum, venting and trim details are not included",
            reference_l_mm=100,
            reference_w_mm=80,
            reference_h_mm=25,
            envelope_l_mm=100,
            envelope_w_mm=80,
            envelope_h_mm=25,
            enlargement=0,
            reserve_x_mm=25,
            reserve_y_mm=25,
            backing_mm=25,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Thermoforming is approximated as a male forming block.",
        ),
    ],
    "metal_molding": [
        BlockSizingRule(
            component="Outer cavity insert",
            role="FEMALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Hemispherical shell",
            material_note="H13 / H13 ESR / Dievar depending on volume",
            heating_cooling="Die preheat and temperature-control circuits are expected",
            reference_l_mm=100,
            reference_w_mm=100,
            reference_h_mm=50,
            envelope_l_mm=100,
            envelope_w_mm=100,
            envelope_h_mm=50,
            enlargement=0.006,
            reserve_x_mm=40,
            reserve_y_mm=40,
            backing_mm=40,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Die-casting cavity block proxy; runners, slides and ejectors are not included.",
        ),
        BlockSizingRule(
            component="Inner core insert",
            role="MALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Hemispherical shell",
            material_note="H13 / H13 ESR / Dievar depending on volume",
            heating_cooling="Die preheat and temperature-control circuits are expected",
            reference_l_mm=100,
            reference_w_mm=100,
            reference_h_mm=50,
            envelope_l_mm=94,
            envelope_w_mm=94,
            envelope_h_mm=47,
            enlargement=0.006,
            reserve_x_mm=35,
            reserve_y_mm=35,
            backing_mm=45,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Core size is reduced for wall thickness in the reference geometry.",
        ),
    ],
    "stamping": [
        BlockSizingRule(
            component="Punch insert",
            role="MALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Pierced U-bracket",
            material_note="A2 / D2 / premium cold-work steel depending on wear",
            heating_cooling="Cold stamping; normally no active cooling",
            reference_l_mm=60,
            reference_w_mm=40,
            reference_h_mm=20,
            envelope_l_mm=60,
            envelope_w_mm=40,
            envelope_h_mm=20,
            enlargement=0,
            reserve_x_mm=15,
            reserve_y_mm=15,
            backing_mm=25,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="One insert per assumed station; strip layout and carrier are not included.",
        ),
        BlockSizingRule(
            component="Die insert",
            role="FEMALE DIE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Pierced U-bracket",
            material_note="A2 / D2 / premium cold-work steel depending on wear",
            heating_cooling="Cold stamping; normally no active cooling",
            reference_l_mm=60,
            reference_w_mm=40,
            reference_h_mm=20,
            envelope_l_mm=60,
            envelope_w_mm=40,
            envelope_h_mm=20,
            enlargement=0,
            reserve_x_mm=20,
            reserve_y_mm=20,
            backing_mm=35,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Die insert only; shoe plates, guides, springs and feeders are separate.",
        ),
    ],
    "forming": [
        BlockSizingRule(
            component="Bending punch",
            role="MALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="L-bracket",
            material_note="42CrMo4 / A2 / D2 depending on wear",
            heating_cooling="Cold process; normally no active cooling",
            reference_l_mm=100,
            reference_w_mm=50,
            reference_h_mm=50,
            envelope_l_mm=100,
            envelope_w_mm=20,
            envelope_h_mm=60,
            enlargement=0,
            reserve_x_mm=5,
            reserve_y_mm=5,
            backing_mm=20,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Press-brake punch-body section; holder interface is not fully modeled.",
        ),
        BlockSizingRule(
            component="V-die",
            role="FEMALE DIE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="L-bracket",
            material_note="42CrMo4 / A2 / D2 depending on wear",
            heating_cooling="Cold process; normally no active cooling",
            reference_l_mm=100,
            reference_w_mm=50,
            reference_h_mm=50,
            envelope_l_mm=100,
            envelope_w_mm=50,
            envelope_h_mm=40,
            enlargement=0,
            reserve_x_mm=10,
            reserve_y_mm=10,
            backing_mm=25,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="V-die block proxy; opening angle and press capacity require validation.",
        ),
    ],
    "deep_drawing": [
        BlockSizingRule(
            component="Drawing punch",
            role="MALE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Shallow drawn cup",
            material_note="A2 / D2 / coated cold-work steel depending on wear",
            heating_cooling="Cold drawing; lubrication and blank holder design are separate",
            reference_l_mm=100,
            reference_w_mm=80,
            reference_h_mm=25,
            envelope_l_mm=98,
            envelope_w_mm=78,
            envelope_h_mm=24,
            enlargement=0,
            reserve_x_mm=20,
            reserve_y_mm=20,
            backing_mm=35,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Approximate inside cup dimensions before springback and radius validation.",
        ),
        BlockSizingRule(
            component="Drawing die",
            role="FEMALE DIE",
            pieces_per_tool_set=1,
            stock_form="Rectangular block",
            reference_part="Shallow drawn cup",
            material_note="A2 / D2 / coated cold-work steel depending on wear",
            heating_cooling="Cold drawing; lubrication and blank holder design are separate",
            reference_l_mm=100,
            reference_w_mm=80,
            reference_h_mm=25,
            envelope_l_mm=100,
            envelope_w_mm=80,
            envelope_h_mm=25,
            enlargement=0,
            reserve_x_mm=30,
            reserve_y_mm=30,
            backing_mm=40,
            allowance_mm=3,
            rounding_increment_mm=5,
            assumption="Die block proxy; binder, draw beads and force calculations are not included.",
        ),
    ],
}


def _scaled(value: float, source: float, target: float) -> float:
    if source <= 0:
        return value

    return value * target / source


def _build_component(
    rule: BlockSizingRule,
    part_length_mm: float,
    part_width_mm: float,
    part_height_mm: float,
    parts_per_tool: int,
) -> ToolingBlockComponent:
    cavity_span = max(1, parts_per_tool)
    envelope_l = _scaled(
        rule.envelope_l_mm,
        rule.reference_l_mm,
        part_length_mm,
    ) * cavity_span
    envelope_w = _scaled(
        rule.envelope_w_mm,
        rule.reference_w_mm,
        part_width_mm,
    )
    envelope_h = _scaled(
        rule.envelope_h_mm,
        rule.reference_h_mm,
        part_height_mm,
    )

    finished_l = envelope_l * (1 + rule.enlargement) + 2 * rule.reserve_x_mm
    finished_h = envelope_h * (1 + rule.enlargement) + rule.backing_mm

    if rule.stock_form == "Round billet":
        finished_w = None
        raw_l = _round_up(finished_l + 2 * rule.allowance_mm, rule.rounding_increment_mm)
        raw_w = None
        raw_h = _round_up(finished_h + 2 * rule.allowance_mm, rule.rounding_increment_mm)
        raw_volume = 3.141592653589793 * (raw_l / 2) ** 2 * raw_h / 1_000_000_000
        finished_volume = 3.141592653589793 * (finished_l / 2) ** 2 * finished_h / 1_000_000_000
    else:
        finished_w = envelope_w * (1 + rule.enlargement) + 2 * rule.reserve_y_mm
        raw_l = _round_up(finished_l + 2 * rule.allowance_mm, rule.rounding_increment_mm)
        raw_w = _round_up(finished_w + 2 * rule.allowance_mm, rule.rounding_increment_mm)
        raw_h = _round_up(finished_h + 2 * rule.allowance_mm, rule.rounding_increment_mm)
        raw_volume = raw_l * raw_w * raw_h / 1_000_000_000
        finished_volume = finished_l * finished_w * finished_h / 1_000_000_000

    working_volume = envelope_l * envelope_w * envelope_h / 1_000_000_000
    pieces = rule.pieces_per_tool_set

    return ToolingBlockComponent(
        component=rule.component,
        role=rule.role,
        pieces=pieces,
        stock_form=rule.stock_form,
        material_note=rule.material_note,
        heating_cooling=rule.heating_cooling,
        raw_length_mm=raw_l,
        raw_width_mm=raw_w,
        raw_height_mm=raw_h,
        finished_length_mm=finished_l,
        finished_width_mm=finished_w,
        finished_height_mm=finished_h,
        raw_volume_m3=raw_volume * pieces,
        finished_volume_m3=finished_volume * pieces,
        working_volume_m3=working_volume * pieces,
        assumption=rule.assumption,
    )


def build_tooling_sizing(
    process: str,
    expected_quantity: int,
    part_length_mm: float,
    part_width_mm: float,
    part_height_mm: float,
    parts_per_tool: int,
) -> ToolingSizingResult:
    rules = RULES[process]
    quantity_band = _quantity_band(expected_quantity)
    tooling_concept = TOOLING_CONCEPTS[process][quantity_band]
    components = [
        _build_component(
            rule=rule,
            part_length_mm=part_length_mm,
            part_width_mm=part_width_mm,
            part_height_mm=part_height_mm,
            parts_per_tool=parts_per_tool,
        )
        for rule in rules
    ]

    raw_volume = sum(component.raw_volume_m3 for component in components)
    finished_volume = sum(component.finished_volume_m3 for component in components)
    working_volume = sum(component.working_volume_m3 for component in components)
    gross_width = max((component.raw_width_mm or component.raw_length_mm) for component in components)

    return ToolingSizingResult(
        quantity_band=quantity_band,
        tooling_concept=tooling_concept,
        sizing_basis=(
            "Block size is derived from the part envelope, number of parts per tool, "
            "tool enlargement, side reserve, backing reserve, machining allowance "
            "and stock rounding. It covers working blocks, not every holder, guide, "
            "ejector, runner, heater or machine-interface detail."
        ),
        components=components,
        gross_length_mm=max(component.raw_length_mm for component in components),
        gross_width_mm=gross_width,
        gross_height_mm=max(component.raw_height_mm for component in components),
        raw_volume_m3=raw_volume,
        finished_volume_m3=finished_volume,
        working_volume_m3=working_volume,
    )
