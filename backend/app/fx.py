"""EUR/USD exchange rate from the European Central Bank.

Source: the ECB euro foreign exchange reference rates, published around 16:00 CET
on every TARGET working day. They are the official reference used across the EU.
https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html

The rate is cached in memory. If the ECB cannot be reached, the last good rate is
kept for up to a week and is marked as stale; after that the endpoint fails and
the user enters a rate by hand.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from pydantic import BaseModel

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
SOURCE_NAME = "European Central Bank euro reference rate"
SOURCE_URL = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html"
REFRESH_S = 4 * 3600
MAX_STALE_S = 7 * 86400


class FxUnavailableError(Exception):
    """No trustworthy rate is available (HTTP 503)."""


class FxRate(BaseModel):
    base: str = "EUR"
    quote: str = "USD"
    rate: float
    date: str
    source: str = SOURCE_NAME
    source_url: str = SOURCE_URL
    stale: bool = False


_lock = threading.Lock()
_cached: tuple[float, FxRate] | None = None  # (fetched at, rate)


def parse_ecb_xml(payload: bytes, currency: str = "USD") -> FxRate:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise FxUnavailableError("The ECB returned an unreadable rate file.") from exc
    for cube in root.iter():
        if cube.tag.endswith("Cube") and cube.get("time"):
            for child in cube:
                if child.get("currency") == currency:
                    rate = float(child.get("rate"))
                    day = date.fromisoformat(cube.get("time"))
                    if not 0.2 < rate < 5:
                        raise FxUnavailableError(f"The ECB {currency} rate {rate} is outside the plausible range.")
                    return FxRate(quote=currency, rate=rate, date=day.isoformat())
    raise FxUnavailableError(f"The ECB rate file has no {currency} rate.")


def _download() -> bytes:
    url = os.environ.get("FX_ECB_URL", ECB_DAILY_URL)
    request = urllib.request.Request(url, headers={"User-Agent": "tooling-cost-estimator"})
    try:
        with urllib.request.urlopen(request, timeout=float(os.environ.get("FX_TIMEOUT_S", "10"))) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FxUnavailableError("The European Central Bank exchange rate could not be loaded.") from exc


def eur_usd() -> FxRate:
    """Current EUR/USD reference rate (US dollars per euro)."""
    global _cached
    now = time.time()
    with _lock:
        cached = _cached
    if cached and now - cached[0] < REFRESH_S:
        return cached[1]
    try:
        rate = parse_ecb_xml(_download())
    except FxUnavailableError:
        if cached and now - cached[0] < MAX_STALE_S:
            return cached[1].model_copy(update={"stale": True})
        raise
    with _lock:
        _cached = (now, rate)
    return rate


def eur_usd_or_none() -> float | None:
    try:
        return eur_usd().rate
    except FxUnavailableError:
        return None


def reset_cache() -> None:
    global _cached
    with _lock:
        _cached = None
