"""Complete-tool model: calibration ranges and live inputs.

The ranges are typical European (Germany) toolmaker prices for a complete tool for
each process's reference part at 10,000 parts. They are planning benchmarks: when
real quotations are available, update the ranges and app/complete_tool.EFFORT together.
"""
import unittest

from app.advisor import build_report
from app.calculator import calculate
from app.complete_tool import MACHINABILITY, size_factor
from app.country_profiles import COUNTRY_PROFILES, assumptions_in_eur
from app.models import CalculationRequest
from app.tooling_catalog import block_records
from app.tooling_materials import TOOLING_MATERIALS
from test_workbook import workbook_request

TARGETS = {
    "bending": (500, 3_000), "metal_extrusion": (2_000, 8_000), "die_casting": (25_000, 45_000),
    "sand_casting": (1_000, 4_000), "investment_casting": (2_500, 7_000), "closed_die_forging": (10_000, 30_000),
    "plastic_extrusion": (5_000, 15_000), "blow_molding": (6_000, 15_000), "compression_molding": (10_000, 25_000),
    "transfer_molding": (10_000, 25_000), "rotational_molding": (2_000, 6_000), "powder_metallurgy": (10_000, 25_000),
    "metal_injection_molding": (15_000, 35_000), "composite_molding": (2_000, 8_000), "pultrusion": (10_000, 30_000),
    "punching_blanking": (3_000, 10_000), "fine_blanking": (20_000, 45_000), "progressive_die_stamping": (25_000, 50_000),
    "tube_hydroforming": (25_000, 60_000), "sheet_hydroforming": (5_000, 15_000), "spinning": (500, 3_000),
}
MATERIAL = {
    "die_casting": "cast_aluminum", "metal_extrusion": "cast_aluminum", "sand_casting": "cast_iron",
    "investment_casting": "stainless_steel", "plastic_extrusion": "standard_thermoplastic",
    "blow_molding": "standard_thermoplastic", "compression_molding": "thermoset", "transfer_molding": "thermoset",
    "rotational_molding": "standard_thermoplastic", "powder_metallurgy": "metal_powder",
    "metal_injection_molding": "metal_powder", "composite_molding": "fiber_composite", "pultrusion": "fiber_composite",
    "spinning": "aluminum_sheet",
}


def reference(process, **kw):
    return workbook_request(process, 10_000, sizing_mode="part_scaled", workpiece_material=MATERIAL.get(process, "mild_steel"), **kw)


def injection(dims, cavities=1, country="DE", **kw):
    data = dict(process="plastic_injection", parts_per_mold=cavities, manufacturing_country=country, expected_cycles=50_000,
                cycle_band="10000_to_100000", workpiece_material="standard_thermoplastic", includes_cooling=True,
                truck_distance_km=0, part=dict(length_mm=dims[0], width_mm=dims[1], height_mm=dims[2]),
                assumptions=assumptions_in_eur(country, 1.16))
    data.update(kw)
    return CalculationRequest(**data)


class CalibrationTests(unittest.TestCase):
    def test_reference_parts_land_in_market_ranges(self):
        for process, (low, high) in TARGETS.items():
            with self.subTest(process=process):
                price = calculate(reference(process)).total_price
                self.assertTrue(low <= price <= high, f"{process}: {price:,.0f} outside {low:,}-{high:,}")

    def test_injection_molds_land_in_market_ranges(self):
        for dims, cavities, (low, high) in [((50, 50, 20), 1, (8_000, 16_000)), ((120, 80, 30), 2, (18_000, 35_000)),
                                            ((200, 150, 50), 1, (18_000, 45_000)), ((400, 300, 100), 1, (45_000, 110_000))]:
            with self.subTest(dims=dims):
                price = calculate(injection(dims, cavities)).total_price
                self.assertTrue(low <= price <= high, f"{dims}: {price:,.0f} outside {low:,}-{high:,}")

    def test_china_is_cheaper_but_not_implausibly(self):
        germany = calculate(injection((120, 80, 30), 2)).total_price
        china = calculate(injection((120, 80, 30), 2, country="CN")).total_price
        # Chinese molds typically cost about 35-70 % of a German quote.
        self.assertTrue(0.3 < china / germany < 0.75, china / germany)


