"""Tests for deterministic risk computation, exposure modifiers, and worst-hour selection."""

from datetime import datetime, timezone, timedelta

import pytest

from app.risk import (
    A1_RADIUS_M,
    _hazard_score,
    _rain_factor,
    _score_to_level,
    _temp_factor,
    _time_factor,
    compute_risk,
    select_worst_hour,
)
from app.ld50_data import lookup_ld50
from app.schemas import WeatherSnapshot


def _w(**kw) -> WeatherSnapshot:
    defaults = dict(windSpeedKmh=18.0, windGustKmh=31.0, windDirectionDegrees=240.0,
                    temperatureC=24.0, humidity=48.0, precipitationMm=0.0, source="test")
    defaults.update(kw)
    return WeatherSnapshot(**defaults)


# ── Exposure modifier unit tests ───────────────────────────────────────────────

def test_temp_factor_cold():
    assert _temp_factor(5.0) == pytest.approx(0.1)

def test_temp_factor_mild():
    assert _temp_factor(12.0) == pytest.approx(0.5)

def test_temp_factor_warm():
    assert _temp_factor(20.0) == pytest.approx(1.0)

def test_time_factor_peak():
    assert _time_factor(12) == pytest.approx(1.0)

def test_time_factor_shoulder():
    assert _time_factor(8) == pytest.approx(0.5)
    assert _time_factor(18) == pytest.approx(0.5)

def test_time_factor_night():
    assert _time_factor(2) == pytest.approx(0.1)
    assert _time_factor(23) == pytest.approx(0.1)

def test_rain_factor_dry():
    assert _rain_factor(0.0) == pytest.approx(1.0)

def test_rain_factor_light():
    assert _rain_factor(0.5) == pytest.approx(0.6)

def test_rain_factor_heavy():
    assert _rain_factor(3.0) == pytest.approx(0.2)

def test_hazard_score_rain_reduces():
    w_dry  = _w(precipitationMm=0.0)
    w_rain = _w(precipitationMm=3.0)
    assert _hazard_score(w_dry, 12) > _hazard_score(w_rain, 12)

def test_hazard_score_night_reduces():
    assert _hazard_score(_w(), 12) > _hazard_score(_w(), 2)


# ── select_worst_hour ─────────────────────────────────────────────────────────

_TZ = timezone(timedelta(hours=3))  # UTC+3 like Romania


def _snapshot_at(hour_utc: int, **kw) -> tuple[datetime, WeatherSnapshot]:
    dt = datetime(2026, 5, 23, hour_utc, 0, tzinfo=timezone.utc)
    return dt, _w(**kw)


def test_select_worst_hour_picks_most_dangerous():
    snapshots = [
        _snapshot_at(2,  windSpeedKmh=5.0,  temperatureC=10.0, precipitationMm=2.0),  # night, cold, rain
        _snapshot_at(12, windSpeedKmh=20.0, temperatureC=22.0, precipitationMm=0.0),  # midday, warm, dry
        _snapshot_at(18, windSpeedKmh=15.0, temperatureC=18.0, precipitationMm=0.0),
    ]
    dt, snap, ef = select_worst_hour(snapshots, _TZ)
    assert dt.hour == 12   # UTC 12 = local 15h → peak foraging

def test_select_worst_hour_fallback_when_empty():
    dt, snap, ef = select_worst_hour([], _TZ)
    assert snap.windSpeedKmh == 20.0   # conservative defaults
    assert ef.temperatureFactor == 1.0

def test_select_worst_hour_exposure_factors_coherent():
    snapshots = [_snapshot_at(14, temperatureC=25.0, precipitationMm=0.0)]
    _, _, ef = select_worst_hour(snapshots, _TZ)
    assert ef.temperatureFactor == pytest.approx(1.0)
    assert ef.timeOfDayFactor == pytest.approx(1.0)   # 14 UTC = 17 local → peak
    assert ef.rainFactor == pytest.approx(1.0)


# ── compute_risk ──────────────────────────────────────────────────────────────

def test_determinism():
    w = _w()
    r1 = compute_risk(bee_toxicity="high", active_substance="acetamiprid",
                      total_amount_kg=1.4, application_method="ground_boom", weather=w)
    r2 = compute_risk(bee_toxicity="high", active_substance="acetamiprid",
                      total_amount_kg=1.4, application_method="ground_boom", weather=w)
    assert r1 == r2

def test_zone_ordering():
    _, _, r_a2, r_a3, r_a4, _ = compute_risk(
        bee_toxicity="high", active_substance="acetamiprid",
        total_amount_kg=1.4, application_method="ground_boom", weather=_w())
    assert r_a2 < r_a3 < r_a4

