import base64
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import drawing_extraction as de
from app.main import app

BLUEPRINTS = Path(__file__).resolve().parents[3] / "blueprints"


def reading(**overrides):
    base = {
        "part_name": "BALL SCREW CAP, AFT",
        "material": "STEEL",
        "shape": "prismatic",
        "overall_length": {"value": 2.0, "unit": "inch", "evidence": "front view"},
        "overall_width": {"value": 2.0, "unit": "inch", "evidence": "front view"},
        "overall_height": {"value": 0.375, "unit": "inch", "evidence": "side view"},
        "wall_thickness": None,
        "missing_or_uncertain": [],
    }
    base.update(overrides)
    return de.ModelReading.model_validate(base)


class BuildResponseTests(unittest.TestCase):
    numbers = {2.0, 0.375, 1.5, 25.0, 1.125}

    def test_converts_inches_and_checks_text_layer(self):
        result = de.build_response("a.pdf", 1, self.numbers, True, reading(), "m")
        self.assertAlmostEqual(result.length.value_mm, 50.8)
        self.assertAlmostEqual(result.height.value_mm, 9.525)
        self.assertEqual(result.length.check, "in_text_layer")
        self.assertEqual(result.material.workpiece_material, "mild_steel")
        self.assertEqual(result.warnings, [])

    def test_sorts_largest_first_and_flags_unknown_number(self):
        r = reading(overall_length={"value": 0.375, "unit": "inch", "evidence": ""},
                    overall_height={"value": 3.5, "unit": "inch", "evidence": ""})
        result = de.build_response("a.pdf", 1, self.numbers, True, r, "m")
        self.assertEqual([result.length.as_printed, result.width.as_printed, result.height.as_printed], [3.5, 2.0, 0.375])
        self.assertEqual(result.length.check, "not_in_text_layer")
        self.assertTrue(any("3.5" in w for w in result.warnings))

    def test_cylinder_diameter_fills_width_and_height(self):
        r = reading(shape="cylindrical",
                    overall_width={"value": 1.125, "unit": "inch", "evidence": ""},
                    overall_height=None)
        result = de.build_response("a.pdf", 1, self.numbers, True, r, "m")
        self.assertAlmostEqual(result.width.value_mm, 28.575)
        self.assertAlmostEqual(result.height.value_mm, 28.575)

    def test_missing_extent_is_left_empty_with_warning(self):
        result = de.build_response("a.pdf", 1, self.numbers, True, reading(overall_height=None), "m")
        self.assertIsNone(result.height)
        self.assertTrue(any("missing" in w for w in result.warnings))

    def test_no_text_layer(self):
        result = de.build_response("a.pdf", 1, set(), False, reading(), "m")
        self.assertEqual(result.length.check, "no_text_layer")

    def test_material_mapping(self):
        self.assertEqual(de.suggest_workpiece_material("AISI 304 Stainless").workpiece_material, "stainless_steel")
        self.assertEqual(de.suggest_workpiece_material("PA66 GF30").workpiece_material, "glass_filled_thermoplastic")
        self.assertIsNone(de.suggest_workpiece_material("Unobtainium").workpiece_material)
        self.assertIsNone(de.suggest_workpiece_material("  "))


@unittest.skipUnless((BLUEPRINTS / "A1220.pdf").exists(), "sample drawings not present")
class PdfTests(unittest.TestCase):
    def test_text_layer_reads_cad_numbers_and_diameter_glyph(self):
        pages, numbers, has_text = de._text_layer_numbers((BLUEPRINTS / "A1312.pdf").read_bytes())
        self.assertEqual(pages, 1)
        self.assertTrue(has_text)
        self.assertTrue({2.0, 1.125, 25.0, 16.0, 0.5}.issubset(numbers))

    def test_render(self):
        self.assertEqual(len(de._render_pages((BLUEPRINTS / "A1220.pdf").read_bytes())), 1)


def image_bytes(fmt, mode="RGB", color="white", size=(40, 30), **save):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, fmt, **save)
    return buffer.getvalue()


class ImageInputTests(unittest.TestCase):
    def decoded(self, b64):
        from PIL import Image
        return Image.open(io.BytesIO(base64.b64decode(b64)))

    def test_common_formats_become_png(self):
        for fmt in ("PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF"):
            with self.subTest(fmt=fmt):
                pages, images = de._image_pages(image_bytes(fmt))
                self.assertEqual((pages, len(images)), (1, 1))
                self.assertEqual(self.decoded(images[0]).format, "PNG")

    def test_transparent_background_becomes_white(self):
        _, images = de._image_pages(image_bytes("PNG", mode="RGBA", color=(0, 0, 0, 0)))
        self.assertEqual(self.decoded(images[0]).getpixel((0, 0)), (255, 255, 255))

    def test_multipage_tiff_and_large_image(self):
        from PIL import Image
        buffer = io.BytesIO()
        frames = [Image.new("RGB", (5000, 100), "white") for _ in range(4)]
        frames[0].save(buffer, "TIFF", save_all=True, append_images=frames[1:])
        pages, images = de._image_pages(buffer.getvalue())
        self.assertEqual((pages, len(images)), (4, de.MAX_PAGES))
        self.assertEqual(self.decoded(images[0]).size[0], de.MAX_IMAGE_SIDE)

    def test_rejects_unknown_and_damaged_files(self):
        for data in (b"hello world", image_bytes("PNG")[:40], image_bytes("ICO")):
            with self.assertRaises(de.DrawingExtractionError):
                de._image_pages(data)

    def test_image_upload_flow(self):
        with mock.patch.object(de, "_ask_model", return_value=reading()):
            result = de.extract_dimensions(image_bytes("JPEG"), "photo.jpg", de.VisionSettings("u", "m", 1))
        self.assertEqual(result.source_kind, "image")
        self.assertEqual(result.length.check, "no_text_layer")
        self.assertTrue(any("Image upload" in w for w in result.warnings))


