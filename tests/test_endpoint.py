"""Integration tests for /health and /ai/risk-assess (v2 zone model)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.schemas import WeatherSnapshot
from app.risk import A1_RADIUS_M

_MOCK_SNAPSHOTS = [
    (
        datetime(2026, 5, 23, 3, 0, tzinfo=timezone.utc),   # 06:00 local (UTC+3)
        WeatherSnapshot(windSpeedKmh=18.0, windGustKmh=31.0, windDirectionDegrees=240.0,
                        temperatureC=24.0, humidity=48.0, precipitationMm=0.0, source="mock"),
    ),
    (
        datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc),   # 12:00 local — peak foraging
        WeatherSnapshot(windSpeedKmh=22.0, windGustKmh=38.0, windDirectionDegrees=250.0,
                        temperatureC=27.0, humidity=42.0, precipitationMm=0.0, source="mock"),
    ),
]

SAMPLE_REQUEST = {
    "crop": "rapita",
    "parcelId": "P-128",
    "product": {
        "commercialName": "Mospilan 20 SG",
        "activeSubstance": "acetamiprid",
        "beeToxicity": "high",
    },
    "dose": {"amountPerHectareKg": 0.2, "totalAmountKg": 1.4},
    "applicationMethod": "ground_boom",
    "appliedAt": "2026-05-23T06:30:00+03:00",
    "durationHours": 2.0,
    "areaHa": 7.0,
    "center": {"lat": 46.7712, "lon": 23.6236},
    "locale": "ro",
}


async def _mock_range(*args, **kwargs):
    return _MOCK_SNAPSHOTS


@pytest.fixture()
def client():
    with patch("app.weather.fetch_weather_range", side_effect=_mock_range):
        from app.main import app
        with TestClient(app) as c:
            yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "bee-ai-service"}


def test_risk_assess_ok(client):
    assert client.post("/ai/risk-assess", json=SAMPLE_REQUEST).status_code == 200


def test_response_schema(client):
    data = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    for key in ("riskScore", "riskLevel", "zones", "weatherUsed", "exposureFactors",
                "warnings", "explanationRo", "recommendedAction", "deterministic",
                "notifyBeekeepersWithinMeters"):
        assert key in data, f"Missing key: {key}"


def test_risk_score_range(client):
    data = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    assert 0.0 <= data["riskScore"] <= 1.0


def test_a1_always_present(client):
    data = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    zones = data["zones"]["features"]
    labels = [f["properties"]["zone"] for f in zones]
    assert "A1" in labels


def test_a1_radius_is_7km(client):
    data = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    a1 = next(f for f in data["zones"]["features"] if f["properties"]["zone"] == "A1")
    assert a1["properties"]["radiusMeters"] == int(A1_RADIUS_M)


def test_notify_at_least_7km(client):
    data = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    assert data["notifyBeekeepersWithinMeters"] >= int(A1_RADIUS_M)


def test_exposure_factors_present(client):
    data = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    ef = data["exposureFactors"]
    assert "temperatureFactor" in ef
    assert "timeOfDayFactor" in ef
    assert "rainFactor" in ef
    assert "worstCaseHourUtc" in ef


def test_determinism(client):
    r1 = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    r2 = client.post("/ai/risk-assess", json=SAMPLE_REQUEST).json()
    assert r1["riskScore"] == r2["riskScore"]
    assert r1["zones"] == r2["zones"]


def test_default_duration_accepted(client):
    req = {**SAMPLE_REQUEST}
    req.pop("durationHours", None)
    assert client.post("/ai/risk-assess", json=req).status_code == 200


def test_missing_optional_fields(client):
    req = {
        k: v for k, v in SAMPLE_REQUEST.items()
        if k not in ("applicationMethod", "durationHours")
    }
    req["product"] = {"commercialName": "TestProd", "activeSubstance": "tebuconazole"}
    assert client.post("/ai/risk-assess", json=req).status_code == 200
