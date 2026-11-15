"""Short AI-written summary of an advanced report.

Token cost is kept low by design:

* The model never sees the drawing or the full report, only a compact set of
  facts (roughly 400-600 input tokens) computed by ``app.advisor``.
* The reply is a small strict JSON object with a hard output-token cap.
* Identical requests are answered from an in-memory cache.
* Requests are rate limited per client and capped per day, because the
  endpoint is public and each call is billed.

The endpoint only accepts a calculation request, never free text, so it cannot
be used as a general-purpose chat proxy.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict, deque
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.advisor import AdvancedReport, build_report
from app.models import CalculationRequest


class SummaryUnavailableError(Exception):
    """The model could not be reached or answered badly (HTTP 503)."""


class SummaryRateLimitError(Exception):
    """Too many summaries requested (HTTP 429)."""


class SummaryRequest(BaseModel):
    request: CalculationRequest
    currency: Literal["EUR", "USD"] = "EUR"
    eur_to_usd: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class Summary(BaseModel):
    headline: str
    recommendations: list[str]
    watch_outs: list[str]


class SummaryResponse(Summary):
    model: str
    cached: bool = False


SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "recommendations", "watch_outs"],
    "properties": {
        "headline": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "watch_outs": {"type": "array", "items": {"type": "string"}},
    },
}

INSTRUCTIONS = (
    "You are a tooling cost engineer. Using ONLY the JSON facts, write advice for a buyer.\n"
    "headline: 1 sentence, the price and the main cost driver.\n"
    "If tool_life shows replacement sets, mention them and the lifetime cost.\n"
    "recommendations: 3-4 items, each 1-2 sentences: best tooling material, part process choice, "
    "cheapest country and quantity strategy, citing numbers from the facts; follow process_matrix when present.\n"
    "watch_outs: 2-3 short items from risks and notes.\n"
    "Never invent numbers or facts. Plain English, no markdown. Fit labels: strong>suitable>limited."
)


# =========================================================
# Settings
# =========================================================

def _settings() -> dict:
    return {
        "url": os.environ.get("SUMMARY_API_URL", os.environ.get("VISION_API_URL", "https://api.openai.com/v1")).rstrip("/"),
        "model": os.environ.get("SUMMARY_MODEL", os.environ.get("VISION_MODEL", "gpt-6-luna")),
        "api_key": os.environ.get("OPENAI_API_KEY"),
        "timeout_s": float(os.environ.get("SUMMARY_TIMEOUT_S", "60")),
        "max_output_tokens": int(os.environ.get("SUMMARY_MAX_OUTPUT_TOKENS", "900")),
        # "none" skips reasoning tokens entirely: the summary only rewrites computed facts.
        "reasoning": os.environ.get("SUMMARY_REASONING_EFFORT", "none").strip(),
        "per_client_hour": int(os.environ.get("SUMMARY_LIMIT_PER_HOUR", "12")),
        "per_day": int(os.environ.get("SUMMARY_LIMIT_PER_DAY", "300")),
    }


# =========================================================
# Facts given to the model
# =========================================================

def _r(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    value *= factor
    return round(value) if abs(value) >= 100 else round(value, 3)


def build_facts(report: AdvancedReport, request: CalculationRequest, currency: str, factor: float) -> dict:
    base = report.base
    part = request.part
    countries = [c for c in report.country_options if c.price is not None]
    current_country = next((c for c in countries if c.is_current), None)
    cheapest = countries[:3] + ([current_country] if current_country and current_country not in countries[:3] else [])
    return {
        "currency": currency,
        "process": request.process.value,
        "part_material": request.workpiece_material.value,
        "part_mm": [round(part.length_mm, 1), round(part.width_mm, 1), round(part.height_mm, 1)],
        "wall_or_sheet_mm": request.material_thickness_mm,
        "quantity": report.quantity,
        "tool_sets": request.parts_per_mold,
        "tolerance": request.tolerance_level.value,
        "finish": request.surface_finish.value,
        "country": request.manufacturing_country,
        "tool_price": _r(base.total_price, factor),
        "tool_cost_per_part": _r(report.tooling_per_part, factor),
        "tool_life": ({"typical_life_cycles": report.tool_life.life, "cycles_per_tool": report.tool_life.shots,
                       "replacement_sets": report.tool_life.replacements,
                       "lifetime_tooling_cost": _r(report.tool_life.lifetime_cost, factor)}
                      if report.tool_life.modelled else None),
        "tool_concept": base.tooling_concept or None,
        "cost_share_pct": {d.label: round(d.share * 100) for d in report.cost_drivers[:4]},
        "tooling_materials": [
            [o.name, o.fit, _r(o.price, factor), "current" if o.is_current else ""]
            for o in report.material_options if o.fit != "not_recommended"
        ][:5],
        "part_processes": [
            [o.label, o.fit, _r(o.tooling_price, factor), "piece cost " + o.piece_cost, "current" if o.is_current else ""]
            for o in report.process_options if o.fit != "not_recommended"
        ][:5],
        "countries": [[c.name, _r(c.price, factor), "current" if c.is_current else ""] for c in cheapest],
        "quantity_bands": [[q.band, _r(q.price, factor), "current" if q.is_current else ""] for q in report.quantity_options],
        "process_matrix": ({"material": f"{report.matrix.material} ({report.matrix.form})", "route": report.matrix.route,
                            "tooling": report.matrix.tooling, "your_process_listed": report.matrix.current_process_listed}
                           if report.matrix.covered else None),
        "risks": [r.risk for r in report.risks][:4],
        "design_notes": report.design_notes[:3],
    }


# =========================================================
# Abuse protection and cache
# =========================================================

_lock = threading.Lock()
_cache: OrderedDict[str, Summary] = OrderedDict()
_client_calls: dict[str, deque] = {}
_day_calls: deque = deque()
CACHE_SIZE = 256


def _check_limits(client: str, settings: dict) -> None:
    now = time.time()
    with _lock:
        while _day_calls and now - _day_calls[0] > 86_400:
            _day_calls.popleft()
        calls = _client_calls.setdefault(client, deque())
        while calls and now - calls[0] > 3_600:
            calls.popleft()
        if len(_day_calls) >= settings["per_day"]:
            raise SummaryRateLimitError("The daily AI summary limit has been reached. Try again tomorrow.")
        if len(calls) >= settings["per_client_hour"]:
            raise SummaryRateLimitError("Too many AI summaries requested. Try again in an hour.")
        calls.append(now)
        _day_calls.append(now)
        if len(_client_calls) > 5_000:  # Drop idle clients so memory stays bounded.
            for key in [k for k, v in _client_calls.items() if not v]:
                del _client_calls[key]


def reset_state() -> None:
    """Clear cache and counters (tests)."""
    with _lock:
        _cache.clear()
        _client_calls.clear()
        _day_calls.clear()


# =========================================================
# Model call
# =========================================================

def _post(settings: dict, body: dict) -> dict:
    request = urllib.request.Request(
        f"{settings['url']}/responses", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings['api_key']}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings["timeout_s"]) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.load(exc).get("error", {}).get("message", "")
        except Exception:
            message = ""
        raise SummaryUnavailableError(f"AI summary request failed ({exc.code}). {message}".strip()) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SummaryUnavailableError("The AI summary service is not reachable.") from exc
    except json.JSONDecodeError as exc:
        raise SummaryUnavailableError("The AI summary service returned an unreadable reply.") from exc


EFFORT_PREFERENCE = ("none", "minimal", "low")


def cheapest_supported_effort(message: str) -> str | None:
    """Lowest reasoning effort named in an API error such as "Supported values are: 'none', 'low'..."."""
    if "supported values" not in message.lower():
        return None
    listed = set(re.findall(r"'([a-z]+)'", message.split("upported values", 1)[1]))
    return next((effort for effort in EFFORT_PREFERENCE if effort in listed), None)


def _ask_model(facts: dict, settings: dict) -> Summary:
    if not settings["api_key"]:
        raise SummaryUnavailableError("OPENAI_API_KEY is not set on the server.")
    body = {
        "model": settings["model"],
        "instructions": INSTRUCTIONS,
        # Compact separators: whitespace costs tokens.
        "input": json.dumps(facts, separators=(",", ":"), ensure_ascii=False),
        "max_output_tokens": settings["max_output_tokens"],
        "store": False,
        "text": {"format": {"type": "json_schema", "name": "tooling_summary", "schema": SUMMARY_SCHEMA, "strict": True}},
    }
    if settings["reasoning"]:
        body["reasoning"] = {"effort": settings["reasoning"]}
    try:
        payload = _post(settings, body)
    except SummaryUnavailableError as exc:
        # A model may reject the effort value (or the field). Retry once with the cheapest
        # value it lists as supported, or without the field.
        if "reasoning" not in body or "(400)" not in str(exc):
            raise
        fallback = cheapest_supported_effort(str(exc))
        if fallback:
            body["reasoning"] = {"effort": fallback}
        else:
            body.pop("reasoning")
        payload = _post(settings, body)
    texts = [
        part.get("text", "")
        for item in payload.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    if not texts:
        reason = (payload.get("incomplete_details") or {}).get("reason")
        raise SummaryUnavailableError(
            "The AI summary was cut short. Raise SUMMARY_MAX_OUTPUT_TOKENS." if reason == "max_output_tokens"
            else "The AI summary service returned no answer."
        )
    try:
        summary = Summary.model_validate_json(texts[-1])
    except ValidationError as exc:
        raise SummaryUnavailableError("The AI summary did not match the expected format.") from exc
    return Summary(headline=summary.headline.strip(), recommendations=summary.recommendations[:5], watch_outs=summary.watch_outs[:4])


def summarize(body: SummaryRequest, client: str) -> SummaryResponse:
    settings = _settings()
    factor = body.eur_to_usd if body.currency == "USD" and body.eur_to_usd else 1.0
    currency = body.currency if factor != 1.0 or body.currency == "EUR" else "EUR"
    report = build_report(body.request)
    facts = build_facts(report, body.request, currency, factor)
    key = hashlib.sha256((settings["model"] + json.dumps(facts, sort_keys=True)).encode()).hexdigest()
    with _lock:
        hit = _cache.get(key)
        if hit:
            _cache.move_to_end(key)
    if hit:
        return SummaryResponse(**hit.model_dump(), model=settings["model"], cached=True)
    _check_limits(client, settings)
    summary = _ask_model(facts, settings)
    with _lock:
        _cache[key] = summary
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return SummaryResponse(**summary.model_dump(), model=settings["model"])
