from math import ceil

from app.recommendation import recommend_tooling

from app.constants import (
    ROAD_COST_PER_100_KM,
    ROAD_LOAD_KG,
    SEA_COST_PER_1000_KM,
    SEA_LOAD_KG,
)

from app.tooling_materials import (
    TOOLING_MATERIALS,
)

from app.models import (
    CalculationRequest,
    CalculationResponse,
)


# =========================================================
# Cooling
# =========================================================

def calculate_cooling_cost(
    tooling_weight_kg: float,
    includes_cooling: bool,
) -> float:
    if not includes_cooling:
        return 0.0

    # Current benchmark ranges.
    #
    # These should eventually be validated
    # against real tooling quotations.

    if tooling_weight_kg < 500:
        return 5000.0

    if tooling_weight_kg < 1000:
        return 7500.0

    if tooling_weight_kg < 2000:
        return 10000.0

    if tooling_weight_kg < 3000:
        return 15000.0

    if tooling_weight_kg < 50_000:
        return 20000.0

    return 0.0


# =========================================================
# Manufacturing route validation
# =========================================================

def validate_route(
    cnc_3_axis_share: float,
    cnc_5_axis_share: float,
    edm_share: float,
    grinding_share: float,
) -> None:
    values = [
        cnc_3_axis_share,
        cnc_5_axis_share,
        edm_share,
        grinding_share,
    ]

    for value in values:
        if value < 0 or value > 1:
            raise ValueError(
                "Manufacturing route shares must "
                "be between 0 and 1."
            )

    total = sum(values)

    if abs(total - 1.0) > 0.001:
        raise ValueError(
            "Manufacturing route allocation "
            f"must equal 100%. Current total: "
            f"{total * 100:.1f}%."
        )


# =========================================================
# Main calculation
# =========================================================

