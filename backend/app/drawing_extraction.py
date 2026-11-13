"""Read a part's overall envelope from an engineering drawing (PDF or image).

Two independent sources are combined:

1. The PDF text layer (CAD exports usually contain every dimension as real text).
   It is exact but has no meaning attached: it cannot tell a bore from an outside
   diameter. Image uploads (PNG, JPG, scans...) have no text layer.
2. A vision-language model that looks at the rendered sheet and decides which
   numbers are the overall extents: OpenAI (the default) or a local Ollama
   model (``VISION_PROVIDER=ollama``, offline fallback only).

Every value the model returns is checked against the text layer when there is
one. The result is only a suggestion: the user confirms it before it is used.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError

MM_PER_INCH = 25.4
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_PAGES = 3
RENDER_DPI = 150
MAX_IMAGE_SIDE = 4096
IMAGE_FORMATS = {"PNG", "JPEG", "MPO", "WEBP", "TIFF", "BMP", "GIF"}
SUPPORTED_FORMATS_TEXT = "PDF, PNG, JPG, WEBP, TIFF, BMP or GIF"


class DrawingExtractionError(Exception):
    """The PDF could not be read (bad input: HTTP 422)."""


class VisionUnavailableError(Exception):
    """The vision model could not be reached or answered badly (HTTP 503)."""


@dataclass(frozen=True)
class VisionSettings:
    url: str
    model: str
    timeout_s: float
    provider: Literal["ollama", "openai"] = "openai"
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "VisionSettings":
        provider = os.environ.get("VISION_PROVIDER", "openai").strip().lower()
        if provider == "openai":
            return cls(
                provider="openai",
                url=os.environ.get("VISION_API_URL", "https://api.openai.com/v1").rstrip("/"),
                model=os.environ.get("VISION_MODEL", "gpt-6-luna"),
                api_key=os.environ.get("OPENAI_API_KEY"),
                timeout_s=float(os.environ.get("VISION_TIMEOUT_S", "180")),
            )
        if provider != "ollama":
            raise VisionUnavailableError(f"Unknown VISION_PROVIDER '{provider}'. Use 'ollama' or 'openai'.")
        return cls(
            provider="ollama",
            url=os.environ.get("VISION_API_URL", "http://localhost:11434").rstrip("/"),
            model=os.environ.get("VISION_MODEL", "qwen3-vl:8b-instruct"),
            timeout_s=float(os.environ.get("VISION_TIMEOUT_S", "300")),
        )


# =========================================================
# Model output contract
# =========================================================

class ModelDimension(BaseModel):
    value: float = Field(gt=0)
    unit: Literal["mm", "inch"]
    evidence: str = ""


class DimensionRead(BaseModel):
    printed: str
    unit: Literal["mm", "inch", "unknown"]
    view: str
    measures: str


class ModelReading(BaseModel):
    dimensions_read: list[DimensionRead] = Field(default_factory=list)
    part_name: str | None = None
    material: str | None = None
    shape: Literal["prismatic", "cylindrical", "other"] = "other"
    overall_length: ModelDimension | None = None
    overall_width: ModelDimension | None = None
    overall_height: ModelDimension | None = None
    wall_thickness: ModelDimension | None = None
    missing_or_uncertain: list[str] = Field(default_factory=list)


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


_DIMENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {"type": "number"},
        "unit": {"type": "string", "enum": ["mm", "inch"]},
        "evidence": {"type": "string"},
    },
    "required": ["value", "unit", "evidence"],
    "additionalProperties": False,
}

_DIMENSION_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "printed": {"type": "string"},
        "unit": {"type": "string", "enum": ["mm", "inch", "unknown"]},
        "view": {"type": "string"},
        "measures": {"type": "string"},
    },
    "required": ["printed", "unit", "view", "measures"],
    "additionalProperties": False,
}

MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        # Listed first so the model classifies every dimension before choosing the envelope.
        "dimensions_read": {"type": "array", "items": _DIMENSION_READ_SCHEMA},
        "part_name": _nullable({"type": "string"}),
        "material": _nullable({"type": "string"}),
        "shape": {"type": "string", "enum": ["prismatic", "cylindrical", "other"]},
        "overall_length": _nullable(_DIMENSION_SCHEMA),
        "overall_width": _nullable(_DIMENSION_SCHEMA),
        "overall_height": _nullable(_DIMENSION_SCHEMA),
        "wall_thickness": _nullable(_DIMENSION_SCHEMA),
        "missing_or_uncertain": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
    "required": [
        "dimensions_read", "part_name", "material", "shape", "overall_length", "overall_width",
        "overall_height", "wall_thickness", "missing_or_uncertain",
    ],
}

# Step 1 lets the model look and reason in free text; step 2 (text only) turns
# its notes into JSON. Forcing JSON from the first token made the model either
# refuse or pick feature dimensions (tested on the sample drawings).
DESCRIBE_PROMPT = """This is a mechanical engineering drawing. Work through it step by step.
1. Read the title block: part name, material, and the general unit convention.
2. For each view, list every printed dimension with: the number exactly as printed, its unit (units can be mixed on one sheet - e.g. 3-decimal numbers like 2.000 may be inches while 2-decimal numbers like 25.00 may be mm; use the title block tolerance notes to decide), and what it measures (overall edge-to-edge extent, hole, bore, slot, bolt circle, spacing, thickness...).
3. Say whether the part is prismatic (block/plate) or round (turned).
4. State the overall bounding envelope: length, width and height, each with unit and the view it came from. For a round part use the length along the axis and the largest outside diameter. If an extent is not dimensioned in any view, say so - do not guess.
"""

# Single-call prompt for strong hosted models (structured output, one request).
ENVELOPE_PROMPT = """You are an experienced manufacturing engineer reading a mechanical engineering drawing for a tooling cost estimate.

