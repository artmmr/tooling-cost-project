"""Engineering sanity checks: material rules, tool life and cost behaviour."""
import unittest

from app.advisor import build_report
from app.calculator import calculate, calculate_cooling_cost
from app.country_profiles import COUNTRY_PROFILES
from app.models import CalculationRequest
from app.recommendation import recommend_tooling
from app.tool_life import typical_life
from test_workbook import workbook_request


def legacy(process, material, cycles=50_000, band="10000_to_100000", **kw):
    data = dict(process=process, parts_per_mold=1, manufacturing_country="DE", expected_cycles=cycles, cycle_band=band,
                workpiece_material=material, includes_cooling=False, truck_distance_km=0,
                part=dict(length_mm=100, width_mm=80, height_mm=30), assumptions=COUNTRY_PROFILES["DE"])
    data.update(kw)
    return CalculationRequest(**data)


class MaterialRuleTests(unittest.TestCase):
    def test_die_casting_uses_hot_work_steel(self):
        for material in ("cast_aluminum", "copper_brass"):
            for cycles, band in ((5_000, "up_to_10000"), (200_000, "100000_to_250000")):
                with self.subTest(material=material, cycles=cycles):
                    rec = recommend_tooling(legacy("metal_molding", material, cycles, band))
                    self.assertEqual(rec.material_family, "hardened_mold_steel")
                    self.assertIn("thermal fatigue", rec.failure_modes)
        self.assertIn("soldering", recommend_tooling(legacy("metal_molding", "cast_aluminum")).failure_modes)

    def test_optical_finish_uses_polishable_stainless(self):
        rec = recommend_tooling(legacy("plastic_injection", "standard_thermoplastic", surface_finish="optical"))
        self.assertEqual(rec.material_family, "corrosion_resistant_mold_steel")
        rec = recommend_tooling(legacy("plastic_injection", "standard_thermoplastic", surface_finish="standard"))
        self.assertEqual(rec.material_family, "pre_hardened_mold_steel")

    def test_matrix_grade_is_not_applied_to_another_process(self):
        report = build_report(workbook_request("die_casting", 50_000, workpiece_material="copper_brass"))
        self.assertFalse(report.matrix.covered)  # Brass castings are not in the matrix.
        cold = next(o for o in report.material_options if o.family == "cold_work_tool_steel")
        self.assertEqual(cold.fit, "not_recommended")


class ToolLifeTests(unittest.TestCase):
    def test_typical_life_values(self):
        self.assertEqual(typical_life("die_casting", "hardened_mold_steel", "cast_aluminum"), 100_000)
        self.assertEqual(typical_life("die_casting", "hardened_mold_steel", "copper_brass"), 20_000)
        self.assertEqual(typical_life("die_casting", "hardened_mold_steel", "cast_aluminum", "zinc_die_casting"), 500_000)
        self.assertEqual(typical_life("closed_die_forging", "hardened_mold_steel", "mild_steel"), 10_000)
        self.assertEqual(typical_life("plastic_injection", "aluminum_tooling", "standard_thermoplastic"), 50_000)
        self.assertEqual(typical_life("plastic_injection", "hardened_mold_steel", "glass_filled_thermoplastic"), 500_000)
        self.assertLess(typical_life("punching_blanking", "cold_work_tool_steel", "stainless_steel"),
                        typical_life("punching_blanking", "cold_work_tool_steel", "mild_steel"))
        self.assertGreater(typical_life("punching_blanking", "high_wear_cold_work_steel", "mild_steel"),
                           typical_life("punching_blanking", "cold_work_tool_steel", "mild_steel"))
        self.assertIsNone(typical_life("metal_extrusion", "hardened_mold_steel", "cast_aluminum"))

    def test_replacements_scale_with_quantity_and_keep_supports(self):
        low = build_report(workbook_request("closed_die_forging", 5_000, workpiece_material="mild_steel")).tool_life
        high = build_report(workbook_request("closed_die_forging", 500_000, workpiece_material="mild_steel")).tool_life
        self.assertEqual(low.replacements, 0)
        self.assertEqual(high.replacements, 49)
        trim = [i for i in high.items if "trim" in i.component.lower()]
        self.assertTrue(trim)
        self.assertTrue(all(i.life == 100_000 and i.replacements == 4 for i in trim))
        self.assertGreater(high.lifetime_cost, 10 * low.lifetime_cost)
        report = build_report(workbook_request("die_casting", 500_000, workpiece_material="cast_aluminum",
                                               sizing_mode="part_scaled"))
        components = {i.component for i in report.tool_life.items}
        self.assertTrue(components)
        self.assertFalse(any("carrier" in c.lower() for c in components))

    def test_parallel_tool_sets_share_the_quantity(self):
        one = build_report(workbook_request("closed_die_forging", 40_000, workpiece_material="mild_steel")).tool_life
        two = build_report(workbook_request("closed_die_forging", 40_000, workpiece_material="mild_steel", parts_per_mold=2)).tool_life
        self.assertEqual((one.shots, one.replacements), (40_000, 3))
        self.assertEqual((two.shots, two.replacements), (20_000, 1))

    def test_lifetime_cost_counts_replacements_per_material(self):
        report = build_report(legacy("plastic_injection", "standard_thermoplastic", 250_000, "100000_to_250000"))
        aluminium = next(o for o in report.material_options if o.family == "aluminum_tooling")
        hardened = next(o for o in report.material_options if o.family == "hardened_mold_steel")
        self.assertLess(aluminium.price, hardened.price)
        self.assertEqual((aluminium.replacements, hardened.replacements), (4, 0))
        self.assertAlmostEqual(hardened.lifetime_price, hardened.price)
        # Replacements re-make the working inserts only; the mould base and design are reused.
        self.assertGreater(aluminium.lifetime_price, 2 * aluminium.price)
        # With construction hours scaled by machinability, five aluminium insert sets cost more
        # over 250,000 shots than one hardened-steel mould, as in practice.
        self.assertGreater(aluminium.lifetime_price, hardened.lifetime_price)
        # A single aluminium mould is cheaper, but not by an order of magnitude.
        self.assertGreater(aluminium.price / hardened.price, 0.35)

    def test_extrusion_is_not_counted_in_parts(self):
        life = build_report(workbook_request("metal_extrusion", 50_000, workpiece_material="cast_aluminum")).tool_life
        self.assertFalse(life.modelled)
        self.assertIn("length or tonnes", life.basis)


