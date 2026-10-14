import json
import math
from pathlib import Path
import unittest

from pydantic import ValidationError

from app.calculator import calculate
from app.country_profiles import COUNTRY_PROFILES
from app.models import CalculationRequest
from app.tooling_catalog import catalog, process_definition, quantity_grade
from app.workbook_sizing import stock_dimensions


def workbook_request(process="die_casting", quantity=1, **overrides):
    definition = process_definition(process)
    data = dict(process=process, parts_per_mold=1, manufacturing_country="DE",
                expected_quantity=quantity, workpiece_material="other", includes_cooling=False,
                truck_distance_km=0, sea_distance_nm=0, part=definition["reference_part"],
                material_thickness_mm=definition["reference_thickness_mm"] or 1,
                assumptions=COUNTRY_PROFILES["DE"], sizing_mode="reference")
    data.update(overrides)
    return CalculationRequest(**data)


class WorkbookTests(unittest.TestCase):
    def test_complete_catalog(self):
        data = catalog()
        self.assertEqual(len(data["processes"]), 21)
        self.assertEqual(len(data["grades"]), 126)
        self.assertEqual(len(data["blocks"]), 354)
        self.assertEqual(len(data["reference_summary"]), 59)
        self.assertEqual(len({b["record_id"] for b in data["blocks"]}), 354)
        self.assertEqual(sum(b["purchased"] for b in data["blocks"]), 6)

    def test_all_workbook_stock_formulas_against_excel_cached_results(self):
        for block in catalog()["blocks"]:
            with self.subTest(record=block["record_id"]):
                if block["purchased"]:
                    self.assertIsNone(block["expected"]["raw_length_mm"])
                    continue
                actual = stock_dimensions(block["inputs"], block["stock_form"])
                for key, value in actual.items():
                    expected = block["expected"][key.replace("height", "depth")]
                    if value is None:
                        self.assertIsNone(expected)
                    else:
                        self.assertAlmostEqual(value, expected, places=8)

    def test_all_126_process_quantity_calculations(self):
        for grade in catalog()["grades"]:
            with self.subTest(process=grade["process"], band=grade["band"]):
                result = calculate(workbook_request(grade["process"], grade["quantity_min"]))
                records = [b for b in catalog()["blocks"] if b["process"] == grade["process"] and b["band"] == grade["band"]]
                self.assertEqual(len(result.tooling_blocks), len(records))
                self.assertEqual(result.grade_candidates, grade["candidates"])
                self.assertEqual(result.grade_treatment, grade["treatment"])
                self.assertEqual(result.tooling_concept, grade["concept"])
                self.assertEqual(result.total_machined_blocks, sum(b["pieces"] for b in records if not b["purchased"]))
                self.assertEqual(result.total_purchased_assemblies, sum(b["pieces"] for b in records if b["purchased"]))
                self.assertTrue(math.isfinite(result.total_price))
                self.assertGreater(result.total_price, 0)
                self.assertAlmostEqual(sum(b.weight_kg for b in result.tooling_blocks), result.tooling_weight_kg)
                for block, record in zip(result.tooling_blocks, records):
                    self.assertEqual(block.record_id, record["record_id"])
                    self.assertEqual(block.material_note, record["material"])
                    self.assertEqual(block.raw_length_mm, record["expected"]["raw_length_mm"])
                    self.assertEqual(block.raw_width_mm, record["expected"]["raw_width_mm"])
                    self.assertEqual(block.raw_height_mm, record["expected"]["raw_depth_mm"])

    def test_boundaries_for_every_process(self):
        for process in catalog()["processes"]:
            grades = [g for g in catalog()["grades"] if g["process"] == process["code"]]
            for grade in grades:
                for quantity in [grade["quantity_min"], grade["quantity_max"] or 10**9]:
                    self.assertEqual(quantity_grade(process["code"], quantity)["band"], grade["band"])
            self.assertEqual(quantity_grade(process["code"], 100001)["quantity_max"], None)

    def test_quantity_does_not_resize_geometry(self):
        for process in catalog()["processes"]:
            low = calculate(workbook_request(process["code"], 1))
            high = calculate(workbook_request(process["code"], 100001))
            self.assertEqual([b.raw_stock for b in low.tooling_blocks], [b.raw_stock for b in high.tooling_blocks])

    def test_custom_mode_reproduces_every_reference_part(self):
        for process in catalog()["processes"]:
            with self.subTest(process=process["code"]):
                reference = calculate(workbook_request(process["code"]))
                custom = calculate(workbook_request(process["code"], sizing_mode="part_scaled"))
                self.assertEqual([b.raw_stock for b in reference.tooling_blocks], [b.raw_stock for b in custom.tooling_blocks])

    def test_extrusion_and_pultrusion_cut_length_not_die_length(self):
        for process in ["metal_extrusion", "plastic_extrusion", "pultrusion"]:
            request = workbook_request(process, sizing_mode="part_scaled")
            base = calculate(request)
            request.part.length_mm *= 5
            changed = calculate(request)
            self.assertEqual([b.raw_stock for b in base.tooling_blocks], [b.raw_stock for b in changed.tooling_blocks])

    def test_part_and_wall_thickness_updates(self):
        base = calculate(workbook_request(sizing_mode="part_scaled"))
        larger = calculate(workbook_request(sizing_mode="part_scaled", part=dict(length_mm=200, width_mm=200, height_mm=100)))
        self.assertGreater(larger.tooling_weight_kg, base.tooling_weight_kg)
        thicker = calculate(workbook_request(sizing_mode="part_scaled", material_thickness_mm=5))
        self.assertEqual(thicker.tooling_blocks[1].sizing_inputs["nominal_length_mm"], 90)
        with self.assertRaisesRegex(ValueError, "working envelope"):
            calculate(workbook_request(sizing_mode="part_scaled", material_thickness_mm=60))

    def test_reference_mode_is_independent_of_part_edit(self):
        base = calculate(workbook_request())
        changed = calculate(workbook_request(part=dict(length_mm=200, width_mm=200, height_mm=100)))
        self.assertEqual(base.total_price, changed.total_price)
        self.assertTrue(any("does not change" in w for w in changed.estimate_warnings))

    def test_multiple_sets_counted_once(self):
        one = calculate(workbook_request("progressive_die_stamping"))
        three = calculate(workbook_request("progressive_die_stamping", parts_per_mold=3))
        self.assertEqual(one.total_machined_blocks, 10)
        self.assertEqual(three.total_machined_blocks, 30)
        self.assertAlmostEqual(three.tooling_weight_kg, one.tooling_weight_kg * 3)
        self.assertAlmostEqual(three.removed_volume_time_min, one.removed_volume_time_min * 3)
        self.assertAlmostEqual(three.material_cost, one.material_cost * 3)
        self.assertEqual([b.raw_stock for b in one.tooling_blocks], [b.raw_stock for b in three.tooling_blocks])

    def test_round_billet_volume(self):
        result = calculate(workbook_request("metal_extrusion"))
        block = result.tooling_blocks[0]
        self.assertIsNone(block.raw_width_mm)
        self.assertAlmostEqual(block.raw_volume_m3, math.pi * (190 / 2)**2 * 70 / 1e9)

    def test_wax_sphere_guide_example(self):
        result = calculate(workbook_request("investment_casting"))
        block = result.tooling_blocks[0]
        self.assertEqual((block.pieces, block.role, block.raw_length_mm, block.raw_width_mm, block.raw_height_mm), (2, "FEMALE", 170, 170, 90))
        self.assertEqual(result.total_machined_blocks, 2)
        guide = {row[0]: row[1] for row in catalog()["worked_example"]}
        self.assertEqual(guide["Wax cavity diameter"], 102)
        self.assertEqual(guide["Cavity depth in each half"], 51)
        self.assertEqual(guide["Raw stock length / width"], block.raw_length_mm)
        self.assertEqual(guide["Raw stock thickness"], block.raw_height_mm)
        self.assertEqual(guide["Required blocks"], block.pieces)

    def test_edit_every_sizing_parameter_and_zero_allowances(self):
        override = dict(component_id="P03-C01", pieces=3, stock_form="Round billet", nominal_length_mm=100,
                        nominal_width_mm=100, nominal_depth_mm=50, enlargement_ratio=0.1,
                        side_reserve_x_mm=10, side_reserve_y_mm=0, backing_mm=20, allowance_mm=0, rounding_mm=5)
        result = calculate(workbook_request(block_overrides=[override]))
        block = result.tooling_blocks[0]
        self.assertEqual((block.raw_length_mm, block.raw_height_mm), (130, 75))
        self.assertIsNone(block.raw_width_mm)
        self.assertEqual(block.pieces, 3)
        self.assertTrue(block.modified)

    def test_rounding_at_exact_increment_and_just_above(self):
        inputs = dict(catalog()["blocks"][0]["inputs"])
        inputs.update(nominal_length_mm=100, enlargement_ratio=0.1, side_reserve_x_mm=0, allowance_mm=0)
        self.assertEqual(stock_dimensions(inputs, "Rectangular block")["raw_length_mm"], 110)
        inputs["nominal_length_mm"] = 100.000001
        self.assertEqual(stock_dimensions(inputs, "Rectangular block")["raw_length_mm"], 115)

    def test_purchased_assembly_never_has_invented_stock(self):
        base = calculate(workbook_request("sheet_hydroforming"))
        chamber = base.tooling_blocks[-1]
        self.assertTrue(chamber.purchased)
        self.assertIsNone(chamber.raw_length_mm)
        self.assertIsNone(chamber.cost_before_commercial)
        self.assertFalse(base.estimate_complete)
        quoted = calculate(workbook_request("sheet_hydroforming", block_overrides=[dict(
            component_id="P20-C03", purchased_unit_cost_eur=1200, purchased_unit_weight_kg=30)]))
        self.assertTrue(quoted.estimate_complete)
        self.assertEqual(quoted.purchased_assemblies_cost, 1200)
        self.assertAlmostEqual(quoted.total_price - base.total_price, 1200 * 1.25 * 1.1)
        self.assertAlmostEqual(quoted.tooling_weight_kg - base.tooling_weight_kg, 30)
        zero = calculate(workbook_request("sheet_hydroforming", block_overrides=[dict(
            component_id="P20-C03", purchased_unit_cost_eur=0, purchased_unit_weight_kg=0)]))
        self.assertTrue(zero.estimate_complete)

    def test_component_rates_and_route_change_cost(self):
        base = calculate(workbook_request())
        block = base.tooling_blocks[0]
        params = block.material_assumptions.model_dump()
        params["block_price_per_tonne"] *= 2
        changed = calculate(workbook_request(block_overrides=[dict(component_id=block.component_id, tooling_material_assumptions=params)]))
        self.assertGreater(changed.material_cost, base.material_cost)
        self.assertEqual(changed.tooling_blocks[1].cost_before_commercial, base.tooling_blocks[1].cost_before_commercial)
        route = dict(cnc_3_axis_share=0, cnc_5_axis_share=1, edm_share=0, grinding_share=0)
        routed = calculate(workbook_request(block_overrides=[dict(component_id=block.component_id, manufacturing_route=route)]))
        self.assertNotEqual(routed.total_price, base.total_price)

    def test_cad_volume_override_and_material_family(self):
        changed = calculate(workbook_request(block_overrides=[dict(component_id="P03-C01", machining_volume_m3=0, material_family="aluminum_tooling")]))
        self.assertEqual(changed.tooling_blocks[0].machining_volume_m3, 0)
        self.assertEqual(changed.tooling_blocks[0].material_family, "aluminum_tooling")
        with self.assertRaisesRegex(ValueError, "raw stock volume"):
            calculate(workbook_request(block_overrides=[dict(component_id="P03-C01", machining_volume_m3=1)]))

    def test_invalid_and_stale_component_overrides_rejected(self):
        for override in [dict(component_id="unknown"), dict(component_id="P01-C01"),
                         dict(component_id="P03-C01", material_family="unknown"),
                         dict(component_id="P03-C01", purchased_unit_cost_eur=10),
                         dict(component_id="P03-C01", manufacturing_route=dict(cnc_3_axis_share=1,cnc_5_axis_share=1,edm_share=0,grinding_share=0))]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                calculate(workbook_request(block_overrides=[override]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            calculate(workbook_request(block_overrides=[dict(component_id="P03-C01")] * 2))
        with self.assertRaisesRegex(ValueError, "purchased assembly"):
            calculate(workbook_request("sheet_hydroforming", block_overrides=[dict(component_id="P20-C03", backing_mm=10)]))

    def test_nonfinite_invalid_and_unknown_inputs(self):
        for override in [dict(component_id="P03-C01", rounding_mm=0), dict(component_id="P03-C01", pieces=1.5),
                         dict(component_id="P03-C01", allowance_mm=-1), dict(component_id="P03-C01", nominal_depth_mm=float("inf")),
                         dict(component_id="P03-C01", unknown=1)]:
            with self.subTest(override=override), self.assertRaises(ValidationError):
                workbook_request(block_overrides=[override])
        with self.assertRaises(ValidationError):
            workbook_request(quantity=1.5)
        with self.assertRaises(ValidationError):
            workbook_request(part=dict(length_mm=float("nan"), width_mm=100, height_mm=50))

    def test_cost_breakdown_reconciles(self):
        result = calculate(workbook_request("progressive_die_stamping", truck_distance_km=100, sea_distance_nm=200))
        before_markup = sum(getattr(result, key) for key in ["material_cost", "transformation_cost", "outside_machining_cost",
            "inside_machining_cost", "milling_tool_cost", "heat_treatment_cost", "cooling_cost", "purchased_assemblies_cost",
            "margin", "handling_cost", "transport_cost"])
        self.assertAlmostEqual(result.total_price, before_markup + result.final_markup)


if __name__ == "__main__":
    unittest.main()