First, in dimensions_read, list every dimension printed on the sheet: the text exactly as printed (with Ø, R, 4X, depth symbols), its unit, the view it is in, and what it measures (overall extent, thickness, hole, bore, counterbore, slot, keyway, bolt circle, spacing, radius...).
Units can be mixed on one sheet. Decide each value's unit individually from the title block, the tolerance notes and the number format; compare sizes only after converting to a common unit.

Then report the part's overall bounding envelope:
- An overall dimension spans the whole part edge to edge. The views together usually give all three extents.
- Round/turned parts: length along the axis; the largest OUTSIDE diameter is both width and height.
- Never use holes, bores, counterbores, keyways, slots, bolt circles, radii, chamfers or feature spacing as an extent.
- If an extent is not dimensioned in any view, return null and say so in missing_or_uncertain. Do not measure the picture or infer it from proportions.
wall_thickness: main wall or plate thickness only for thin-walled, sheet or plate parts, else null.
material: the title block MATERIAL field exactly, else null.
evidence: short phrase naming the view and the printed text used.
"""

STRUCTURE_PROMPT = """Convert these notes about an engineering drawing into the JSON format. Use only what the notes state as the overall envelope; null for anything the notes say is not dimensioned. Keep units as stated in the notes. wall_thickness only for thin-walled or plate parts. material from the title block, else null. evidence: one short phrase naming the view used.

