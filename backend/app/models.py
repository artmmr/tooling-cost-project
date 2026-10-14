from enum import Enum
from typing import Literal

from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


# =========================================================
# Existing calculator enums
# =========================================================

class CycleBand(str, Enum):
    UP_TO_10K = "up_to_10000"
    FROM_10K_TO_100K = "10000_to_100000"
    FROM_100K_TO_250K = "100000_to_250000"


class ProcessType(str, Enum):
    BENDING = "bending"
    METAL_EXTRUSION = "metal_extrusion"
    DIE_CASTING = "die_casting"
    SAND_CASTING = "sand_casting"
    INVESTMENT_CASTING = "investment_casting"
    CLOSED_DIE_FORGING = "closed_die_forging"
    PLASTIC_EXTRUSION = "plastic_extrusion"
    BLOW_MOLDING = "blow_molding"
    COMPRESSION_MOLDING = "compression_molding"
    TRANSFER_MOLDING = "transfer_molding"
    ROTATIONAL_MOLDING = "rotational_molding"
    POWDER_METALLURGY = "powder_metallurgy"
    METAL_INJECTION_MOLDING = "metal_injection_molding"
    COMPOSITE_MOLDING = "composite_molding"
    PULTRUSION = "pultrusion"
    PUNCHING_BLANKING = "punching_blanking"
    FINE_BLANKING = "fine_blanking"
    PROGRESSIVE_DIE_STAMPING = "progressive_die_stamping"
    TUBE_HYDROFORMING = "tube_hydroforming"
    SHEET_HYDROFORMING = "sheet_hydroforming"
    SPINNING = "spinning"

    # Existing API values remain valid and retain their original rules.
    PLASTIC_MOLDING = "plastic_molding"
    PLASTIC_INJECTION = "plastic_injection"
    FOAMING = "foaming"
    THERMOFORMING = "thermoforming"

    METAL_MOLDING = "metal_molding"
    STAMPING = "stamping"
    FORMING = "forming"
    DEEP_DRAWING = "deep_drawing"


# =========================================================
# Recommendation enums
# =========================================================

class WorkpieceMaterial(str, Enum):
    CAST_ALUMINUM = "cast_aluminum"
    CAST_IRON = "cast_iron"
    METAL_POWDER = "metal_powder"
    FIBER_COMPOSITE = "fiber_composite"
    # Plastic materials
    STANDARD_THERMOPLASTIC = (
        "standard_thermoplastic"
    )

    GLASS_FILLED_THERMOPLASTIC = (
        "glass_filled_thermoplastic"
    )

    MINERAL_FILLED_THERMOPLASTIC = (
        "mineral_filled_thermoplastic"
    )

    CORROSIVE_POLYMER = (
        "corrosive_polymer"
    )

    THERMOSET = "thermoset"
    ELASTOMER = "elastomer"

    # Metal materials
    MILD_STEEL = "mild_steel"

    HIGH_STRENGTH_STEEL = (
        "high_strength_steel"
    )

    ADVANCED_HIGH_STRENGTH_STEEL = (
        "advanced_high_strength_steel"
    )

    STAINLESS_STEEL = "stainless_steel"

    ALUMINUM_SHEET = "aluminum_sheet"

    COPPER_BRASS = "copper_brass"

    OTHER = "other"


class ToleranceLevel(str, Enum):
    STANDARD = "standard"
    PRECISION = "precision"
    HIGH_PRECISION = "high_precision"


class SurfaceFinish(str, Enum):
    STANDARD = "standard"
    HIGH = "high"
    OPTICAL = "optical"


# =========================================================
# Geometry
# =========================================================

class PartDimensions(BaseModel):
    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)


# =========================================================
# Country / user cost assumptions
# =========================================================

class CostAssumptions(BaseModel):
    engineering_rate: float = Field(gt=0)
    assembly_rate: float = Field(gt=0)

    cnc_3_axis_rate: float = Field(gt=0)
    cnc_5_axis_rate: float = Field(gt=0)

    edm_rate: float = Field(gt=0)
    grinding_rate: float = Field(gt=0)

    electricity_eur_kwh: float = Field(gt=0)

    machine_efficiency: float = Field(
        gt=0,
        le=1,
    )

    operator_efficiency: float = Field(
        gt=0,
        le=1,
    )

    overhead_rate: float = Field(
        ge=0,
        le=1,
    )

    margin_rate: float = Field(
        ge=0,
        le=1,
    )


# =========================================================
# API request
# =========================================================

class ToolingMaterialAssumptions(BaseModel):
    density_kg_m3: float = Field(gt=0)

    block_price_per_tonne: float = Field(gt=0)

    removal_rate_cm3_min: float = Field(gt=0)

    milling_volume_factor: float = Field(gt=0)

    milling_tool_price: float = Field(ge=0)

    heat_treatment_eur_per_kg: float = Field(ge=0)


class ManufacturingRouteAssumptions(BaseModel):
    cnc_3_axis_share: float = Field(ge=0, le=1)
    cnc_5_axis_share: float = Field(ge=0, le=1)
    edm_share: float = Field(ge=0, le=1)
    grinding_share: float = Field(ge=0, le=1)

class LogisticsAssumptions(BaseModel):
    # Rates are always EUR at the API boundary. Defaults preserve legacy costs.
    road_rate_eur_per_km: float = Field(default=1400 / 250, ge=0, allow_inf_nan=False)
    sea_rate_eur_per_nm: float = Field(default=8000 / 19800 * 1.852, ge=0, allow_inf_nan=False)
    road_load_kg: float = Field(default=18000, gt=0, allow_inf_nan=False)
    sea_load_kg: float = Field(default=27000, gt=0, allow_inf_nan=False)
    road_journeys: int = Field(default=2, ge=1, le=100)
    sea_journeys: int = Field(default=2, ge=1, le=100)
    allocation: Literal["proportional", "whole_load"] = "proportional"


class BlockOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    component_id: str
    pieces: int | None = Field(default=None, ge=1, le=1000)
    stock_form: Literal["Rectangular block", "Round billet"] | None = None
    nominal_length_mm: float | None = Field(default=None, gt=0)
    nominal_width_mm: float | None = Field(default=None, gt=0)
    nominal_depth_mm: float | None = Field(default=None, gt=0)
    enlargement_ratio: float | None = Field(default=None, ge=0, le=1)
    side_reserve_x_mm: float | None = Field(default=None, ge=0)
    side_reserve_y_mm: float | None = Field(default=None, ge=0)
    backing_mm: float | None = Field(default=None, ge=0)
    allowance_mm: float | None = Field(default=None, ge=0)
    rounding_mm: float | None = Field(default=None, gt=0)
    material_family: str | None = None
    tooling_material_assumptions: ToolingMaterialAssumptions | None = None
    manufacturing_route: ManufacturingRouteAssumptions | None = None
    # This workbook contains envelopes, not CAD-derived machining volumes.
    machining_volume_m3: float | None = Field(default=None, ge=0)
    purchased_unit_cost_eur: float | None = Field(default=None, ge=0)
    purchased_unit_weight_kg: float | None = Field(default=None, ge=0)


class CalculationRequest(BaseModel):
    cycle_band: CycleBand = CycleBand.UP_TO_10K
    process: ProcessType
    parts_per_mold: int = Field(ge=1, le=30)
    manufacturing_country: str
    expected_cycles: int = Field(default=10000, gt=0)
    expected_quantity: int | None = Field(default=None, gt=0)
    sizing_mode: Literal["reference", "part_scaled"] = "part_scaled"
    block_overrides: list[BlockOverride] = Field(default_factory=list, max_length=100)
    workpiece_material: WorkpieceMaterial
    material_thickness_mm: float = Field(
        default=1.0,
        gt=0,
    )
    tolerance_level: ToleranceLevel = (
        ToleranceLevel.STANDARD
    )
    surface_finish: SurfaceFinish = (
        SurfaceFinish.STANDARD
    )
    abrasive_material: bool = False
    corrosive_environment: bool = False
    truck_distance_km: float = Field(ge=0)
    sea_distance_km: float = Field(default=0, ge=0)
    sea_distance_nm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    logistics: LogisticsAssumptions = Field(default_factory=LogisticsAssumptions)
    includes_cooling: bool
    part: PartDimensions
    assumptions: CostAssumptions

    tooling_material_family: str | None = None

    tooling_material_assumptions: (
        ToolingMaterialAssumptions | None
    ) = None

    manufacturing_route: (
        ManufacturingRouteAssumptions | None
    ) = None


# =========================================================
# API response
# =========================================================

class ToolingBlockComponentResponse(BaseModel):
    component_id: str = ""
    record_id: str = ""
    component: str
    role: str
    pieces: int
    stock_form: str
    raw_stock: str
    raw_length_mm: float | None = None
    raw_width_mm: float | None = None
    raw_height_mm: float | None = None
    material_note: str
    heating_cooling: str
    assumption: str
    purchased: bool = False
    pieces_per_set: int = 1
    finished_length_mm: float | None = None
    finished_width_mm: float | None = None
    finished_height_mm: float | None = None
    sizing_inputs: dict[str, float] = Field(default_factory=dict)
    raw_volume_m3: float = 0
    finished_volume_m3: float = 0
    machining_volume_m3: float = 0
    machining_basis: str = ""
    weight_kg: float = 0
    material_family: str | None = None
    costing_material: str = ""
    material_assumptions: ToolingMaterialAssumptions | None = None
    manufacturing_route: ManufacturingRouteAssumptions | None = None
    cost_before_commercial: float | None = None
    purchased_unit_cost_eur: float | None = None
    purchased_unit_weight_kg: float | None = None
    modified: bool = False


class CalculationResponse(BaseModel):
    calculation_basis: str = "legacy"
    expected_quantity: int | None = None
    total_machined_blocks: int = 0
    total_purchased_assemblies: int = 0
    grade_candidates: str = ""
    grade_treatment: str = ""
    grade_scope: str = ""
    selection_conditions: str = ""
    tooling_scope: str = ""
    estimate_warnings: list[str] = Field(default_factory=list)
    purchased_assemblies_cost: float = 0
    estimate_complete: bool = True
    final_markup: float = 0
    cost_model_note: str = ""
    recommendation_confidence_explanation: str = ""
    tooling_material: str

    gross_length_mm: float
    gross_width_mm: float
    gross_height_mm: float

    tooling_weight_kg: float
    tooling_quantity_band: str = ""
    tooling_concept: str = ""
    tooling_sizing_basis: str = ""
    tooling_blocks: list[ToolingBlockComponentResponse] = Field(default_factory=list)

    outside_machining_volume_m3: float
    inside_machining_volume_m3: float

    milling_time_index: int
    removed_volume_time_min: float

    material_cost: float
    transformation_cost: float

    outside_machining_cost: float
    inside_machining_cost: float

    milling_tool_cost: float
    cooling_cost: float

    margin: float
    handling_cost: float
    road_transport_cost: float = 0
    sea_transport_cost: float = 0
    transport_cost: float
    heat_treatment_cost: float

    total_price: float

    # Recommendation output
    recommended_material: str

    recommended_material_family: str

    recommendation_confidence: str

    failure_modes: list[str]

    recommendation_reasons: list[str]

    recommended_operations: list[str]