class DimensionsReadTests(unittest.TestCase):
    def test_numbers_in_ignores_glued_symbols(self):
        self.assertEqual(de.numbers_in("4X M5x0.8 n1.125 R0.125 .375"), [4, 5, 0.8, 1.125, 0.125, 0.375])

    def test_each_read_dimension_is_checked(self):
        r = reading(dimensions_read=[
            {"printed": "4X Ø0.190 THRU", "unit": "inch", "view": "front", "measures": "hole"},
            {"printed": "Ø9.99", "unit": "mm", "view": "front", "measures": "bore"},
        ])
        result = de.build_response("a.pdf", 1, {4.0, 0.19, 2.0, 0.375}, True, r, "m")
        self.assertEqual([d.check for d in result.dimensions_read], ["in_text_layer", "not_in_text_layer"])

    def test_short_material_codes_need_exact_match(self):
        self.assertIsNone(de.suggest_workpiece_material("per customer spec").workpiece_material)
        self.assertEqual(de.suggest_workpiece_material("PP copolymer").workpiece_material, "standard_thermoplastic")
        self.assertEqual(de.suggest_workpiece_material("PA66-GF30").workpiece_material, "glass_filled_thermoplastic")


class OpenAIProviderTests(unittest.TestCase):
    settings = de.VisionSettings(url="https://api.example/v1", model="gpt-6-luna", timeout_s=5,
                                 provider="openai", api_key="sk-test")

    def test_parses_responses_api_output(self):
        reply = reading().model_dump_json()
        payload = {"output": [{"type": "reasoning"},
                              {"type": "message", "content": [{"type": "output_text", "text": reply}]}]}
        with mock.patch.object(de, "_post_json", return_value=payload) as post:
            result = de._ask_model(["abc"], self.settings)
        self.assertEqual(result.overall_length.value, 2.0)
        url, body, headers, _ = post.call_args.args
        self.assertEqual(url, "https://api.example/v1/responses")
        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(headers["Authorization"], "Bearer sk-test")

    def test_missing_key(self):
        settings = de.VisionSettings(url="u", model="m", timeout_s=1, provider="openai", api_key=None)
        with self.assertRaises(de.VisionUnavailableError):
            de._ask_model(["abc"], settings)

    def test_settings_from_env(self):
        with mock.patch.dict(os.environ, {"VISION_PROVIDER": "openai", "OPENAI_API_KEY": "k"}, clear=False):
            settings = de.VisionSettings.from_env()
        self.assertEqual((settings.provider, settings.model, settings.api_key), ("openai", "gpt-6-luna", "k"))
        with mock.patch.dict(os.environ, {"VISION_PROVIDER": "nope"}):
            with self.assertRaises(de.VisionUnavailableError):
                de.VisionSettings.from_env()


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_rejects_unsupported_file(self):
        response = self.client.post("/api/extract-dimensions", files={"file": ("a.pdf", b"hello", "application/pdf")})
        self.assertEqual(response.status_code, 422)

    @unittest.skipUnless((BLUEPRINTS / "A1220.pdf").exists(), "sample drawings not present")
    def test_model_unreachable_is_503(self):
        settings = de.VisionSettings(url="http://127.0.0.1:9", model="x", timeout_s=2)
        with mock.patch.object(de.VisionSettings, "from_env", return_value=settings):
            response = self.client.post("/api/extract-dimensions",
                                        files={"file": ("A1220.pdf", (BLUEPRINTS / "A1220.pdf").read_bytes(), "application/pdf")})
        self.assertEqual(response.status_code, 503)
        self.assertIn("not reachable", response.json()["detail"])

    @unittest.skipUnless((BLUEPRINTS / "A1220.pdf").exists(), "sample drawings not present")
    def test_full_flow_with_mocked_model(self):
        with mock.patch.object(de, "_ask_model", return_value=reading()):
            response = self.client.post("/api/extract-dimensions",
                                        files={"file": ("A1220.pdf", (BLUEPRINTS / "A1220.pdf").read_bytes(), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["length"]["check"], "in_text_layer")
        self.assertAlmostEqual(body["height"]["value_mm"], 9.525)


if __name__ == "__main__":
    unittest.main()
