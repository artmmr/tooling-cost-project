import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import summary
from app.advisor import build_report
from app.main import app
from app.models import WorkpieceMaterial
from app.process_matrix import (GRADE_FAMILY, ROW_WORKPIECE, auto_row_id, band_index, interpret_row, matrix,
                                route_processes, tooling_grades)
from app.tooling_catalog import is_workbook_process
from app.tooling_materials import TOOLING_MATERIALS
from test_workbook import workbook_request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
from import_process_matrix import build  # noqa: E402


def cell(row_id, band):
    entry = next(r for r in matrix()["rows"] if r["id"] == row_id)
    return interpret_row(entry)[band], entry["bands"][band]


class MatrixDataTests(unittest.TestCase):
    def test_json_matches_the_workbook(self):
        workbook = ROOT / "data" / "Industrialisation_Process_Tooling_Matrix_EN.xlsx"
        fresh = build(workbook)
        committed = matrix()
        self.assertEqual(fresh["rows"], committed["rows"])
        self.assertEqual(fresh["grades"], committed["grades"])
        self.assertEqual(fresh["index_basket"], committed["index_basket"])
        self.assertEqual(len(committed["rows"]), 23)
        self.assertEqual(len(committed["grades"]), 13)

    def test_bands_match_the_v4_quantity_bands(self):
        from app.tooling_catalog import public_catalog
        v4 = [(b["quantity_min"], b["quantity_max"]) for b in public_catalog()["quantity_bands"]]
        self.assertEqual([(b["quantity_min"], b["quantity_max"]) for b in matrix()["bands"]], v4)
        self.assertEqual([band_index(q) for q in (1, 20, 21, 1000, 1001, 100000, 100001, 10**7)], [0, 0, 1, 2, 3, 4, 5, 5])

    def test_every_cell_is_interpreted(self):
        for entry in matrix()["rows"]:
            for band, (parsed, raw) in enumerate(zip(interpret_row(entry), entry["bands"])):
                with self.subTest(row=entry["id"], band=band):
                    self.assertEqual(parsed["unknown"], [], raw)
                    self.assertTrue(parsed["codes"] or parsed["unpriced"] or parsed["no_tooling"], raw)
                    for code in parsed["codes"]:
                        self.assertTrue(is_workbook_process(code) or code == "plastic_injection", code)

    def test_every_named_grade_is_in_the_grade_table_and_costed(self):
        names = {g["name"] for g in matrix()["grades"]}
        self.assertEqual(set(GRADE_FAMILY), names)
        for family in filter(None, GRADE_FAMILY.values()):
            self.assertIn(family, TOOLING_MATERIALS)
        for entry in matrix()["rows"]:
            for raw in entry["bands"]:
                for grade in tooling_grades(raw["tooling"]):
                    self.assertIn(grade, names)

    def test_known_cells(self):
        parsed, _ = cell("aluminium_complex_part", 5)
        self.assertEqual(parsed["codes"], ["die_casting"])
        self.assertEqual(parsed["grades"], ["Premium H13 / ESR"])
        parsed, _ = cell("carbon_steel_sheet_metal", 3)
        self.assertEqual(parsed["codes"], ["punching_blanking"])
        self.assertEqual(parsed["grades"], ["D2 / 1.2379"])
        self.assertTrue(cell("abs_thermoplastic", 0)[0]["no_tooling"])
        self.assertTrue(cell("carbon_steel_solid", 2)[0]["no_tooling"])  # CNC with C45 fixtures
        self.assertEqual(cell("pvc_corrosive_thermoplastic", 5)[0]["grades"], ["1.2083 ESR"])
        self.assertEqual(cell("pvc_corrosive_thermoplastic", 4)[0]["codes"], ["plastic_injection", "plastic_extrusion"])
        self.assertEqual(cell("aluminium_profile", 3)[0]["codes"], ["metal_extrusion"])
        self.assertEqual(cell("aluminium_complex_part", 3)[0]["unpriced"], ["Gravity / low-pressure casting (permanent mold)"])
        self.assertEqual(cell("stainless_steel_solid", 4)[0]["codes"], ["closed_die_forging", "investment_casting"])
        # "High volume" repeats the previous band's process.
        self.assertEqual(cell("brass_sheet_solid", 5)[0]["codes"], ["progressive_die_stamping"])
        self.assertEqual(route_processes("pp_pe_thermoplastic", "Injection molding", "P20")["codes"], ["plastic_injection"])

    def test_part_material_mapping(self):
        for material in WorkpieceMaterial:
            row_id = auto_row_id(material.value, "die_casting")
            if row_id:
                self.assertIn(row_id, ROW_WORKPIECE)
        self.assertEqual(auto_row_id("stainless_steel", "progressive_die_stamping"), "stainless_steel_sheet_metal")
        self.assertEqual(auto_row_id("stainless_steel", "investment_casting"), "stainless_steel_solid")
        self.assertEqual(auto_row_id("cast_aluminum", "metal_extrusion"), "aluminium_profile")
        self.assertEqual(auto_row_id("corrosive_polymer", "plastic_injection"), "pvc_corrosive_thermoplastic")
        self.assertIsNone(auto_row_id("cast_iron", "sand_casting"))
        for row_id, material in ROW_WORKPIECE.items():
            WorkpieceMaterial(material)


