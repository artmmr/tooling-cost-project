from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException

from app.country_profiles import COUNTRY_PROFILES
from app.tooling_materials import TOOLING_MATERIALS

from app.calculator import calculate
from app.models import CalculationRequest, CalculationResponse


app = FastAPI(
    title="Tooling Cost API",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://frabjous-parfait-6e9800.netlify.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def root():
    return {
        "name": "Tooling Cost API",
        "status": "online",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/calculate",
    response_model=CalculationResponse,
)
def calculate_tooling(
    request: CalculationRequest,
) -> CalculationResponse:
    return calculate(request)


@app.get("/api/countries")
def get_countries():
    return [
        {
            "code": code,
            "name": profile["name"],
        }
        for code, profile in COUNTRY_PROFILES.items()
    ]


@app.get("/api/countries/{country_code}")
def get_country_profile(country_code: str):
    country_code = country_code.upper()

    profile = COUNTRY_PROFILES.get(country_code)

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Country not found",
        )

    return {
        "code": country_code,
        **profile,
    }


@app.get("/api/tooling-materials/{material_code}")
def get_tooling_material(material_code: str):
    profile = TOOLING_MATERIALS.get(material_code)

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Tooling material profile not found",
        )

    return {
        "code": material_code,
        "name": profile.name,

        "density_kg_m3": profile.density_kg_m3,
        "block_price_per_tonne": profile.block_price_per_tonne,
        "removal_rate_cm3_min": profile.removal_rate_cm3_min,

        "milling_volume_factor": profile.milling_volume_factor,
        "milling_tool_price": profile.milling_tool_price,

        "requires_heat_treatment": profile.requires_heat_treatment,
        "heat_treatment_eur_per_kg": profile.heat_treatment_eur_per_kg,

        "route": {
            "cnc_3_axis_share": profile.route.cnc_3_axis_share,
            "cnc_5_axis_share": profile.route.cnc_5_axis_share,
            "edm_share": profile.route.edm_share,
            "grinding_share": profile.route.grinding_share,
        },
    }