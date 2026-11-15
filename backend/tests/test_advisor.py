import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import summary
from app.advisor import build_report
from app.country_profiles import COUNTRY_PROFILES
from app.main import app
from app.models import CalculationRequest
from app.tooling_catalog import catalog
from test_workbook import workbook_request


def legacy_request(**overrides):
    data = dict(process="plastic_injection", parts_per_mold=2, manufacturing_country="DE", expected_cycles=50_000,
                cycle_band="10000_to_100000", workpiece_material="glass_filled_thermoplastic", includes_cooling=True,
                truck_distance_km=100, part=dict(length_mm=120, width_mm=80, height_mm=30),
                assumptions=COUNTRY_PROFILES["DE"])
    data.update(overrides)
    return CalculationRequest(**data)


def fake_openai(text):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


SUMMARY_JSON = json.dumps({"headline": "Tool costs about EUR 1,800.", "recommendations": ["Use H13."], "watch_outs": ["Thermal fatigue."]})


class AdvisorTests(unittest.TestCase):
    def test_every_workbook_process_builds_a_report(self):
        for process in catalog()["processes"]:
            with self.subTest(process=process["code"]):
                report = build_report(workbook_request(process["code"], 5_000, sizing_mode="part_scaled"))
                self.assertGreater(report.base.total_price, 0)
                self.assertAlmostEqual(sum(d.share for d in report.cost_drivers), 1, places=6)
                self.assertTrue(any(o.is_current for o in report.process_options))
                self.assertEqual(sum(q.is_current for q in report.quantity_options), 1)
                self.assertEqual(len(report.country_options), len(COUNTRY_PROFILES))

    def test_current_estimate_matches_calculate(self):
        request = workbook_request("die_casting", 150_000, workpiece_material="cast_aluminum")
        client = TestClient(app)
        calc = client.post("/api/calculate", json=request.model_dump(mode="json")).json()
        report = client.post("/api/advanced-report", json=request.model_dump(mode="json")).json()
        self.assertAlmostEqual(report["base"]["total_price"], calc["total_price"])
        life = report["tool_life"]
        self.assertAlmostEqual(life["lifetime_cost"], calc["total_price"] + life["replacement_cost"])
        self.assertAlmostEqual(report["tooling_per_part"], life["lifetime_cost"] / 150_000)

    def test_hot_process_prefers_hot_work_steel(self):
        report = build_report(workbook_request("die_casting", 150_000, workpiece_material="cast_aluminum"))
        fits = {o.family: o.fit for o in report.material_options}
        self.assertEqual(fits["hardened_mold_steel"], "strong")
        self.assertEqual(fits["aluminum_tooling"], "not_recommended")
        self.assertIsNone(next(o for o in report.material_options if o.family == "aluminum_tooling").price)

    def test_legacy_material_alternatives_are_priced_differently(self):
        report = build_report(legacy_request())
        prices = {o.family: o.price for o in report.material_options if o.price}
        self.assertIn("aluminum_tooling", prices)
        self.assertLess(prices["aluminum_tooling"], prices["hardened_mold_steel"])
        self.assertEqual(sum(o.is_current for o in report.material_options), 1)

    def test_sheet_parts_only_compare_sheet_processes(self):
        report = build_report(workbook_request("progressive_die_stamping", 200_000, workpiece_material="stainless_steel"))
        codes = {o.process for o in report.process_options}
        self.assertNotIn("metal_injection_molding", codes)
        self.assertNotIn("closed_die_forging", codes)
        self.assertIn("punching_blanking", codes)

    def test_country_comparison_uses_country_defaults(self):
        report = build_report(legacy_request(manufacturing_country="DE"))
        current = next(c for c in report.country_options if c.is_current)
        self.assertEqual(current.code, "DE")
        self.assertAlmostEqual(current.price, report.base.total_price)
        prices = [c.price for c in report.country_options]
        self.assertEqual(prices, sorted(prices))


class SummaryTests(unittest.TestCase):
    def setUp(self):
        summary.reset_state()
        self.client = TestClient(app)
        self.payload = {"request": workbook_request("die_casting", 150_000, workpiece_material="cast_aluminum").model_dump(mode="json")}
        self.env = mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test", "SUMMARY_MODEL": "test-model",
                                                  "SUMMARY_LIMIT_PER_HOUR": "2"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.client.close()

    def test_facts_are_compact(self):
        request = workbook_request("die_casting", 150_000, workpiece_material="cast_aluminum")
        facts = summary.build_facts(build_report(request), request, "EUR", 1.0)
        text = json.dumps(facts, separators=(",", ":"))
        # About four characters per token: keep the input well under 1,000 tokens.
        self.assertLess(len(text), 3000)
        self.assertEqual(facts["tool_price"], round(build_report(request).base.total_price))

    def test_summary_is_cached_and_sends_only_facts(self):
        with mock.patch.object(summary, "_post", return_value=fake_openai(SUMMARY_JSON)) as post:
            first = self.client.post("/api/advanced-report/summary", json=self.payload)
            second = self.client.post("/api/advanced-report/summary", json=self.payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["cached"])
        self.assertTrue(second.json()["cached"])
        self.assertEqual(post.call_count, 1)
        body = post.call_args.args[1]
        self.assertEqual(body["model"], "test-model")
        self.assertFalse(body["store"])
        self.assertLessEqual(body["max_output_tokens"], 900)
        self.assertIn('"tool_price"', body["input"])

    def test_rate_limit(self):
        with mock.patch.object(summary, "_post", return_value=fake_openai(SUMMARY_JSON)):
            codes = []
            for quantity in (150_000, 160_000, 170_000):
                payload = {"request": workbook_request("die_casting", quantity, workpiece_material="cast_aluminum").model_dump(mode="json")}
                codes.append(self.client.post("/api/advanced-report/summary", json=payload).status_code)
        self.assertEqual(codes, [200, 200, 429])

    def test_retries_without_reasoning_when_unsupported(self):
        calls = []

        def post(settings, body):
            calls.append(dict(body))
            if "reasoning" in body:
                raise summary.SummaryUnavailableError("AI summary request failed (400). Unsupported parameter: 'reasoning.effort'.")
            return fake_openai(SUMMARY_JSON)

        with mock.patch.object(summary, "_post", side_effect=post):
            response = self.client.post("/api/advanced-report/summary", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("reasoning", calls[1])

    def test_missing_key_is_503(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            response = self.client.post("/api/advanced-report/summary", json=self.payload)
        self.assertEqual(response.status_code, 503)

    def test_bad_model_reply_is_503(self):
        with mock.patch.object(summary, "_post", return_value=fake_openai("not json")):
            response = self.client.post("/api/advanced-report/summary", json=self.payload)
        self.assertEqual(response.status_code, 503)

    def test_usd_facts(self):
        payload = {**self.payload, "currency": "USD", "eur_to_usd": 2.0}
        with mock.patch.object(summary, "_post", return_value=fake_openai(SUMMARY_JSON)) as post:
            self.client.post("/api/advanced-report/summary", json=payload)
        facts = json.loads(post.call_args.args[1]["input"])
        self.assertEqual(facts["currency"], "USD")


if __name__ == "__main__":
    unittest.main()
