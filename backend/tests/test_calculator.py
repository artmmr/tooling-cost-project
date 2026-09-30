from app.calculator import calculate
from app.country_profiles import COUNTRY_PROFILES
from app.models import (
    CalculationRequest,
    CycleBand,
    LogisticsAssumptions,
    PartDimensions,
    ProcessType,
    SurfaceFinish,
    ToleranceLevel,
    WorkpieceMaterial,
    CostAssumptions,
)


def create_base_request(**overrides):
    base = {
        "cycle_band": CycleBand.FROM_100K_TO_250K,
        "process": ProcessType.STAMPING,
        "parts_per_mold": 2,
        "manufacturing_country": "DE",
        "expected_cycles": 150000,
        "workpiece_material": WorkpieceMaterial.ADVANCED_HIGH_STRENGTH_STEEL,
        "material_thickness_mm": 3.0,
        "tolerance_level": ToleranceLevel.HIGH_PRECISION,
        "surface_finish": SurfaceFinish.STANDARD,
        "abrasive_material": False,
        "corrosive_environment": False,
        "truck_distance_km": 1700.0,
        "sea_distance_nm": 10700.0,
        "includes_cooling": False,
        "part": PartDimensions(length_mm=300, width_mm=300, height_mm=40),
        "assumptions": CostAssumptions(**{
            k: v for k, v in COUNTRY_PROFILES["DE"].items()
            if k not in ("name", "currency", "currency_symbol")
        }),
    }
    base.update(overrides)
    return CalculationRequest(**base)


def test_calculate_germany_currency_and_confidence():
    req = create_base_request(manufacturing_country="DE")
    res = calculate(req)

    assert res.currency == "EUR"
    assert res.currency_symbol == "€"
    assert res.recommendation_confidence == "high"
    assert "High confidence:" in res.confidence_explanation
    assert res.total_price > 0
    assert res.sea_transport_cost > 0
    assert res.road_transport_cost > 0


def test_calculate_china_currency_usd():
    req = create_base_request(
        manufacturing_country="CN",
        assumptions=CostAssumptions(**{
            k: v for k, v in COUNTRY_PROFILES["CN"].items()
            if k not in ("name", "currency", "currency_symbol")
        }),
    )
    res = calculate(req)

    assert res.currency == "USD"
    assert res.currency_symbol == "$"


def test_capitalized_risks_and_operations():
    req = create_base_request()
    res = calculate(req)

    for mode in res.failure_modes:
        assert mode[0].isupper(), f"Risk '{mode}' should start with capital letter"

    for op in res.recommended_operations:
        assert op[0].isupper(), f"Operation '{op}' should start with capital letter"

    assert any("Electro-Discharge Machining" in op for op in res.recommended_operations)


def test_custom_logistics_assumptions():
    custom_logistics = LogisticsAssumptions(
        truck_distance_km=500.0,
        road_cost_per_100_km=700.0,
        road_load_kg=15000.0,
        sea_distance_nm=5000.0,
        sea_container_cost=10000.0,
        sea_reference_distance_nm=10700.0,
        sea_load_kg=25000.0,
    )
    req = create_base_request(logistics=custom_logistics)
    res = calculate(req)

    assert res.total_price > 0
    assert res.road_transport_cost > 0
    assert res.sea_transport_cost > 0
