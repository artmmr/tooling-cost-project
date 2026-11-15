from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.country_profiles import COUNTRY_PROFILES
from app.fx import FxRate, FxUnavailableError, eur_usd
from app.process_matrix import public_matrix
from app.tooling_materials import TOOLING_MATERIALS

from app.advisor import AdvancedReport, build_report
from app.calculator import calculate
from app.summary import (
    SummaryRateLimitError,
    SummaryRequest,
    SummaryResponse,
    SummaryUnavailableError,
    summarize,
)
from app.drawing_extraction import (
    DrawingExtractionError,
    DrawingExtractionResponse,
    VisionUnavailableError,
    extract_dimensions,
)
from app.models import CalculationRequest, CalculationResponse
from app.reference_data import load_reference_summary
from app.tooling_catalog import public_catalog
from dataclasses import asdict


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
    try:
        return calculate(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/advanced-report",
    response_model=AdvancedReport,
)
def advanced_report(request: CalculationRequest) -> AdvancedReport:
    try:
        return build_report(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def client_id(http_request: Request) -> str:
    # Render terminates TLS at a proxy; the first forwarded address is the client.
    forwarded = http_request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (http_request.client.host if http_request.client else "unknown")


@app.post(
    "/api/advanced-report/summary",
    response_model=SummaryResponse,
)
async def advanced_report_summary(body: SummaryRequest, http_request: Request) -> SummaryResponse:
    try:
        return await run_in_threadpool(summarize, body, client_id(http_request))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SummaryRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except SummaryUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/api/extract-dimensions",
    response_model=DrawingExtractionResponse,
)
async def extract_drawing_dimensions(
    file: UploadFile = File(...),
) -> DrawingExtractionResponse:
    pdf_bytes = await file.read()
    try:
        return await run_in_threadpool(
            extract_dimensions, pdf_bytes, file.filename or "drawing.pdf"
        )
    except DrawingExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VisionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/countries")
def get_countries():
    return [
        {
            "code": code,
            "name": profile["name"],
            "currency": profile["currency"],
        }
        for code, profile in COUNTRY_PROFILES.items()
    ]


@app.get("/api/fx/eur-usd", response_model=FxRate)
def get_eur_usd() -> FxRate:
    try:
        return eur_usd()
    except FxUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/process-matrix")
def get_process_matrix():
    return public_matrix()


@app.get("/api/reference-data")
def get_reference_data():
    return load_reference_summary()


@app.get("/api/tooling-catalog")
def get_tooling_catalog():
    return public_catalog()


@app.get("/api/tooling-materials")
def get_tooling_materials():
    return {code: asdict(profile) for code, profile in TOOLING_MATERIALS.items()}


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
