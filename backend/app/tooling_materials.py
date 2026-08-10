from dataclasses import dataclass


@dataclass(frozen=True)
class ManufacturingRouteDefaults:
    cnc_3_axis_share: float
    cnc_5_axis_share: float
    edm_share: float
    grinding_share: float


@dataclass(frozen=True)
class ToolingMaterialProfile:
    name: str

    density_kg_m3: float
    block_price_per_tonne: float
    removal_rate_cm3_min: float

    milling_volume_factor: float
    milling_tool_price: float

    requires_heat_treatment: bool
    heat_treatment_eur_per_kg: float

    route: ManufacturingRouteDefaults


TOOLING_MATERIALS = {
    "aluminum_tooling": ToolingMaterialProfile(
        name="Aluminum tooling alloy",
        density_kg_m3=2710,
        block_price_per_tonne=2700,
        removal_rate_cm3_min=42.672,
        milling_volume_factor=0.010125,
        milling_tool_price=40,
        requires_heat_treatment=False,
        heat_treatment_eur_per_kg=0,
        route=ManufacturingRouteDefaults(
            cnc_3_axis_share=0.70,
            cnc_5_axis_share=0.30,
            edm_share=0.00,
            grinding_share=0.00,
        ),
    ),

    "pre_hardened_mold_steel": ToolingMaterialProfile(
        name="Pre-hardened mold steel",
        density_kg_m3=7850,
        block_price_per_tonne=1800,
        removal_rate_cm3_min=4.5,
        milling_volume_factor=0.00065,
        milling_tool_price=60,
        requires_heat_treatment=False,
        heat_treatment_eur_per_kg=0,
        route=ManufacturingRouteDefaults(
            cnc_3_axis_share=0.55,
            cnc_5_axis_share=0.30,
            edm_share=0.10,
            grinding_share=0.05,
        ),
    ),

    "hardened_mold_steel": ToolingMaterialProfile(
        name="Hardened mold steel",
        density_kg_m3=7900,
        block_price_per_tonne=2600,
        removal_rate_cm3_min=2.2,
        milling_volume_factor=0.00045,
        milling_tool_price=80,
        requires_heat_treatment=True,
        heat_treatment_eur_per_kg=2.5,
        route=ManufacturingRouteDefaults(
            cnc_3_axis_share=0.40,
            cnc_5_axis_share=0.25,
            edm_share=0.20,
            grinding_share=0.15,
        ),
    ),

    "corrosion_resistant_mold_steel": ToolingMaterialProfile(
        name="Corrosion-resistant mold steel",
        density_kg_m3=7800,
        block_price_per_tonne=3500,
        removal_rate_cm3_min=2.4,
        milling_volume_factor=0.00045,
        milling_tool_price=85,
        requires_heat_treatment=True,
        heat_treatment_eur_per_kg=3.0,
        route=ManufacturingRouteDefaults(
            cnc_3_axis_share=0.40,
            cnc_5_axis_share=0.30,
            edm_share=0.15,
            grinding_share=0.15,
        ),
    ),

    "cold_work_tool_steel": ToolingMaterialProfile(
        name="Cold-work tool steel",
        density_kg_m3=7850,
        block_price_per_tonne=2200,
        removal_rate_cm3_min=2.5,
        milling_volume_factor=0.0005,
        milling_tool_price=75,
        requires_heat_treatment=True,
        heat_treatment_eur_per_kg=2.5,
        route=ManufacturingRouteDefaults(
            cnc_3_axis_share=0.40,
            cnc_5_axis_share=0.20,
            edm_share=0.20,
            grinding_share=0.20,
        ),
    ),

    "high_wear_cold_work_steel": ToolingMaterialProfile(
        name="High-wear cold-work tool steel",
        density_kg_m3=7900,
        block_price_per_tonne=3000,
        removal_rate_cm3_min=1.9,
        milling_volume_factor=0.00042,
        milling_tool_price=90,
        requires_heat_treatment=True,
        heat_treatment_eur_per_kg=3.0,
        route=ManufacturingRouteDefaults(
            cnc_3_axis_share=0.30,
            cnc_5_axis_share=0.20,
            edm_share=0.25,
            grinding_share=0.25,
        ),
    ),

    "high_toughness_cold_work_steel": ToolingMaterialProfile(
        name="High-toughness cold-work tool steel",
        density_kg_m3=7850,
        block_price_per_tonne=3200,
        removal_rate_cm3_min=2.1,
        milling_volume_factor=0.00045,
        milling_tool_price=90,
        requires_heat_treatment=True,
        heat_treatment_eur_per_kg=3.0,
        route=ManufacturingRouteDefaults(
            cnc_3_axis_share=0.35,
            cnc_5_axis_share=0.20,
            edm_share=0.25,
            grinding_share=0.20,
        ),
    ),
}