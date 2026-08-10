from enum import Enum

from pydantic import BaseModel, Field


# =========================================================
# Existing calculator enums
# =========================================================

class CycleBand(str, Enum):
    UP_TO_10K = "up_to_10000"
    FROM_10K_TO_100K = "10000_to_100000"
    FROM_100K_TO_250K = "100000_to_250000"


class ProcessType(str, Enum):
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

class CalculationRequest(BaseModel):
    cycle_band: CycleBand
    process: ProcessType
    parts_per_mold: int = Field(ge=1, le=30)
    manufacturing_country: str
    expected_cycles: int = Field(gt=0)
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
    sea_distance_km: float = Field(ge=0)
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

class CalculationResponse(BaseModel):
    tooling_material: str

    gross_length_mm: float
    gross_width_mm: float
    gross_height_mm: float

    tooling_weight_kg: float

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