from dataclasses import dataclass


@dataclass
class ToolingRecommendation:
    material_family: str
    material_label: str
    confidence: str

    failure_modes: list[str]
    reasons: list[str]

    requires_heat_treatment: bool
    recommended_operations: list[str]


PLASTIC_PROCESSES = {
    "plastic_molding",
    "plastic_injection",
    "foaming",
    "thermoforming",
}


METAL_PROCESSES = {
    "metal_molding",
    "stamping",
    "forming",
    "deep_drawing",
}


ABRASIVE_PLASTIC_MATERIALS = {
    "glass_filled_thermoplastic",
    "mineral_filled_thermoplastic",
    "thermoset",
}


CORROSIVE_PLASTIC_MATERIALS = {
    "corrosive_polymer",
}


HIGH_STRENGTH_METALS = {
    "high_strength_steel",
    "advanced_high_strength_steel",
    "stainless_steel",
}


HIGH_GALLING_RISK_METALS = {
    "stainless_steel",
    "aluminum_sheet",
}


def unique_items(items: list[str]) -> list[str]:
    """
    Remove duplicates while preserving order.
    """

    return list(dict.fromkeys(items))


def recommend_tooling(request) -> ToolingRecommendation:
    """
    Main recommendation dispatcher.

    Routes the calculation request to the appropriate
    process-specific tooling recommendation engine.
    """

    process = request.process.value

    if process in PLASTIC_PROCESSES:
        return recommend_plastic_tooling(request)

    if process in METAL_PROCESSES:
        return recommend_metal_tooling(request)

    raise ValueError(
        f"No tooling recommendation rules available "
        f"for process '{process}'."
    )