def calculate(
    request: CalculationRequest,
) -> CalculationResponse:

    # ---------------------------------------------------------
    # 1. Recommend tooling material
    # ---------------------------------------------------------

    recommendation = recommend_tooling(
        request
    )

    recommended_family = (
        recommendation.material_family
    )

    if (
        recommended_family
        not in TOOLING_MATERIALS
    ):
        raise ValueError(
            "Recommended tooling material "
            f"'{recommended_family}' "
            "does not have a material profile."
        )

    recommended_profile = (
        TOOLING_MATERIALS[
            recommended_family
        ]
    )


    # ---------------------------------------------------------
    # 2. Decide whether frontend overrides are valid
    # ---------------------------------------------------------
    #
    # Important:
    #
    # The frontend may still contain tooling assumptions from
    # the PREVIOUS recommendation if the user changes process,
    # material, cycles, etc.
    #
    # Therefore we only accept submitted tooling overrides if
    # their material family matches the recommendation generated
    # for THIS request.
    #
    # Otherwise we fall back to the newly recommended defaults.

    use_user_tooling_override = (
        request.tooling_material_family
        == recommended_family
        and request.tooling_material_assumptions
        is not None
    )

    use_user_route_override = (
        request.tooling_material_family
        == recommended_family
        and request.manufacturing_route
        is not None
    )


    # ---------------------------------------------------------
    # 3. Final tooling material assumptions
    # ---------------------------------------------------------

    if use_user_tooling_override:
        tooling_assumptions = (
            request.tooling_material_assumptions
        )

        density_kg_m3 = (
            tooling_assumptions.density_kg_m3
        )

        block_price_per_tonne = (
            tooling_assumptions.block_price_per_tonne
        )

        removal_rate_cm3_min = (
            tooling_assumptions.removal_rate_cm3_min
        )

        milling_volume_factor = (
            tooling_assumptions.milling_volume_factor
        )

        milling_tool_price = (
            tooling_assumptions.milling_tool_price
        )

        heat_treatment_eur_per_kg = (
            tooling_assumptions
            .heat_treatment_eur_per_kg
        )

    else:
        density_kg_m3 = (
            recommended_profile.density_kg_m3
        )

        block_price_per_tonne = (
            recommended_profile
            .block_price_per_tonne
        )

        removal_rate_cm3_min = (
            recommended_profile
            .removal_rate_cm3_min
        )

        milling_volume_factor = (
            recommended_profile
            .milling_volume_factor
        )

        milling_tool_price = (
            recommended_profile
            .milling_tool_price
        )

        heat_treatment_eur_per_kg = (
            recommended_profile
            .heat_treatment_eur_per_kg
        )


    # ---------------------------------------------------------
    # 4. Final manufacturing route
    # ---------------------------------------------------------

    if use_user_route_override:
        route = (
            request.manufacturing_route
        )

        cnc_3_axis_share = (
            route.cnc_3_axis_share
        )

        cnc_5_axis_share = (
            route.cnc_5_axis_share
        )

        edm_share = (
            route.edm_share
        )

        grinding_share = (
            route.grinding_share
        )

    else:
        default_route = (
            recommended_profile.route
        )

        cnc_3_axis_share = (
            default_route.cnc_3_axis_share
        )

        cnc_5_axis_share = (
            default_route.cnc_5_axis_share
        )

        edm_share = (
            default_route.edm_share
        )

        grinding_share = (
            default_route.grinding_share
        )


    validate_route(
        cnc_3_axis_share=(
            cnc_3_axis_share
        ),
        cnc_5_axis_share=(
            cnc_5_axis_share
        ),
        edm_share=(
            edm_share
        ),
        grinding_share=(
            grinding_share
        ),
    )


    # ---------------------------------------------------------
    # 5. Input values
    # ---------------------------------------------------------

    parts_per_mold = (
        request.parts_per_mold
    )

    part_length = (
        request.part.length_mm
    )

    part_width = (
        request.part.width_mm
    )

    part_height = (
        request.part.height_mm
    )


    # ---------------------------------------------------------
    # 6. Gross tooling dimensions
    # ---------------------------------------------------------

    gross_length_mm = (
        part_length
        * parts_per_mold
        + 150 * 2
    )

    gross_width_mm = (
        part_width
        + 150 * 2
    )

    gross_height_mm = (
        part_height
        / 2
        * 3
        * 2
    )


    # ---------------------------------------------------------
    # 7. Tooling volume and weight
    # ---------------------------------------------------------

    gross_volume_m3 = (
        gross_length_mm
        * gross_width_mm
        * gross_height_mm
        / 1_000_000_000
    )

    tooling_weight_kg = (
        gross_volume_m3
        * density_kg_m3
    )


    # ---------------------------------------------------------
    # 8. Machining volumes
    # ---------------------------------------------------------

    outside_machining_volume_m3 = (
        (
            (
                gross_length_mm + 5
            )
            * (
                gross_width_mm + 5
            )
            * (
                gross_height_mm + 5
            )
        )
        -
        (
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


    # ---------------------------------------------------------
    # 9. Milling tool consumption
    # ---------------------------------------------------------

    milling_time_index = ceil(
        total_machining_volume_m3
        / milling_volume_factor
    )


    # ---------------------------------------------------------
    # 10. Removed-volume machining time
    # ---------------------------------------------------------
    #
    # NOTE:
    #
    # This intentionally preserves the existing workbook
    # behavior.
    #
    # inside_machining_volume_m3 already includes
    # parts_per_mold, and this formula multiplies it by
    # parts_per_mold again.
    #
    # We should validate this against the Excel model later
    # before changing it.

    removed_volume_time_min = (
        (
            inside_machining_volume_m3
            * 1_000_000
            / removal_rate_cm3_min
        )
        * parts_per_mold
        +
        (
            outside_machining_volume_m3
            * 1_000_000
            / removal_rate_cm3_min
        )
    )


    # ---------------------------------------------------------
    # 11. Weighted manufacturing machine rate
    # ---------------------------------------------------------
    #
    # Route example:
    #
    # 35% CNC 3-axis
    # 20% CNC 5-axis
    # 25% EDM
    # 20% Grinding
    #
    # The result is a weighted benchmark hourly machine rate.

    machine_rate_per_hour = (
        request.assumptions.cnc_3_axis_rate
        * cnc_3_axis_share
        +
        request.assumptions.cnc_5_axis_rate
        * cnc_5_axis_share
        +
        request.assumptions.edm_rate
        * edm_share
        +
        request.assumptions.grinding_rate
        * grinding_share
    )


    operator_rate_per_hour = (
        request.assumptions.assembly_rate
    )


    # ---------------------------------------------------------
    # 12. Efficiency
    # ---------------------------------------------------------
    #
    # Example:
    #
    # €100/h machine at 80% efficiency
    # = €125 per productive hour.

    effective_machine_rate_per_hour = (
        machine_rate_per_hour
        / request.assumptions.machine_efficiency
    )

    effective_operator_rate_per_hour = (
        operator_rate_per_hour
        / request.assumptions.operator_efficiency
    )


    hourly_cost_per_minute = (
        effective_machine_rate_per_hour
        + effective_operator_rate_per_hour
    ) / 60


    # ---------------------------------------------------------
    # 13. Tooling material cost
    # ---------------------------------------------------------
    #
    # Existing workbook factors are retained:
    #
    # ×2
    # ×1.4

    material_cost = (
        tooling_weight_kg
        * (
            block_price_per_tonne
            / 1000
        )
        * 2
        * 1.4
    )


    # ---------------------------------------------------------
    # 14. Raw material transformation
    # ---------------------------------------------------------

    transformation_cost = (
        material_cost * 1.5
        - material_cost
    )


    # ---------------------------------------------------------
    # 15. Outside machining cost
    # ---------------------------------------------------------

    outside_machining_cost = (
        outside_machining_volume_m3
        * 1_000_000
        / removal_rate_cm3_min
        * hourly_cost_per_minute
        * 1.25
    )


    # ---------------------------------------------------------
    # 16. Inside machining cost
    # ---------------------------------------------------------
    #
    # This also intentionally preserves the current workbook
    # double parts_per_mold multiplication until we validate it.

    inside_machining_cost = (
        inside_machining_volume_m3
        * 1_000_000
        / removal_rate_cm3_min
        * hourly_cost_per_minute
        * 1.25
        * parts_per_mold
    )


    # ---------------------------------------------------------
    # 17. Milling tool cost
    # ---------------------------------------------------------

    milling_tool_cost = (
        milling_time_index
        * milling_tool_price
    )


    # ---------------------------------------------------------
    # 18. Heat treatment
    # ---------------------------------------------------------
    #
    # Only apply heat treatment if the recommended tooling
    # material profile requires it.
    #
    # The €/kg value itself remains editable from the frontend.

    if (
        recommended_profile
        .requires_heat_treatment
    ):
        heat_treatment_cost = (
            tooling_weight_kg
            * heat_treatment_eur_per_kg
        )
    else:
        heat_treatment_cost = 0.0


    # ---------------------------------------------------------
    # 19. Cooling cost
    # ---------------------------------------------------------

    cooling_cost = (
        calculate_cooling_cost(
            tooling_weight_kg=(
                tooling_weight_kg
            ),
            includes_cooling=(
                request.includes_cooling
            ),
        )
    )


    # ---------------------------------------------------------
    # 20. Base manufacturing cost
    # ---------------------------------------------------------

    base_cost = (
        material_cost
        + transformation_cost
        + outside_machining_cost
        + inside_machining_cost
        + milling_tool_cost
        + heat_treatment_cost
        + cooling_cost
    )


    # ---------------------------------------------------------
    # 21. Existing Excel commercial adjustments
    # ---------------------------------------------------------
    #
    # IMPORTANT:
    #
    # These stay unchanged for now.
    #
    # We are still NOT applying:
    #
    # request.assumptions.overhead_rate
    # request.assumptions.margin_rate
    #
    # because the existing workbook already has:
    #
    # +20% margin
    # +5% handling
    # +10% final markup
    #
    # We should clean this commercial layer separately.

    margin = (
        base_cost * 1.2
        - base_cost
    )

    handling_cost = (
        base_cost * 1.05
        - base_cost
    )


    # ---------------------------------------------------------
    # 22. Transport
    # ---------------------------------------------------------

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


    # ---------------------------------------------------------
    # 23. Final price
    # ---------------------------------------------------------

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


    # ---------------------------------------------------------
    # 24. API response
    # ---------------------------------------------------------

    return CalculationResponse(
        tooling_material=(
            recommended_profile.name
        ),

        gross_length_mm=(
            gross_length_mm
        ),

        gross_width_mm=(
            gross_width_mm
        ),

        gross_height_mm=(
            gross_height_mm
        ),

        tooling_weight_kg=(
            tooling_weight_kg
        ),

        outside_machining_volume_m3=(
            outside_machining_volume_m3
        ),

        inside_machining_volume_m3=(
            inside_machining_volume_m3
        ),

        milling_time_index=(
            milling_time_index
        ),

        removed_volume_time_min=(
            removed_volume_time_min
        ),

        material_cost=(
            material_cost
        ),

        transformation_cost=(
            transformation_cost
        ),

        outside_machining_cost=(
            outside_machining_cost
        ),

        inside_machining_cost=(
            inside_machining_cost
        ),

        milling_tool_cost=(
            milling_tool_cost
        ),

        cooling_cost=(
            cooling_cost
        ),

        heat_treatment_cost=(
            heat_treatment_cost
        ),

        margin=(
            margin
        ),

        handling_cost=(
            handling_cost
        ),

        transport_cost=(
            transport_cost
        ),

        total_price=(
            total_price
        ),

        recommended_material=(
            recommendation.material_label
        ),

        recommended_material_family=(
            recommendation.material_family
        ),

        recommendation_confidence=(
            recommendation.confidence
        ),

        failure_modes=(
            recommendation.failure_modes
        ),

        recommendation_reasons=(
            recommendation.reasons
        ),

        recommended_operations=(
            recommendation
            .recommended_operations
        ),
    )