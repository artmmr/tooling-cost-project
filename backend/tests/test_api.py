import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.tooling_catalog import catalog
from test_workbook import workbook_request


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_catalog_and_cost_profiles(self):
        response = self.client.get("/api/tooling-catalog")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["processes"]), 21)
        self.assertEqual(len(response.json()["quantity_bands"]), 6)
        self.assertEqual(len(response.json()["glossary"]), 7)
        self.assertEqual(len(response.json()["sizing_steps"]), 7)
        self.assertEqual(len(response.json()["review_checklist"]), 6)
        self.assertEqual(len(response.json()["worked_example"]), 10)
        self.assertNotIn("provenance", response.text)
        self.assertEqual(self.client.get("/api/tooling-materials").status_code, 200)

    def test_every_process_and_quantity_over_http(self):
        for grade in catalog()["grades"]:
            with self.subTest(process=grade["process"], quantity=grade["quantity_min"]):
                payload = workbook_request(grade["process"], grade["quantity_min"]).model_dump(mode="json")
                response = self.client.post("/api/calculate", json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertEqual(data["tooling_quantity_band"], grade["band"])
                self.assertEqual(data["grade_candidates"], grade["candidates"])

    def test_validation_errors_are_422(self):
        for override in [dict(component_id="wrong"), dict(component_id="P03-C01", rounding_mm=0),
                         dict(component_id="P03-C01", manufacturing_route=dict(cnc_3_axis_share=1,cnc_5_axis_share=1,edm_share=0,grinding_share=0))]:
            payload = workbook_request().model_dump(mode="json")
            payload["block_overrides"] = [override]
            response = self.client.post("/api/calculate", json=payload)
            self.assertEqual(response.status_code, 422)

    def test_legacy_clients_still_work(self):
        from test_calculator import example
        response = self.client.post("/api/calculate", json=example().model_dump(mode="json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["calculation_basis"], "legacy")

    def test_frontend_origin_preflight(self):
        response = self.client.options("/api/calculate", headers={
            "Origin": "https://frabjous-parfait-6e9800.netlify.app",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "https://frabjous-parfait-6e9800.netlify.app")


if __name__ == "__main__":
    unittest.main()
