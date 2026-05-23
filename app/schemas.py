from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


BeeToxicity = Literal["low", "medium", "high", "very_high"]
ApplicationMethod = Literal["ground_boom", "airblast", "aerial"]
RiskLevel = Literal["low", "medium", "high", "very_high"]


class ProductInfo(BaseModel):
    commercialName: str
    activeSubstance: str
    beeToxicity: Optional[BeeToxicity] = None


class DoseInfo(BaseModel):
    amountPerHectareKg: float
    totalAmountKg: float


class CenterPoint(BaseModel):
    lat: float
    lon: float


class RiskRequest(BaseModel):
    crop: str
    parcelId: str
    product: ProductInfo
    dose: DoseInfo
    applicationMethod: Optional[ApplicationMethod] = "ground_boom"
    appliedAt: datetime
    durationHours: Optional[float] = Field(default=1.0, ge=0.0,
        description="How long the application takes, in hours. "
                    "Weather is evaluated for this window plus a 4h persistence tail.")
    areaHa: float
    center: CenterPoint
    locale: Optional[str] = "ro"


class WeatherSnapshot(BaseModel):
    windSpeedKmh: float
    windGustKmh: float
    windDirectionDegrees: float
    temperatureC: float
    humidity: float
    precipitationMm: float
    source: str = "open-meteo"


class ExposureFactors(BaseModel):
    """Bee-activity modifiers derived from the worst-case hour in the application window."""
    temperatureFactor: float = Field(
        description="Bee activity by temperature: 0.1 (<10°C) / 0.5 (10–15°C) / 1.0 (>15°C)")
    timeOfDayFactor: float = Field(
        description="Foraging by time of day: 1.0 (09–17h) / 0.5 (shoulders) / 0.1 (night)")
    rainFactor: float = Field(
        description="Rain discount: 1.0 (dry) / 0.6 (≥0.5 mm/h) / 0.2 (≥2 mm/h)")
    worstCaseHourUtc: str = Field(description="ISO 8601 UTC datetime of the worst-case hour")
    worstCaseWindKmh: float
    worstCaseWindDirectionDeg: float


class DeterministicDetails(BaseModel):
    baseRadiusM: float
    windFactor: float
    gustFactor: float
    exposureMultiplier: float = Field(
        description="Combined temp × time-of-day × rain factor (≤1.0 reduces zone size)")
    ld50UsedUgPerBee: Optional[float] = Field(
        default=None,
        description="EFSA acute contact LD50 used for this substance. "
                    "None means toxicity-label fallback was used.")


GeoJSONFeatureCollection = dict[str, Any]


class RiskResponse(BaseModel):
    riskScore: float = Field(ge=0.0, le=1.0)
    riskLevel: RiskLevel
    zones: GeoJSONFeatureCollection = Field(
        description="GeoJSON FeatureCollection. A1 (7 km) is always present. "
                    "A2/A3/A4 appear only when their computed radius exceeds 7 km.")
    notifyBeekeepersWithinMeters: int
    weatherUsed: WeatherSnapshot = Field(description="The worst-case hour snapshot")
    exposureFactors: ExposureFactors
    warnings: list[str]
    explanationRo: str
    recommendedAction: str
    deterministic: DeterministicDetails
