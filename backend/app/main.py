from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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