import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import fx
from app.advisor import build_report
from app.country_profiles import COUNTRY_PROFILES, assumptions_in_eur
from app.main import app
from conftest import SAMPLE_ECB_XML
from test_workbook import workbook_request


class FxTests(unittest.TestCase):
    def test_parses_ecb_file(self):
        rate = fx.parse_ecb_xml(SAMPLE_ECB_XML)
        self.assertEqual((rate.rate, rate.date, rate.quote), (1.16, "2026-11-13", "USD"))
        self.assertIn("European Central Bank", rate.source)

    def test_rejects_bad_files(self):
        for payload in (b"not xml", b"<Cube><Cube time='2026-11-13'><Cube currency='JPY' rate='170'/></Cube></Cube>",
                        b"<Cube><Cube time='2026-11-13'><Cube currency='USD' rate='116'/></Cube></Cube>"):
            with self.subTest(payload=payload), self.assertRaises(fx.FxUnavailableError):
                fx.parse_ecb_xml(payload)

    def test_endpoint(self):
        response = TestClient(app).get("/api/fx/eur-usd")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rate"], 1.16)
        self.assertFalse(response.json()["stale"])

    def test_cached_and_stale_fallback(self):
        calls = []
        def download():
            calls.append(1)
            return SAMPLE_ECB_XML
        with mock.patch.object(fx, "_download", download):
            fx.eur_usd()
            fx.eur_usd()
        self.assertEqual(len(calls), 1)
        # After the refresh interval a failed download keeps the last rate, marked stale.
        fx._cached = (time.time() - fx.REFRESH_S - 1, fx._cached[1])
        with mock.patch.object(fx, "_download", side_effect=fx.FxUnavailableError("down")):
            self.assertTrue(fx.eur_usd().stale)
            fx._cached = (time.time() - fx.MAX_STALE_S - 1, fx._cached[1])
            response = TestClient(app).get("/api/fx/eur-usd")
        self.assertEqual(response.status_code, 503)

    def test_usd_country_rates_convert_to_eur(self):
        euros = assumptions_in_eur("CN", 1.25)
        self.assertAlmostEqual(euros["cnc_3_axis_rate"], COUNTRY_PROFILES["CN"]["cnc_3_axis_rate"] / 1.25)
        self.assertEqual(euros["machine_efficiency"], COUNTRY_PROFILES["CN"]["machine_efficiency"])
        self.assertEqual(assumptions_in_eur("DE", None)["cnc_3_axis_rate"], COUNTRY_PROFILES["DE"]["cnc_3_axis_rate"])
        with self.assertRaises(ValueError):
            assumptions_in_eur("IN", None)

    def test_countries_list_currency(self):
        countries = {c["code"]: c["currency"] for c in TestClient(app).get("/api/countries").json()}
        self.assertEqual(countries["CN"], "USD")
        self.assertEqual(countries["IN"], "USD")
        self.assertEqual(countries["DE"], "EUR")

    def test_report_prices_usd_countries_with_the_clients_rate(self):
        request = workbook_request("die_casting", 50_000, workpiece_material="cast_aluminum")
        cheap_dollar = {c.code: c.price for c in build_report(request.model_copy(update={"eur_to_usd": 2.0})).country_options}
        dear_dollar = {c.code: c.price for c in build_report(request.model_copy(update={"eur_to_usd": 1.0})).country_options}
        # More dollars per euro makes USD rates cheaper in euros; EUR countries do not move.
        self.assertLess(cheap_dollar["CN"], dear_dollar["CN"])
        self.assertAlmostEqual(cheap_dollar["FR"], dear_dollar["FR"])

    def test_selected_usd_country_round_trips(self):
        # The client sends CN rates converted with its rate; the report's CN price equals the calculation.
        request = workbook_request("die_casting", 50_000, workpiece_material="cast_aluminum", manufacturing_country="CN",
                                   assumptions=assumptions_in_eur("CN", 1.16), eur_to_usd=1.16)
        report = build_report(request)
        cn = next(c for c in report.country_options if c.code == "CN")
        self.assertTrue(cn.is_current)
        self.assertEqual(cn.currency, "USD")
        self.assertAlmostEqual(cn.price, report.base.total_price)

    def test_usd_countries_unpriced_without_any_rate(self):
        with mock.patch.object(fx, "_download", side_effect=fx.FxUnavailableError("down")):
            report = build_report(workbook_request("die_casting", 50_000, workpiece_material="cast_aluminum"))
        prices = {c.code: c.price for c in report.country_options}
        self.assertIsNone(prices["CN"])
        self.assertIsNotNone(prices["DE"])


if __name__ == "__main__":
    unittest.main()