class MatrixReportTests(unittest.TestCase):
    def test_high_volume_die_casting_follows_matrix(self):
        report = build_report(workbook_request("die_casting", 150_000, workpiece_material="cast_aluminum"))
        self.assertTrue(report.matrix.covered)
        self.assertEqual(report.matrix.route, "High-volume HPDC")
        self.assertTrue(report.matrix.current_process_listed)
        self.assertEqual([g.name for g in report.matrix.grades], ["Premium H13 / ESR"])
        current = next(o for o in report.process_options if o.is_current)
        self.assertEqual(current.fit, "strong")
        self.assertIn("Process matrix", current.notes[0])
        hardened = next(o for o in report.material_options if o.family == "hardened_mold_steel")
        self.assertEqual(hardened.fit, "strong")
        self.assertIn("Premium H13 / ESR", hardened.reasons[1])

    def test_low_volume_recommends_no_tool(self):
        report = build_report(workbook_request("die_casting", 50, workpiece_material="cast_aluminum"))
        self.assertFalse(report.matrix.current_process_listed)
        self.assertEqual(report.matrix.current_process_band, "10,001–100,000")
        no_tool = next(o for o in report.process_options if o.process == "no_dedicated_tooling")
        self.assertEqual((no_tool.fit, no_tool.tooling_price), ("strong", 0))
        die = next(o for o in report.process_options if o.is_current)
        self.assertEqual(die.fit, "limited")
        self.assertTrue(any("process matrix recommends CNC" in n for n in report.design_notes))

    def test_chosen_material_detail_overrides_auto_mapping(self):
        request = workbook_request("compression_molding", 50_000, workpiece_material="elastomer",
                                   part_material_detail="silicone_lsr_elastomer")
        report = build_report(request)
        self.assertEqual((report.matrix.material, report.matrix.chosen_by), ("Silicone / LSR", "user"))
        injection = next(o for o in report.process_options if o.process == "plastic_injection")
        self.assertEqual(injection.fit, "strong")
        self.assertIsNotNone(injection.tooling_price)

    def test_uncovered_material(self):
        report = build_report(workbook_request("sand_casting", 500, workpiece_material="cast_iron"))
        self.assertFalse(report.matrix.covered)
        self.assertTrue(report.matrix.message)

    def test_api(self):
        client = TestClient(app)
        data = client.get("/api/process-matrix").json()
        self.assertEqual(len(data["rows"]), 23)
        self.assertEqual(len(data["bands"]), 6)
        payload = workbook_request("die_casting", 500, workpiece_material="cast_aluminum").model_dump(mode="json")
        payload["part_material_detail"] = "unobtainium"
        self.assertEqual(client.post("/api/advanced-report", json=payload).status_code, 422)
        payload["part_material_detail"] = "zinc_die_casting"
        body = client.post("/api/advanced-report", json=payload).json()
        self.assertEqual(body["matrix"]["material"], "Zinc")
        self.assertEqual(client.post("/api/calculate", json=payload).status_code, 200)

    def test_summary_facts_include_matrix(self):
        request = workbook_request("die_casting", 150_000, workpiece_material="cast_aluminum")
        facts = summary.build_facts(build_report(request), request, "EUR", 1.0)
        self.assertEqual(facts["process_matrix"]["route"], "High-volume HPDC")
        self.assertLess(len(json.dumps(facts, separators=(",", ":"))), 3600)


if __name__ == "__main__":
    unittest.main()