NOTES:
"""


# =========================================================
# Response contract
# =========================================================

Check = Literal["in_text_layer", "not_in_text_layer", "no_text_layer"]


class ExtractedDimension(BaseModel):
    value_mm: float
    as_printed: float
    unit: Literal["mm", "inch"]
    check: Check
    evidence: str


class ReadDimensionOut(BaseModel):
    printed: str
    unit: Literal["mm", "inch", "unknown"]
    view: str
    measures: str
    check: Check


class MaterialSuggestion(BaseModel):
    as_printed: str
    workpiece_material: str | None


class DrawingExtractionResponse(BaseModel):
    file_name: str
    source_kind: Literal["pdf", "image"]
    pages: int
    model: str
    part_name: str | None
    shape: str
    material: MaterialSuggestion | None
    length: ExtractedDimension | None
    width: ExtractedDimension | None
    height: ExtractedDimension | None
    wall_thickness: ExtractedDimension | None
    dimensions_read: list[ReadDimensionOut]
    warnings: list[str]


# =========================================================
# PDF handling
# =========================================================

_NUMBER = re.compile(r"(?<![\d.])(\d+\.\d+|\d+|\.\d+)(?![\d.])")


def numbers_in(text: str) -> list[float]:
    """Numbers in drawing text, ignoring glued symbols: "n1.125" (CAD font for Ø), "4X", "M5x0.8"."""
    return [float(match) for match in _NUMBER.findall(text)]


def _text_layer_numbers(pdf_bytes: bytes) -> tuple[int, set[float], bool]:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = pdf.pages[:MAX_PAGES]
            text = " ".join(page.extract_text() or "" for page in pages)
            page_count = len(pdf.pages)
    except Exception as exc:  # pdfminer raises many unrelated types
        raise DrawingExtractionError("The file is not a readable PDF.") from exc
    numbers = set(numbers_in(text))
    return page_count, numbers, len(text.strip()) > 0


def _render_pages(pdf_bytes: bytes) -> list[str]:
    try:
        document = pdfium.PdfDocument(pdf_bytes)
    except Exception as exc:
        raise DrawingExtractionError("The file is not a readable PDF.") from exc
    images = []
    for index in range(min(len(document), MAX_PAGES)):
        bitmap = document[index].render(scale=RENDER_DPI / 72)
        buffer = io.BytesIO()
        bitmap.to_pil().save(buffer, "PNG")
        images.append(base64.b64encode(buffer.getvalue()).decode())
    if not images:
        raise DrawingExtractionError("The PDF has no pages.")
    return images


def _flatten(image: Image.Image) -> Image.Image:
    """RGB on white: transparent PNG drawings would otherwise turn black."""
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _image_pages(data: bytes) -> tuple[int, list[str]]:
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in IMAGE_FORMATS:
            raise DrawingExtractionError(f"Unsupported image format. Upload a {SUPPORTED_FORMATS_TEXT} file.")
        # Multi-page TIFFs are drawing sheets; GIF/WEBP frames are animation, so read only the first.
        page_count = getattr(image, "n_frames", 1) if image.format == "TIFF" else 1
        images = []
        for index in range(min(page_count, MAX_PAGES)):
            image.seek(index)
            frame = _flatten(ImageOps.exif_transpose(image))  # phone photos carry a rotation flag
            frame.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            buffer = io.BytesIO()
            frame.save(buffer, "PNG")
            images.append(base64.b64encode(buffer.getvalue()).decode())
    except DrawingExtractionError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise DrawingExtractionError(f"Unsupported or oversized file. Upload a {SUPPORTED_FORMATS_TEXT} drawing.") from exc
    except (OSError, ValueError, EOFError) as exc:
        raise DrawingExtractionError("The image file is damaged or could not be read.") from exc
    return page_count, images


# =========================================================
# Model call
# =========================================================

def _chat(settings: VisionSettings, messages: list[dict], schema: dict | None, max_tokens: int) -> str:
    body = {
        "model": settings.model,
        "stream": False,
        "messages": messages,
        # num_predict caps runaway repetition loops seen at temperature 0.
        "options": {"temperature": 0, "num_ctx": 16384, "num_predict": max_tokens, "repeat_penalty": 1.05},
    }
    if schema is not None:
        body["format"] = schema
    request = urllib.request.Request(
        f"{settings.url}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_s) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VisionUnavailableError(
            f"Vision model at {settings.url} is not reachable. "
            "Start Ollama, or set VISION_API_URL."
        ) from exc
    except json.JSONDecodeError as exc:
        raise VisionUnavailableError("Vision model returned an unreadable reply.") from exc
    if "error" in payload:
        raise VisionUnavailableError(f"Vision model error: {payload['error']}")
    try:
        return payload["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise VisionUnavailableError("Vision model reply did not match the expected format.") from exc


def _post_json(url: str, body: dict, headers: dict, settings: VisionSettings) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_s) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.load(exc).get("error", {}).get("message", "")
        except Exception:
            message = ""
        raise VisionUnavailableError(f"Vision model request failed ({exc.code}). {message}".strip()) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VisionUnavailableError(f"Vision model at {settings.url} is not reachable.") from exc
    except json.JSONDecodeError as exc:
        raise VisionUnavailableError("Vision model returned an unreadable reply.") from exc


def _ask_openai(images: list[str], settings: VisionSettings) -> ModelReading:
    if not settings.api_key:
        raise VisionUnavailableError("OPENAI_API_KEY is not set on the server. Add it to the backend environment variables.")
    content = [{"type": "input_text", "text": ENVELOPE_PROMPT}] + [
        {"type": "input_image", "image_url": f"data:image/png;base64,{image}", "detail": "high"}
        for image in images
    ]
    payload = _post_json(
        f"{settings.url}/responses",
        {
            "model": settings.model,
            "input": [{"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": "drawing_envelope", "schema": MODEL_SCHEMA, "strict": True}},
        },
        {"Authorization": f"Bearer {settings.api_key}"},
        settings,
    )
    texts = [
        part.get("text", "")
        for item in payload.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    if not texts:
        raise VisionUnavailableError("Vision model returned no answer.")
    try:
        return ModelReading.model_validate_json(texts[-1])
    except ValidationError as exc:
        raise VisionUnavailableError("Vision model reply did not match the expected format.") from exc


def _ask_model(images: list[str], settings: VisionSettings) -> ModelReading:
    if settings.provider == "openai":
        return _ask_openai(images, settings)
    notes = _chat(settings, [{"role": "user", "content": DESCRIBE_PROMPT, "images": images}], None, 2500)
    reply = _chat(settings, [{"role": "user", "content": STRUCTURE_PROMPT + notes}], MODEL_SCHEMA, 800)
    try:
        return ModelReading.model_validate_json(reply)
    except ValidationError as exc:
        raise VisionUnavailableError("Vision model reply did not match the expected format.") from exc


# =========================================================
# Post-processing
# =========================================================

_MATERIAL_KEYWORDS = [
    ("stainless", "stainless_steel"),
    ("aluminium", "aluminum_sheet"),
    ("aluminum", "aluminum_sheet"),
    ("brass", "copper_brass"),
    ("copper", "copper_brass"),
    ("cast iron", "cast_iron"),
    ("steel", "mild_steel"),
    ("glass", "glass_filled_thermoplastic"),
    ("gf", "glass_filled_thermoplastic"),
    ("rubber", "elastomer"),
    ("epdm", "elastomer"),
    ("silicone", "elastomer"),
    ("pa6", "standard_thermoplastic"),
    ("abs", "standard_thermoplastic"),
    ("pp", "standard_thermoplastic"),
    ("pe", "standard_thermoplastic"),
    ("pom", "standard_thermoplastic"),
    ("pc", "standard_thermoplastic"),
]


def _keyword_matches(keyword: str, words: list[str], joined: str) -> bool:
    if " " in keyword:
        return keyword in joined
    for word in words:
        if word == keyword:
            return True
        if word.startswith(keyword):
            rest = word[len(keyword):]
            # "gf30", "pa66", "steels" match; "per" must not match "pe".
            if rest.isdigit() or len(keyword) >= 4:
                return True
    return False


def suggest_workpiece_material(printed: str | None) -> MaterialSuggestion | None:
    if not printed or not printed.strip():
        return None
    words = re.findall(r"[a-z0-9]+", printed.lower())
    joined = " ".join(words)
    for keyword, code in _MATERIAL_KEYWORDS:
        if _keyword_matches(keyword, words, joined):
            return MaterialSuggestion(as_printed=printed.strip(), workpiece_material=code)
    return MaterialSuggestion(as_printed=printed.strip(), workpiece_material=None)


def _check(value: float, numbers: set[float], has_text: bool) -> Check:
    if not has_text:
        return "no_text_layer"
    return "in_text_layer" if any(abs(value - n) < 1e-6 for n in numbers) else "not_in_text_layer"


def _convert(dim: ModelDimension | None, numbers: set[float], has_text: bool) -> ExtractedDimension | None:
    if dim is None:
        return None
    factor = MM_PER_INCH if dim.unit == "inch" else 1.0
    return ExtractedDimension(
        value_mm=round(dim.value * factor, 3),
        as_printed=dim.value,
        unit=dim.unit,
        check=_check(dim.value, numbers, has_text),
        evidence=dim.evidence,
    )


def _check_printed(printed: str, numbers: set[float], has_text: bool) -> Check:
    if not has_text:
        return "no_text_layer"
    values = numbers_in(printed)
    if values and all(any(abs(v - n) < 1e-6 for n in numbers) for v in values):
        return "in_text_layer"
    return "not_in_text_layer"


def build_response(
    file_name: str,
    page_count: int,
    numbers: set[float],
    has_text: bool,
    reading: ModelReading,
    model: str,
    source_kind: Literal["pdf", "image"] = "pdf",
) -> DrawingExtractionResponse:
    warnings = list(reading.missing_or_uncertain)
    extents = [
        _convert(d, numbers, has_text)
        for d in (reading.overall_length, reading.overall_width, reading.overall_height)
    ]
    if reading.shape == "cylindrical":
        # Round parts: the diameter is both width and height.
        present = [e for e in extents[1:] if e is not None]
        if len(present) == 1:
            extents[1] = extents[2] = present[0]
    # Largest first, so length >= width >= height; missing values go last.
    known = sorted((e for e in extents if e is not None), key=lambda e: -e.value_mm)
    extents = known + [None] * (3 - len(known))
    if len(known) < 3:
        warnings.append("Not every overall extent is dimensioned. Enter the missing value by hand.")
    if page_count > MAX_PAGES:
        warnings.append(f"Only the first {MAX_PAGES} of {page_count} pages were read.")
    if source_kind == "image":
        warnings.append("Image upload: values were read from the picture only and could not be cross-checked against drawing text.")
    elif not has_text:
        warnings.append("The PDF has no text layer (scanned drawing). Values could not be cross-checked.")
    for name, extent in zip(("Length", "Width", "Height"), extents):
        if extent is not None and extent.check == "not_in_text_layer":
            warnings.append(f"{name} {extent.as_printed} does not appear in the drawing text. Check it.")
    if page_count > 1:
        warnings.append("Multi-page drawing: confirm the values belong to the same part.")
    return DrawingExtractionResponse(
        file_name=file_name,
        source_kind=source_kind,
        pages=page_count,
        model=model,
        part_name=reading.part_name,
        shape=reading.shape,
        material=suggest_workpiece_material(reading.material),
        length=extents[0],
        width=extents[1],
        height=extents[2],
        wall_thickness=_convert(reading.wall_thickness, numbers, has_text),
        dimensions_read=[
            ReadDimensionOut(**d.model_dump(), check=_check_printed(d.printed, numbers, has_text))
            for d in reading.dimensions_read
        ],
        warnings=warnings,
    )


def extract_dimensions(
    data: bytes,
    file_name: str,
    settings: VisionSettings | None = None,
) -> DrawingExtractionResponse:
    if not data:
        raise DrawingExtractionError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise DrawingExtractionError("The file is larger than 15 MB.")
    settings = settings or VisionSettings.from_env()
    if data.startswith(b"%PDF"):
        page_count, numbers, has_text = _text_layer_numbers(data)
        images = _render_pages(data)
        source_kind = "pdf"
    else:
        page_count, images = _image_pages(data)
        numbers, has_text, source_kind = set(), False, "image"
    reading = _ask_model(images, settings)
    return build_response(file_name, page_count, numbers, has_text, reading, settings.model, source_kind)
