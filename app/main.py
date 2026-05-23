"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

from app.fallback import generate_fallback
from app.geometry import build_zones
from app.llm import ExplainInput, build_llm_client
from app.risk import A1_RADIUS_M, compute_risk, select_worst_hour
from app.schemas import RiskRequest, RiskResponse
from app.weather import PERSISTENCE_HOURS, fetch_weather_range

_llm_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm_client
    _llm_client = build_llm_client()
    logger.info("Bee AI Service v2 started.")
    yield
    logger.info("Bee AI Service stopped.")


app = FastAPI(
    title="Bee AI Risk Assessment Service",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "bee-ai-service"}


@app.post("/ai/risk-assess", response_model=RiskResponse)
async def risk_assess(req: RiskRequest) -> Any:
    duration_h = req.durationHours or 1.0
    local_tz   = req.appliedAt.tzinfo
    end_dt     = req.appliedAt + timedelta(hours=duration_h + PERSISTENCE_HOURS)

    # 1. Fetch weather for the full application window + persistence tail
    try:
        snapshots = await fetch_weather_range(
            req.center.lat, req.center.lon, req.appliedAt, end_dt,
        )
    except Exception as exc:
        logger.error("Weather fetch failed: %s", exc)
        snapshots = []

    if not snapshots:
        logger.warning("No weather data — worst-hour selector will use conservative defaults")

    # 2. Pick the single worst-case hour
    _, worst_weather, exposure_factors = select_worst_hour(snapshots, local_tz)

    bee_toxicity       = req.product.beeToxicity or "high"
    application_method = req.applicationMethod or "ground_boom"

    # 3. Deterministic risk + zone radii
    risk_score, risk_level, r_a2, r_a3, r_a4, details = compute_risk(
        bee_toxicity=bee_toxicity,
        active_substance=req.product.activeSubstance,
        total_amount_kg=req.dose.totalAmountKg,
        application_method=application_method,
        weather=worst_weather,
        temp_factor=exposure_factors.temperatureFactor,
        time_factor=exposure_factors.timeOfDayFactor,
        rain_factor=exposure_factors.rainFactor,
    )

    # 4. GeoJSON — A1 always at 7 km; A2/A3/A4 only if they exceed 7 km
    zones = build_zones(
        center_lat=req.center.lat,
        center_lon=req.center.lon,
        r_a2=r_a2, r_a3=r_a3, r_a4=r_a4,
        wind_speed_kmh=worst_weather.windSpeedKmh,
        wind_direction_deg=worst_weather.windDirectionDegrees,
    )

    # 5. Notification distance: always at least A1
    notify_m = max(A1_RADIUS_M, r_a4)

    # 6. Natural-language explanation via LLM (or deterministic fallback)
    explain_input = ExplainInput(
        product_name=req.product.commercialName,
        active_substance=req.product.activeSubstance,
        bee_toxicity=bee_toxicity,
        total_amount_kg=req.dose.totalAmountKg,
        application_method=application_method,
        wind_speed_kmh=worst_weather.windSpeedKmh,
        wind_direction_deg=worst_weather.windDirectionDegrees,
        temperature_c=worst_weather.temperatureC,
        risk_score=risk_score,
        risk_level=risk_level,
        r_high_m=max(A1_RADIUS_M, r_a2),
        r_low_m=notify_m,
    )

    llm_result = _llm_client.explain(explain_input) if _llm_client else None
    if llm_result is None:
        llm_result = generate_fallback(explain_input)

    return RiskResponse(
        riskScore=round(risk_score, 4),
        riskLevel=risk_level,
        zones=zones,
        notifyBeekeepersWithinMeters=int(round(notify_m)),
        weatherUsed=worst_weather,
        exposureFactors=exposure_factors,
        warnings=llm_result.warnings,
        explanationRo=llm_result.explanation_ro,
        recommendedAction=llm_result.recommended_action,
        deterministic=details,
    )
