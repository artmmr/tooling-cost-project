"""Run with: python -m unittest discover -s tests -v"""
import math
import unittest
from pydantic import ValidationError
from app.models import CalculationRequest
from app.calculator import calculate
from app.country_profiles import COUNTRY_PROFILES


def example(**overrides):
    data = dict(cycle_band='100000_to_250000', process='stamping', parts_per_mold=2,
                manufacturing_country='DE', expected_cycles=150000,
                workpiece_material='high_strength_steel', material_thickness_mm=3,
                tolerance_level='high_precision', truck_distance_km=1700,
                sea_distance_km=19800, includes_cooling=False,
                part=dict(length_mm=300, width_mm=300, height_mm=40),
                assumptions=COUNTRY_PROFILES['DE'])
    data.update(overrides)
    return CalculationRequest(**data)


class LogisticsTests(unittest.TestCase):
    def test_legacy_km_and_nautical_miles_match(self):
        old = calculate(example())
        new = calculate(example(sea_distance_nm=19800 / 1.852, sea_distance_km=0))
        self.assertAlmostEqual(old.total_price, new.total_price)
        self.assertAlmostEqual(old.transport_cost,
            old.tooling_weight_kg * (1700 * 5.6 / 18000 * 2 + 8000 / 27000 * 2))

    def test_new_distance_takes_precedence_even_when_zero(self):
        self.assertEqual(calculate(example(sea_distance_nm=0)).sea_transport_cost, 0)

    def test_edit_freight_rate_updates_total(self):
        base = calculate(example())
        changed = calculate(example(logistics={'road_rate_eur_per_km':11.2}))
        self.assertAlmostEqual(changed.road_transport_cost, 2 * base.road_transport_cost)
        self.assertAlmostEqual(changed.total_price - base.total_price, base.road_transport_cost * 1.1)

    def test_whole_loads_and_zero_distance(self):
        result = calculate(example(logistics={'allocation':'whole_load'}))
        self.assertAlmostEqual(result.road_transport_cost, 1700 * 5.6 * math.ceil(result.tooling_weight_kg / 18000) * 2)
        zero = calculate(example(truck_distance_km=0,sea_distance_nm=0,logistics={'allocation':'whole_load'}))
        self.assertEqual(zero.transport_cost,0)

    def test_zero_rate_is_valid(self):
        self.assertEqual(calculate(example(logistics={'road_rate_eur_per_km':0, 'sea_rate_eur_per_nm':0})).transport_cost,0)

    def test_invalid_freight_rejected(self):
        for invalid in [{'road_load_kg':0}, {'sea_rate_eur_per_nm':-1}, {'road_journeys':1.5}, {'allocation':'other'}, {'road_rate_eur_per_km':float('inf')}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError): example(logistics=invalid)

    def test_tooling_override_changes_cost(self):
        req=example();base=calculate(req)
        from app.tooling_materials import TOOLING_MATERIALS
        profile=TOOLING_MATERIALS[base.recommended_material_family]
        override={name:getattr(profile,name) for name in ['density_kg_m3','block_price_per_tonne','removal_rate_cm3_min','milling_volume_factor','milling_tool_price','heat_treatment_eur_per_kg']}
        override['block_price_per_tonne']*=2
        changed=calculate(example(tooling_material_family=base.recommended_material_family,tooling_material_assumptions=override))
        self.assertAlmostEqual(changed.material_cost,base.material_cost*2)
        stale=calculate(example(tooling_material_family='aluminum_tooling',tooling_material_assumptions=override))
        self.assertEqual(stale.total_price,base.total_price)

    def test_component_block_sizing_is_returned(self):
        result = calculate(example(process='stamping', expected_cycles=150000))
        self.assertEqual(result.tooling_quantity_band, 'Above 100,000')
        self.assertIn('progressive die', result.tooling_concept.lower())
        self.assertGreater(result.tooling_weight_kg, 0)
        self.assertAlmostEqual(result.final_markup, result.total_price / 11)
        self.assertTrue(result.recommendation_confidence_explanation)
        self.assertGreaterEqual(len(result.tooling_blocks), 2)
        self.assertTrue(all(block.raw_stock for block in result.tooling_blocks))
        self.assertTrue(any(block.role == 'FEMALE DIE' for block in result.tooling_blocks))

if __name__ == '__main__': unittest.main()