def recommend_plastic_tooling(
    request,
) -> ToolingRecommendation:
    """
    Recommend tooling material for plastic-related processes.

    Main engineering considerations:
    - abrasive wear
    - corrosion
    - surface degradation
    - long-term wear
    - dimensional stability
    - required polishing / finish
    """

    cycles = request.expected_cycles

    workpiece_material = (
        request.workpiece_material.value
        if hasattr(
            request.workpiece_material,
            "value",
        )
        else request.workpiece_material
    )

    tolerance = (
        request.tolerance_level.value
        if hasattr(
            request.tolerance_level,
            "value",
        )
        else request.tolerance_level
    )

    surface_finish = (
        request.surface_finish.value
        if hasattr(
            request.surface_finish,
            "value",
        )
        else request.surface_finish
    )

    abrasive = (
        request.abrasive_material
        or workpiece_material
        in ABRASIVE_PLASTIC_MATERIALS
    )

    corrosive = (
        request.corrosive_environment
        or workpiece_material
        in CORROSIVE_PLASTIC_MATERIALS
    )

    failure_modes = []
    reasons = []


    # ---------------------------------------------------------
    # Detect abrasive wear risk
    # ---------------------------------------------------------

    if abrasive:
        failure_modes.append(
            "abrasive wear"
        )

        reasons.append(
            "The molded material is abrasive or filled, "
            "which increases cavity and core wear."
        )


    # ---------------------------------------------------------
    # Detect corrosion risk
    # ---------------------------------------------------------

    if corrosive:
        failure_modes.append(
            "corrosion"
        )

        reasons.append(
            "The molding environment or polymer presents "
            "an elevated corrosion risk."
        )


    # ---------------------------------------------------------
    # Surface finish requirement
    # ---------------------------------------------------------

    if surface_finish in {
        "high",
        "optical",
    }:
        failure_modes.append(
            "surface degradation"
        )

        reasons.append(
            "The required surface finish increases demands "
            "on polishability and surface stability."
        )


    # ---------------------------------------------------------
    # Precision requirement
    # ---------------------------------------------------------

    if tolerance == "precision":
        failure_modes.append(
            "dimensional drift"
        )

        reasons.append(
            "Precision tolerance increases dimensional "
            "stability requirements."
        )


    if tolerance == "high_precision":
        failure_modes.append(
            "dimensional drift"
        )

        reasons.append(
            "High-precision tolerance strongly increases "
            "dimensional stability requirements."
        )


    # ---------------------------------------------------------
    # Tool life
    # ---------------------------------------------------------

    if cycles >= 100_000:
        failure_modes.append(
            "long-term wear"
        )

        reasons.append(
            "The expected production life is above "
            "100,000 cycles."
        )

    elif cycles >= 10_000:
        reasons.append(
            "Medium production volume requires greater "
            "tool durability than prototype tooling."
        )


    # =========================================================
    # CORROSIVE APPLICATION
    # =========================================================

    if corrosive:

        if abrasive:
            reasons.append(
                "Both corrosion resistance and wear resistance "
                "are important for this application."
            )

        return ToolingRecommendation(
            material_family=(
                "corrosion_resistant_mold_steel"
            ),

            material_label=(
                "Corrosion-resistant mold steel"
            ),

            confidence="high",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=True,

            recommended_operations=[
                "CNC rough machining",
                "heat treatment if required by selected grade",
                "CNC finish machining",
                "EDM if geometry requires it",
                "grinding if required",
                "polishing",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # ABRASIVE OR HIGH-VOLUME APPLICATION
    # =========================================================

    if (
        abrasive
        or cycles >= 100_000
    ):
        reasons.append(
            "Wear resistance is more important than "
            "maximum machinability for this application."
        )

        return ToolingRecommendation(
            material_family=(
                "hardened_mold_steel"
            ),

            material_label=(
                "Hardened mold steel"
            ),

            confidence="high",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=True,

            recommended_operations=[
                "CNC rough machining",
                "heat treatment",
                "CNC finish machining",
                "EDM if geometry requires it",
                "grinding if required",
                "polishing if required",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # HIGH PRECISION / HIGH FINISH
    # =========================================================

    if (
        tolerance == "high_precision"
        or surface_finish
        in {"high", "optical"}
    ):
        reasons.append(
            "Steel tooling is preferred because the "
            "application requires improved dimensional "
            "stability or surface quality."
        )

        return ToolingRecommendation(
            material_family=(
                "pre_hardened_mold_steel"
            ),

            material_label=(
                "Pre-hardened mold steel"
            ),

            confidence="high",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=False,

            recommended_operations=[
                "CNC rough machining",
                "CNC finish machining",
                "EDM if geometry requires it",
                "polishing",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # LOW-VOLUME PLASTIC TOOL
    # =========================================================

    if cycles < 10_000:
        reasons.append(
            "Low production volume and standard molding "
            "conditions favor a fast-machining tooling material."
        )

        return ToolingRecommendation(
            material_family=(
                "aluminum_tooling"
            ),

            material_label=(
                "Aluminum tooling alloy"
            ),

            confidence="medium",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=False,

            recommended_operations=[
                "CNC rough machining",
                "CNC finish machining",
                "polishing if required",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # MEDIUM-VOLUME PLASTIC TOOL
    # =========================================================

    reasons.append(
        "Medium production volume favors pre-hardened "
        "mold steel for improved durability."
    )

    return ToolingRecommendation(
        material_family=(
            "pre_hardened_mold_steel"
        ),

        material_label=(
            "Pre-hardened mold steel"
        ),

        confidence="medium",

        failure_modes=unique_items(
            failure_modes
        ),

        reasons=unique_items(
            reasons
        ),

        requires_heat_treatment=False,

        recommended_operations=[
            "CNC rough machining",
            "CNC finish machining",
            "EDM if geometry requires it",
            "polishing if required",
            "dimensional inspection",
        ],
    )


def recommend_metal_tooling(
    request,
) -> ToolingRecommendation:
    """
    Recommend tooling material for stamping,
    forming and deep-drawing applications.

    Main engineering considerations:
    - abrasive wear
    - adhesive wear / galling
    - chipping
    - cracking
    - plastic deformation
    - mechanical loading
    - dimensional stability
    """

    cycles = request.expected_cycles

    workpiece_material = (
        request.workpiece_material.value
        if hasattr(
            request.workpiece_material,
            "value",
        )
        else request.workpiece_material
    )

    tolerance = (
        request.tolerance_level.value
        if hasattr(
            request.tolerance_level,
            "value",
        )
        else request.tolerance_level
    )

    thickness = (
        request.material_thickness_mm
    )

    high_strength_material = (
        workpiece_material
        in HIGH_STRENGTH_METALS
    )

    galling_risk = (
        workpiece_material
        in HIGH_GALLING_RISK_METALS
    )

    failure_modes = []
    reasons = []


    # ---------------------------------------------------------
    # High-strength material
    # ---------------------------------------------------------

    if high_strength_material:
        failure_modes.extend(
            [
                "abrasive wear",
                "chipping",
                "cracking",
                "plastic deformation",
            ]
        )

        reasons.append(
            "The workpiece material has elevated strength "
            "or hardness, increasing tooling load and wear."
        )


    # ---------------------------------------------------------
    # AHSS-specific loading
    # ---------------------------------------------------------

    if (
        workpiece_material
        == "advanced_high_strength_steel"
    ):
        reasons.append(
            "Advanced high-strength steel generates severe "
            "contact pressure and increases cracking and "
            "plastic-deformation risk."
        )


    # ---------------------------------------------------------
    # Galling
    # ---------------------------------------------------------

    if galling_risk:
        failure_modes.append(
            "galling"
        )

        reasons.append(
            "The selected workpiece material has an "
            "elevated risk of adhesive wear or galling."
        )


    # ---------------------------------------------------------
    # Thickness / mechanical loading
    # ---------------------------------------------------------

    if thickness >= 3:
        failure_modes.append(
            "high mechanical loading"
        )

        reasons.append(
            "Material thickness of 3 mm or more increases "
            "mechanical loading on punches, dies and forming "
            "surfaces."
        )


    if thickness >= 6:
        failure_modes.append(
            "chipping"
        )

        failure_modes.append(
            "cracking"
        )

        reasons.append(
            "Heavy-gauge material significantly increases "
            "tool stress."
        )


    # ---------------------------------------------------------
    # Production life
    # ---------------------------------------------------------

    if cycles >= 100_000:
        failure_modes.append(
            "long-term wear"
        )

        reasons.append(
            "The expected tooling life is above "
            "100,000 cycles."
        )

    elif cycles >= 10_000:
        reasons.append(
            "Medium production volume requires production-grade "
            "cold-work tooling."
        )


    # ---------------------------------------------------------
    # Precision
    # ---------------------------------------------------------

    if tolerance == "precision":
        failure_modes.append(
            "dimensional drift"
        )

        reasons.append(
            "Precision tolerance increases wear and "
            "dimensional-stability requirements."
        )


    if tolerance == "high_precision":
        failure_modes.append(
            "dimensional drift"
        )

        reasons.append(
            "High-precision requirements increase the need "
            "for dimensional stability and controlled finish "
            "machining."
        )


    # =========================================================
    # SEVERE LOAD / AHSS
    # =========================================================

    if (
        workpiece_material
        == "advanced_high_strength_steel"
        or (
            high_strength_material
            and thickness >= 3
        )
    ):
        reasons.append(
            "The combination of high loading and cracking "
            "risk favors a high-toughness cold-work tool steel."
        )

        return ToolingRecommendation(
            material_family=(
                "high_toughness_cold_work_steel"
            ),

            material_label=(
                "High-toughness cold-work tool steel"
            ),

            confidence="high",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=True,

            recommended_operations=[
                "CNC rough machining",
                "stress relieving if required",
                "heat treatment",
                "EDM",
                "CNC finish machining",
                "grinding",
                "surface treatment or coating if required",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # HIGH WEAR
    # =========================================================

    if (
        cycles >= 100_000
        or high_strength_material
    ):
        reasons.append(
            "High wear demand favors hardened "
            "cold-work tool steel."
        )

        return ToolingRecommendation(
            material_family=(
                "high_wear_cold_work_steel"
            ),

            material_label=(
                "High-wear cold-work tool steel"
            ),

            confidence="high",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=True,

            recommended_operations=[
                "CNC rough machining",
                "heat treatment",
                "EDM if geometry requires it",
                "CNC finish machining",
                "grinding",
                "surface treatment or coating if required",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # GALLING-PRONE MATERIAL
    # =========================================================

    if galling_risk:
        reasons.append(
            "A cold-work tooling material with good "
            "resistance to adhesive wear is recommended."
        )

        return ToolingRecommendation(
            material_family=(
                "cold_work_tool_steel"
            ),

            material_label=(
                "Cold-work tool steel"
            ),

            confidence="medium",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=True,

            recommended_operations=[
                "CNC rough machining",
                "heat treatment",
                "CNC finish machining",
                "grinding",
                "anti-galling coating if required",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # HIGH PRECISION
    # =========================================================

    if tolerance == "high_precision":
        reasons.append(
            "High-precision forming requires hardened tooling "
            "with stable finished surfaces."
        )

        return ToolingRecommendation(
            material_family=(
                "cold_work_tool_steel"
            ),

            material_label=(
                "Cold-work tool steel"
            ),

            confidence="medium",

            failure_modes=unique_items(
                failure_modes
            ),

            reasons=unique_items(
                reasons
            ),

            requires_heat_treatment=True,

            recommended_operations=[
                "CNC rough machining",
                "heat treatment",
                "CNC finish machining",
                "grinding",
                "dimensional inspection",
            ],
        )


    # =========================================================
    # STANDARD PRODUCTION TOOL
    # =========================================================

    reasons.append(
        "Standard cold-forming conditions favor "
        "general-purpose cold-work tool steel."
    )

    return ToolingRecommendation(
        material_family=(
            "cold_work_tool_steel"
        ),

        material_label=(
            "Cold-work tool steel"
        ),

        confidence="medium",

        failure_modes=unique_items(
            failure_modes
        ),

        reasons=unique_items(
            reasons
        ),

        requires_heat_treatment=True,

        recommended_operations=[
            "CNC rough machining",
            "heat treatment",
            "CNC finish machining",
            "grinding if required",
            "dimensional inspection",
        ],
    )