def test_risk_score_bounds():
    score, *_ = compute_risk(
        bee_toxicity="very_high", active_substance="deltamethrin",
        total_amount_kg=100.0, application_method="aerial",
        weather=_w(windSpeedKmh=200.0, windGustKmh=300.0))
    assert 0.0 <= score <= 1.0

def test_more_toxic_larger_zone():
    w = _w()
    _, _, r_delta, *_ = compute_risk(bee_toxicity="very_high", active_substance="deltamethrin",
                                      total_amount_kg=1.0, application_method="ground_boom", weather=w)
    _, _, r_aceta, *_ = compute_risk(bee_toxicity="high", active_substance="acetamiprid",
                                      total_amount_kg=1.0, application_method="ground_boom", weather=w)
    assert r_delta > r_aceta

def test_aerial_larger_than_ground():
    w = _w()
    _, _, r_air, *_ = compute_risk(bee_toxicity="high", active_substance="deltamethrin",
                                    total_amount_kg=1.0, application_method="aerial", weather=w)
    _, _, r_gnd, *_ = compute_risk(bee_toxicity="high", active_substance="deltamethrin",
                                    total_amount_kg=1.0, application_method="ground_boom", weather=w)
    assert r_air > r_gnd

def test_wind_increases_radius():
    _, _, r_calm, *_ = compute_risk(bee_toxicity="high", total_amount_kg=1.0,
                                     application_method="ground_boom",
                                     weather=_w(windSpeedKmh=0.0, windGustKmh=0.0))
    _, _, r_wind, *_ = compute_risk(bee_toxicity="high", total_amount_kg=1.0,
                                     application_method="ground_boom",
                                     weather=_w(windSpeedKmh=40.0, windGustKmh=60.0))
    assert r_wind > r_calm

def test_rain_reduces_radius():
    _, _, r_dry, *_ = compute_risk(bee_toxicity="high", total_amount_kg=1.0,
                                    application_method="ground_boom", weather=_w(),
                                    rain_factor=1.0)
    _, _, r_wet, *_ = compute_risk(bee_toxicity="high", total_amount_kg=1.0,
                                    application_method="ground_boom", weather=_w(),
                                    rain_factor=0.2)
    assert r_dry > r_wet

def test_cold_temp_reduces_radius():
    _, _, r_warm, *_ = compute_risk(bee_toxicity="high", total_amount_kg=1.0,
                                     application_method="ground_boom", weather=_w(),
                                     temp_factor=1.0)
    _, _, r_cold, *_ = compute_risk(bee_toxicity="high", total_amount_kg=1.0,
                                     application_method="ground_boom", weather=_w(),
                                     temp_factor=0.1)
    assert r_warm > r_cold

def test_fungicide_smaller_than_insecticide():
    w = _w()
    _, _, r_fungi, *_ = compute_risk(bee_toxicity="low", active_substance="tebuconazole",
                                      total_amount_kg=1.0, application_method="ground_boom", weather=w)
    _, _, r_ins, *_ = compute_risk(bee_toxicity="high", active_substance="chlorpyrifos",
                                    total_amount_kg=1.0, application_method="ground_boom", weather=w)
    assert r_fungi < r_ins

def test_unknown_substance_fallback():
    score, level, r_a2, r_a3, r_a4, details = compute_risk(
        bee_toxicity="high", active_substance="made-up-xyz",
        total_amount_kg=1.0, application_method="ground_boom", weather=_w())
    assert 0.0 <= score <= 1.0
    assert r_a2 > 0
    assert details.ld50UsedUgPerBee is None

def test_ld50_stored_in_details():
    _, _, _, _, _, details = compute_risk(
        bee_toxicity="high", active_substance="acetamiprid",
        total_amount_kg=1.0, application_method="ground_boom", weather=_w())
    assert details.ld50UsedUgPerBee == pytest.approx(7.1)

def test_score_to_level_boundaries():
    assert _score_to_level(0.0)  == "low"
    assert _score_to_level(0.25) == "medium"
    assert _score_to_level(0.50) == "high"
    assert _score_to_level(0.75) == "very_high"


# ── LD50 lookup ───────────────────────────────────────────────────────────────

def test_ld50_known():
    assert lookup_ld50("acetamiprid") == pytest.approx(7.1)
    assert lookup_ld50("deltamethrin") == pytest.approx(0.0015)

def test_ld50_case_insensitive():
    assert lookup_ld50("Acetamiprid") == lookup_ld50("acetamiprid")

def test_ld50_hyphen_normalisation():
    assert lookup_ld50("lambda cyhalothrin") == pytest.approx(0.038)

def test_ld50_unknown_returns_none():
    assert lookup_ld50("totally-unknown-xyz") is None
