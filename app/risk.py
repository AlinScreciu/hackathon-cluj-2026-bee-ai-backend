"""Deterministic bee risk score and zone radii calculation.

Zone structure
--------------
A1  Fixed 7 km — always shown. The guaranteed notification perimeter.
A2  Computed (LD50-based). Shown only if radius > 7 km.
A3  Computed. Shown only if radius > 7 km.
A4  Computed. Shown only if radius > 7 km.

Worst-hour selection
--------------------
The caller fetches hourly weather over the full application window
(duration + persistence tail) and passes the list to `select_worst_hour`,
which returns the single snapshot that would produce the highest bee exposure.
That snapshot (and its derived modifiers) drives all zone computations.

Safety multiplier
-----------------
SAFETY_MULTIPLIER = 1.5 is applied to every computed radius to compensate
for unmodelled factors (droplet size, nozzle type, canopy shielding, …).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.ld50_data import lookup_ld50
from app.schemas import (
    ApplicationMethod,
    BeeToxicity,
    DeterministicDetails,
    ExposureFactors,
    RiskLevel,
    WeatherSnapshot,
)

# ── Zone constants ─────────────────────────────────────────────────────────────
A1_RADIUS_M: float = 7_000.0          # fixed, always rendered
ZONE_MULTIPLIERS = {"A3": 2.0, "A4": 3.5}   # relative to R_A2

# ── Safety buffer ──────────────────────────────────────────────────────────────
SAFETY_MULTIPLIER: float = 1.5

# ── LD50 → radius (log scale) ─────────────────────────────────────────────────
_LOG_SCALE_M  = 120.0
_LOG_OFFSET   = 3.0
_MIN_LOG_FACTOR = 0.2

# ── Toxicity-label fallback (unknown substance) ───────────────────────────────
_TOXICITY_RADIUS_FALLBACK: dict[str, float] = {
    "low":       80.0,
    "medium":   200.0,
    "high":     400.0,
    "very_high":700.0,
}

# ── Application method ────────────────────────────────────────────────────────
METHOD_FACTOR: dict[str, float] = {
    "ground_boom": 1.0,
    "airblast":    1.4,
    "aerial":      2.0,
}

_SCORE_REF_RADIUS_M = 2000.0


# ── Exposure modifiers ────────────────────────────────────────────────────────

def _temp_factor(temp_c: float) -> float:
    """Bee activity by temperature. Below 10 °C bees stay in the hive."""
    if temp_c < 10.0:
        return 0.1
    if temp_c < 15.0:
        return 0.5
    return 1.0


def _time_factor(local_hour: int) -> float:
    """Bee foraging by local hour. Peak 09–17 h."""
    if 9 <= local_hour <= 17:
        return 1.0
    if local_hour in (7, 8, 18, 19):
        return 0.5
    return 0.1


def _rain_factor(precip_mm: float) -> float:
    """Rain reduces bee activity and washes residues off foliage."""
    if precip_mm >= 2.0:
        return 0.2
    if precip_mm >= 0.5:
        return 0.6
    return 1.0


def _hazard_score(snap: WeatherSnapshot, local_hour: int) -> float:
    """Composite hazard score for a single hourly snapshot.

    Higher score = worse conditions for bees = this is the hour we want.
    """
    wind_stretch = (
        (1.0 + snap.windSpeedKmh / 20.0)
        * (1.0 + max(0.0, (snap.windGustKmh - 25.0) / 40.0))
    )
    return (
        wind_stretch
        * _temp_factor(snap.temperatureC)
        * _time_factor(local_hour)
        * _rain_factor(snap.precipitationMm)
    )


def select_worst_hour(
    snapshots: list[tuple[datetime, WeatherSnapshot]],
    local_tz,               # tzinfo from appliedAt — used for time-of-day factor
) -> tuple[datetime, WeatherSnapshot, ExposureFactors]:
    """Return the (datetime, snapshot, ExposureFactors) with the highest hazard score.

    Falls back to conservative defaults when no snapshots are available.
    """
    if not snapshots:
        dt = datetime.now(tz=timezone.utc)
        snap = WeatherSnapshot(
            windSpeedKmh=20.0, windGustKmh=35.0, windDirectionDegrees=270.0,
            temperatureC=20.0, humidity=50.0, precipitationMm=0.0,
            source="fallback-defaults",
        )
    else:
        dt, snap = max(
            snapshots,
            key=lambda item: _hazard_score(item[1], item[0].astimezone(local_tz).hour),
        )

    local_hour = dt.astimezone(local_tz).hour
    ef = ExposureFactors(
        temperatureFactor=_temp_factor(snap.temperatureC),
        timeOfDayFactor=_time_factor(local_hour),
        rainFactor=_rain_factor(snap.precipitationMm),
        worstCaseHourUtc=dt.astimezone(timezone.utc).isoformat(),
        worstCaseWindKmh=snap.windSpeedKmh,
        worstCaseWindDirectionDeg=snap.windDirectionDegrees,
    )
    return dt, snap, ef


# ── Core computation ───────────────────────────────────────────────────────────

def compute_risk(
    *,
    bee_toxicity: BeeToxicity,
    active_substance: str = "",
    total_amount_kg: float,
    application_method: ApplicationMethod,
    weather: WeatherSnapshot,
    temp_factor: float = 1.0,
    time_factor: float = 1.0,
    rain_factor: float = 1.0,
) -> tuple[float, RiskLevel, float, float, float, DeterministicDetails]:
    """Return (riskScore, riskLevel, r_a2, r_a3, r_a4, details).

    r_a2/r_a3/r_a4 are computed zone radii. geometry.build_zones decides
    whether to render each based on whether it exceeds A1_RADIUS_M.
    """
    toxicity = bee_toxicity or "high"
    method   = application_method or "ground_boom"

    ld50 = lookup_ld50(active_substance) if active_substance else None
    raw_base = (
        _ld50_to_base_radius(ld50) if ld50 is not None
        else _TOXICITY_RADIUS_FALLBACK.get(toxicity, _TOXICITY_RADIUS_FALLBACK["high"])
    )

    exposure_multiplier = temp_factor * time_factor * rain_factor

    base_radius_m = (
        raw_base
        * math.sqrt(max(total_amount_kg, 0.01))
        * METHOD_FACTOR.get(method, 1.0)
        * SAFETY_MULTIPLIER
        * exposure_multiplier
    )

    wind_factor = 1.0 + (weather.windSpeedKmh / 20.0)
    gust_factor = 1.0 + max(0.0, (weather.windGustKmh - 25.0) / 40.0)

    r_a2 = base_radius_m * wind_factor * gust_factor
    r_a3 = r_a2 * ZONE_MULTIPLIERS["A3"]
    r_a4 = r_a2 * ZONE_MULTIPLIERS["A4"]

    # Risk score derived from raw_base only (before safety/exposure adjustments)
    # so it reflects true chemical hazard, not the conservative buffer.
    raw_score = (
        (raw_base * math.sqrt(max(total_amount_kg, 0.01)) * wind_factor)
        / _SCORE_REF_RADIUS_M
        * _ld50_weight(ld50, toxicity)
    )
    risk_score = min(1.0, max(0.0, raw_score))

    details = DeterministicDetails(
        baseRadiusM=round(base_radius_m, 2),
        windFactor=round(wind_factor, 4),
        gustFactor=round(gust_factor, 4),
        exposureMultiplier=round(exposure_multiplier, 4),
        ld50UsedUgPerBee=ld50,
    )

    return risk_score, _score_to_level(risk_score), r_a2, r_a3, r_a4, details


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ld50_to_base_radius(ld50: float) -> float:
    factor = max(_MIN_LOG_FACTOR, -math.log10(ld50) + _LOG_OFFSET)
    return _LOG_SCALE_M * factor


def _ld50_weight(ld50: float | None, toxicity: str) -> float:
    if ld50 is not None:
        return max(0.3, min(2.0, -math.log10(ld50) * 0.4 + 0.5))
    return {"low": 0.4, "medium": 0.65, "high": 1.0, "very_high": 1.4}.get(toxicity, 1.0)


def _score_to_level(score: float) -> RiskLevel:
    if score < 0.25: return "low"
    if score < 0.50: return "medium"
    if score < 0.75: return "high"
    return "very_high"
