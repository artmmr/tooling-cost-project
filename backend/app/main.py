import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.calculator import calculate
from app.models import CalculationRequest, CalculationResponse


app = FastAPI(
    title="Tooling Cost API",
    version="0.1.0",
)


frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://127.0.0.1:5500,http://localhost:5500",
)

allowed_origins = [
    origin.strip()
    for origin in frontend_origins.split(",")
    if origin.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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


@app.get("/")
def root():
    return {
        "name": "Tooling Cost API",
        "status": "Online"
    }