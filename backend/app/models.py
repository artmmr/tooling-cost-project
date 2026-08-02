from enum import Enum

from pydantic import BaseModel, Field


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


class PartDimensions(BaseModel):
    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)


class CalculationRequest(BaseModel):
    cycle_band: CycleBand
    process: ProcessType
    parts_per_mold: int = Field(ge=1, le=30)

    truck_distance_km: float = Field(ge=0)
    sea_distance_km: float = Field(ge=0)

    includes_cooling: bool

    part: PartDimensions


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

    total_price: float