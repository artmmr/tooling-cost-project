from math import ceil

from app.constants import (
    MACHINE_RATE_PER_HOUR,
    MATERIALS,
    OPERATOR_RATE_PER_HOUR,
    ROAD_COST_PER_100_KM,
    ROAD_LOAD_KG,
    SEA_COST_PER_1000_KM,
    SEA_LOAD_KG,
)
from app.models import (
    CalculationRequest,
    CalculationResponse,
)


CYCLE_CATEGORY = {
    "up_to_10000": 1,
    "10000_to_100000": 2,
    "100000_to_250000": 3,
}


PROCESS_CATEGORY = {
    "plastic_molding": 1,
    "plastic_injection": 1,
    "foaming": 1,
    "thermoforming": 1,
    "metal_molding": 2,
    "stamping": 2,
    "forming": 2,
    "deep_drawing": 2,
}


def select_material(
    cycle_category: int,
    process_category: int,
) -> str:
    material_matrix = {
        (1, 1): "aluminum",
        (1, 2): "aluminum",
        (1, 3): "steel",
        (2, 1): "aluminum",
        (2, 2): "aluminum",
        (2, 3): "hard_steel",
        (3, 1): "steel",
        (3, 2): "hard_steel",
        (3, 3): "hard_steel",
    }

    return material_matrix.get(
        (cycle_category, process_category),
        "aluminum",
    )


def calculate_cooling_cost(
    tooling_weight_kg: float,
    includes_cooling: bool,
) -> float:
    if not includes_cooling:
        return 0

    # These ranges need to be confirmed against the workbook.
    # The original JavaScript contains overlapping conditions.
    if tooling_weight_kg < 500:
        return 5000

    if tooling_weight_kg < 1000:
        return 7500

    if tooling_weight_kg < 2000:
        return 10000

    if tooling_weight_kg < 3000:
        return 15000

    if tooling_weight_kg < 50_000:
        return 20000

    return 0


def calculate(
    request: CalculationRequest,
) -> CalculationResponse:
    cycle_category = CYCLE_CATEGORY[
        request.cycle_band.value
    ]

    process_category = PROCESS_CATEGORY[
        request.process.value
    ]

    material_key = select_material(
        cycle_category=cycle_category,
        process_category=process_category,
    )

    material = MATERIALS[material_key]

    parts_per_mold = request.parts_per_mold

    part_length = request.part.length_mm
    part_width = request.part.width_mm
    part_height = request.part.height_mm

    gross_length_mm = (
        part_length * parts_per_mold
        + 150 * 2
    )

    gross_width_mm = (
        part_width
        + 150 * 2
    )

    gross_height_mm = (
        part_height / 2
        * 3
        * 2
    )

    gross_volume_m3 = (
        gross_length_mm
        * gross_width_mm
        * gross_height_mm
        / 1_000_000_000
    )

    tooling_weight_kg = (
        gross_volume_m3
        * material.density_kg_m3
    )

    outside_machining_volume_m3 = (
        (
            (gross_length_mm + 5)
            * (gross_width_mm + 5)
            * (gross_height_mm + 5)
        )
        - (
            gross_length_mm
            * gross_width_mm
            * gross_height_mm
        )
    ) / 1_000_000_000

    inside_machining_volume_m3 = (
        part_length
        * part_width
        * part_height
        / 1_000_000_000
        * parts_per_mold
    )

    total_machining_volume_m3 = (
        inside_machining_volume_m3
        + outside_machining_volume_m3
    )

    milling_time_index = ceil(
        total_machining_volume_m3
        / material.milling_volume_factor
    )

    removed_volume_time_min = (
        (
            inside_machining_volume_m3
            * 1_000_000
            / material.removal_rate_cm3_min
        )
        * parts_per_mold
        + (
            outside_machining_volume_m3
            * 1_000_000
            / material.removal_rate_cm3_min
        )
    )

    hourly_cost_per_minute = (
        MACHINE_RATE_PER_HOUR
        + OPERATOR_RATE_PER_HOUR
    ) / 60

    material_cost = (
        tooling_weight_kg
        * (
            material.block_price_per_tonne
            / 1000
        )
        * 2
        * 1.4
    )

    transformation_cost = (
        material_cost * 1.5
        - material_cost
    )

    outside_machining_cost = (
        outside_machining_volume_m3
        * 1_000_000
        / material.removal_rate_cm3_min
        * hourly_cost_per_minute
        * 1.25
    )

    inside_machining_cost = (
        inside_machining_volume_m3
        * 1_000_000
        / material.removal_rate_cm3_min
        * hourly_cost_per_minute
        * 1.25
        * parts_per_mold
    )

    milling_tool_cost = (
        milling_time_index
        * material.milling_tool_price
    )

    cooling_cost = calculate_cooling_cost(
        tooling_weight_kg=tooling_weight_kg,
        includes_cooling=request.includes_cooling,
    )

    base_cost = (
        material_cost
        + transformation_cost
        + outside_machining_cost
        + inside_machining_cost
        + milling_tool_cost
        + cooling_cost
    )

    margin = (
        base_cost * 1.2
        - base_cost
    )

    handling_cost = (
        base_cost * 1.05
        - base_cost
    )

    road_transport_cost = (
        request.truck_distance_km
        / 100
        * ROAD_COST_PER_100_KM
        * (
            tooling_weight_kg
            / ROAD_LOAD_KG
        )
        * 2
    )

    sea_transport_cost = (
        request.sea_distance_km
        / 1000
        * SEA_COST_PER_1000_KM
        * (
            tooling_weight_kg
            / SEA_LOAD_KG
        )
        * 2
    )

    transport_cost = (
        road_transport_cost
        + sea_transport_cost
    )

    total_before_final_markup = (
        base_cost
        + margin
        + handling_cost
        + transport_cost
    )

    total_price = (
        total_before_final_markup
        * 1.1
    )

    return CalculationResponse(
        tooling_material=material.name,
        gross_length_mm=gross_length_mm,
        gross_width_mm=gross_width_mm,
        gross_height_mm=gross_height_mm,
        tooling_weight_kg=tooling_weight_kg,
        outside_machining_volume_m3=(
            outside_machining_volume_m3
        ),
        inside_machining_volume_m3=(
            inside_machining_volume_m3
        ),
        milling_time_index=milling_time_index,
        removed_volume_time_min=(
            removed_volume_time_min
        ),
        material_cost=material_cost,
        transformation_cost=transformation_cost,
        outside_machining_cost=(
            outside_machining_cost
        ),
        inside_machining_cost=(
            inside_machining_cost
        ),
        milling_tool_cost=milling_tool_cost,
        cooling_cost=cooling_cost,
        margin=margin,
        handling_cost=handling_cost,
        transport_cost=transport_cost,
        total_price=total_price,
    )