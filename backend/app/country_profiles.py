# Rates are in each country's own costing currency ("currency"): EUR for the
# European countries, USD for China and India, where tooling is quoted in USD.
# China and India: typical toolroom shop rates in USD/h (2026 planning values;
# validate against supplier quotes). The quarterly labour/energy databases in the
# TCE folder are still empty templates, so they cannot be used as a source yet.
# The key "electricity_eur_kwh" keeps its historical name; for USD countries the
# value is USD/kWh. Use assumptions_in_eur() before passing a profile to the
# calculator, whose monetary contract is EUR.
MONEY_KEYS = (
    "engineering_rate", "assembly_rate", "cnc_3_axis_rate", "cnc_5_axis_rate",
    "edm_rate", "grinding_rate", "electricity_eur_kwh",
)
RATE_KEYS = MONEY_KEYS + ("machine_efficiency", "operator_efficiency", "overhead_rate", "margin_rate")

COUNTRY_PROFILES = {
    "DE": {
        "name": "Germany",
        "currency": "EUR",
        "engineering_rate": 80.0,
        "assembly_rate": 45.0,
        "cnc_3_axis_rate": 110.0,
        "cnc_5_axis_rate": 145.0,
        "edm_rate": 115.0,
        "grinding_rate": 110.0,
        "electricity_eur_kwh": 0.226,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "FR": {
        "name": "France",
        "currency": "EUR",
        "engineering_rate": 75.0,
        "assembly_rate": 43.0,
        "cnc_3_axis_rate": 105.0,
        "cnc_5_axis_rate": 140.0,
        "edm_rate": 115.0,
        "grinding_rate": 110.0,
        "electricity_eur_kwh": 0.153,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "AT": {
        "name": "Austria",
        "currency": "EUR",
        "engineering_rate": 85.0,
        "assembly_rate": 47.0,
        "cnc_3_axis_rate": 110.0,
        "cnc_5_axis_rate": 145.0,
        "edm_rate": 120.0,
        "grinding_rate": 115.0,
        "electricity_eur_kwh": 0.199,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "CZ": {
        "name": "Czech Republic",
        "currency": "EUR",
        "engineering_rate": 35.0,
        "assembly_rate": 19.0,
        "cnc_3_axis_rate": 80.0,
        "cnc_5_axis_rate": 115.0,
        "edm_rate": 85.0,
        "grinding_rate": 85.0,
        "electricity_eur_kwh": 0.183,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "SK": {
        "name": "Slovakia",
        "currency": "EUR",
        "engineering_rate": 30.0,
        "assembly_rate": 18.0,
        "cnc_3_axis_rate": 80.0,
        "cnc_5_axis_rate": 115.0,
        "edm_rate": 85.0,
        "grinding_rate": 80.0,
        "electricity_eur_kwh": 0.209,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "HU": {
        "name": "Hungary",
        "currency": "EUR",
        "engineering_rate": 25.0,
        "assembly_rate": 14.0,
        "cnc_3_axis_rate": 75.0,
        "cnc_5_axis_rate": 110.0,
        "edm_rate": 85.0,
        "grinding_rate": 80.0,
        "electricity_eur_kwh": 0.213,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "PL": {
        "name": "Poland",
        "currency": "EUR",
        "engineering_rate": 30.0,
        "assembly_rate": 16.0,
        "cnc_3_axis_rate": 75.0,
        "cnc_5_axis_rate": 115.0,
        "edm_rate": 85.0,
        "grinding_rate": 80.0,
        "electricity_eur_kwh": 0.192,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "ES": {
        "name": "Spain",
        "currency": "EUR",
        "engineering_rate": 45.0,
        "assembly_rate": 26.0,
        "cnc_3_axis_rate": 85.0,
        "cnc_5_axis_rate": 120.0,
        "edm_rate": 95.0,
        "grinding_rate": 90.0,
        "electricity_eur_kwh": 0.132,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "IT": {
        "name": "Italy",
        "currency": "EUR",
        "engineering_rate": 55.0,
        "assembly_rate": 30.0,
        "cnc_3_axis_rate": 90.0,
        "cnc_5_axis_rate": 130.0,
        "edm_rate": 100.0,
        "grinding_rate": 95.0,
        "electricity_eur_kwh": 0.220,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "CN": {
        "name": "China",
        "currency": "USD",
        "engineering_rate": 30.0,
        "assembly_rate": 12.0,
        "cnc_3_axis_rate": 35.0,
        "cnc_5_axis_rate": 55.0,
        "edm_rate": 40.0,
        "grinding_rate": 35.0,
        "electricity_eur_kwh": 0.09,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },

    "IN": {
        "name": "India",
        "currency": "USD",
        "engineering_rate": 20.0,
        "assembly_rate": 7.0,
        "cnc_3_axis_rate": 25.0,
        "cnc_5_axis_rate": 40.0,
        "edm_rate": 30.0,
        "grinding_rate": 25.0,
        "electricity_eur_kwh": 0.1,
        "machine_efficiency": 0.82,
        "operator_efficiency": 0.88,
        "overhead_rate": 0.15,
        "margin_rate": 0.15,
    },
}

def assumptions_in_eur(code: str, eur_to_usd: float | None) -> dict:
    """The country's default cost assumptions converted to EUR.

    ``eur_to_usd`` is US dollars per euro. It is required for USD countries.
    """
    profile = COUNTRY_PROFILES[code]
    values = {key: profile[key] for key in RATE_KEYS}
    if profile["currency"] == "USD":
        if not eur_to_usd or eur_to_usd <= 0:
            raise ValueError(f"An EUR/USD exchange rate is required to cost {profile['name']}.")
        for key in MONEY_KEYS:
            values[key] = values[key] / eur_to_usd
    return values