class ModelBehaviourTests(unittest.TestCase):
    def test_breakdown_has_every_complete_tool_line(self):
        result = calculate(reference("die_casting"))
        for key in ("construction_cost", "design_cost", "standard_parts_cost", "assembly_tryout_cost", "energy_cost",
                    "overhead_cost", "margin"):
            self.assertGreater(getattr(result, key), 0, key)
        self.assertEqual((result.final_markup, result.handling_cost), (0, 0))
        self.assertGreater(result.design_hours, 10)

    def test_former_dead_inputs_change_the_price(self):
        base = calculate(reference("die_casting"))
        for key, value in (("engineering_rate", 160.0), ("overhead_rate", 0.30), ("margin_rate", 0.30),
                           ("electricity_eur_kwh", 1.0)):
            with self.subTest(input=key):
                changed = reference("die_casting")
                setattr(changed.assumptions, key, value)
                self.assertGreater(calculate(changed).total_price, base.total_price)

    def test_effort_grows_with_part_size_but_sublinearly(self):
        self.assertEqual(size_factor(100), 1)
        self.assertAlmostEqual(size_factor(400), 2)
        self.assertEqual(size_factor(10), 0.6)
        self.assertEqual(size_factor(5000), 3.0)
        small = calculate(injection((50, 50, 20)))
        large = calculate(injection((400, 300, 100)))
        self.assertGreater(large.construction_hours, small.construction_hours)
        self.assertLess(large.construction_hours / small.construction_hours, 8)

    def test_machinability_ratio_is_realistic(self):
        self.assertAlmostEqual(MACHINABILITY["pre_hardened_mold_steel"], 1.0)
        self.assertTrue(1.8 < MACHINABILITY["hardened_mold_steel"] / MACHINABILITY["aluminum_tooling"] < 3)

    def test_tolerance_and_finish_add_effort(self):
        standard = calculate(injection((120, 80, 30))).total_price
        precise = calculate(injection((120, 80, 30), tolerance_level="high_precision")).total_price
        optical = calculate(injection((120, 80, 30), surface_finish="optical")).total_price
        self.assertGreater(precise, standard * 1.1)
        self.assertGreater(optical, standard * 1.1)

    def test_premium_grades_cost_more(self):
        result = calculate(workbook_request("die_casting", 200_000, sizing_mode="part_scaled", workpiece_material="cast_aluminum"))
        premium = [b for b in result.tooling_blocks if "ESR" in b.material_note]
        self.assertTrue(premium)
        self.assertTrue(all("premium grade" in b.costing_material for b in premium))
        self.assertTrue(all(b.material_assumptions.block_price_per_tonne == 2600 * 1.6 for b in premium))

    def test_pm_steel_and_carbide_prices(self):
        # x2 x1.4 in the calculators: about 22 EUR/kg for PM/HSS and about 70 EUR/kg for carbide.
        self.assertAlmostEqual(TOOLING_MATERIALS["high_wear_cold_work_steel"].block_price_per_tonne * 2.8 / 1000, 22.4)
        self.assertAlmostEqual(TOOLING_MATERIALS["carbide"].block_price_per_tonne * 2.8 / 1000, 70)
        report = build_report(workbook_request("powder_metallurgy", 500_000, workpiece_material="metal_powder"))
        carbide = next(o for o in report.material_options if o.family == "carbide")
        self.assertEqual(carbide.fit, "strong")

    def test_large_parts_get_proportional_walls(self):
        small = calculate(workbook_request("die_casting", 50_000, sizing_mode="part_scaled", workpiece_material="cast_aluminum"))
        large = calculate(workbook_request("die_casting", 50_000, sizing_mode="part_scaled", workpiece_material="cast_aluminum",
                                           part=dict(length_mm=1000, width_mm=800, height_mm=300)))
        cavity = large.tooling_blocks[0]
        self.assertGreaterEqual(cavity.sizing_inputs["side_reserve_x_mm"], 150)
        self.assertGreaterEqual(cavity.sizing_inputs["backing_mm"], 150)
        self.assertGreater(large.tooling_weight_kg, 5_000)
        # Punches and pins are not thickened.
        stamping = calculate(workbook_request("punching_blanking", 50_000, sizing_mode="part_scaled",
                                              part=dict(length_mm=500, width_mm=500, height_mm=2), material_thickness_mm=2))
        punch = next(b for b in stamping.tooling_blocks if b.role.startswith("MALE"))
        record = next(r for r in block_records("punching_blanking", 50_000) if r["component_id"] == punch.component_id)
        self.assertEqual(punch.sizing_inputs["side_reserve_x_mm"], record["inputs"]["side_reserve_x_mm"])
        self.assertLess(small.tooling_weight_kg, 200)

    def test_china_and_india_rates_are_market_level(self):
        for code, ceiling in (("CN", 60), ("IN", 45)):
            self.assertEqual(COUNTRY_PROFILES[code]["currency"], "USD")
            self.assertLessEqual(COUNTRY_PROFILES[code]["cnc_3_axis_rate"], ceiling)
            self.assertLess(COUNTRY_PROFILES[code]["cnc_3_axis_rate"], COUNTRY_PROFILES["DE"]["cnc_3_axis_rate"] / 2)


if __name__ == "__main__":
    unittest.main()
