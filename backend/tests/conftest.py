import pytest

from app import fx

# Shape of https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
SAMPLE_ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <gesmes:Sender><gesmes:name>European Central Bank</gesmes:name></gesmes:Sender>
  <Cube>
    <Cube time="2026-11-13">
      <Cube currency="USD" rate="1.1600"/>
      <Cube currency="JPY" rate="171.20"/>
      <Cube currency="CNY" rate="8.2650"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


@pytest.fixture(autouse=True)
def offline_fx(monkeypatch):
    """No test may call the ECB: serve a fixed rate file."""
    fx.reset_cache()
    monkeypatch.setattr(fx, "_download", lambda: SAMPLE_ECB_XML)
    yield
    fx.reset_cache()