class CostBehaviourTests(unittest.TestCase):
    def test_cooling_scales_with_tool_size(self):
        self.assertEqual(calculate_cooling_cost(10, False), 0)
        self.assertEqual(calculate_cooling_cost(10, True), 800)
        self.assertLess(calculate_cooling_cost(100, True), calculate_cooling_cost(400, True))
        self.assertEqual(calculate_cooling_cost(60_000, True), 20_000)
        sizes = [5, 50, 200, 400, 800, 1500, 2500, 10_000, 60_000]
        costs = [calculate_cooling_cost(w, True) for w in sizes]
        self.assertEqual(costs, sorted(costs))

    def test_price_grows_with_part_size(self):
        prices = [calculate(legacy("plastic_injection", "standard_thermoplastic", part=dict(length_mm=s, width_mm=s * 0.8, height_mm=s * 0.3))).total_price
                  for s in (50, 100, 200, 400)]
        self.assertEqual(prices, sorted(prices))

    def test_harder_materials_cost_more_to_machine(self):
        req = legacy("plastic_injection", "standard_thermoplastic")
        from app.advisor import material_options
        options = {o.family: o for o in material_options(req, calculate(req))[0]}
        self.assertLess(options["aluminum_tooling"].price, options["pre_hardened_mold_steel"].price)
        self.assertLess(options["pre_hardened_mold_steel"].price, options["hardened_mold_steel"].price)


if __name__ == "__main__":
    unittest.main()


class ForcedMaterialTests(unittest.TestCase):
    def test_broad_process_can_be_priced_in_another_material(self):
        base = calculate(legacy("plastic_injection", "standard_thermoplastic"))
        forced = calculate(legacy("plastic_injection", "standard_thermoplastic",
                                  tooling_material_family="aluminum_tooling", force_tooling_material=True))
        self.assertEqual(base.costing_material_family, "pre_hardened_mold_steel")
        self.assertEqual(forced.costing_material_family, "aluminum_tooling")
        self.assertEqual(forced.recommended_material_family, "pre_hardened_mold_steel")
        self.assertLess(forced.total_price, base.total_price)
        report = build_report(legacy("plastic_injection", "standard_thermoplastic",
                                     tooling_material_family="aluminum_tooling", force_tooling_material=True))
        current = next(o for o in report.material_options if o.is_current)
        self.assertEqual(current.family, "aluminum_tooling")
        self.assertEqual(report.tool_life.life, 50_000)

    def test_unknown_forced_family_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate(legacy("plastic_injection", "standard_thermoplastic", tooling_material_family="unobtainium",
                             force_tooling_material=True))
