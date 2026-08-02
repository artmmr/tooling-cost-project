from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialParameters:
    name: str
    density_kg_m3: float
    removal_rate_cm3_min: float
    block_price_per_tonne: float
    milling_volume_factor: float
    milling_tool_price: float


MATERIALS = {
    "aluminum": MaterialParameters(
        name="Aluminum",
        density_kg_m3=2710,
        removal_rate_cm3_min=42.672,
        block_price_per_tonne=2700,
        milling_volume_factor=0.010125,
        milling_tool_price=40,
    ),
    "steel": MaterialParameters(
        name="Steel",
        density_kg_m3=7850,
        removal_rate_cm3_min=3.7338,
        block_price_per_tonne=800,
        milling_volume_factor=0.0005537109375,
        milling_tool_price=60,
    ),
    "hard_steel": MaterialParameters(
        name="Hard Steel",
        density_kg_m3=7900,
        removal_rate_cm3_min=1.8669,
        block_price_per_tonne=1400,
        milling_volume_factor=0.00044296875,
        milling_tool_price=80,
    ),
}


MACHINE_RATE_PER_HOUR = 150
OPERATOR_RATE_PER_HOUR = 40


ROAD_COST_PER_100_KM = (1400 / 250) * 100
ROAD_LOAD_KG = 18_000


SEA_COST_PER_1000_KM = (
    8000 / (11_000 * 1.8)
) * 1000

SEA_LOAD_KG = 27_000