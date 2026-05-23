"""Open-Meteo weather client.

Cache strategy: full-day raw responses keyed by (lat, lon, date).
This lets both single-hour and multi-hour range queries reuse the same fetch.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from app.schemas import WeatherSnapshot

logger = logging.getLogger(__name__)

_CACHE_TTL_S = int(os.getenv("WEATHER_CACHE_S", "600"))

# Hours added after the end of application to cover residue persistence on foliage.
PERSISTENCE_HOURS: int = int(os.getenv("WEATHER_PERSISTENCE_H", "4"))

# (lat_rounded, lon_rounded, date_str) → (raw_hourly_dict, fetched_at_monotonic)
_day_cache: dict[tuple, tuple[dict, float]] = {}


# ── Public API ─────────────────────────────────────────────────────────────────

async def fetch_weather(lat: float, lon: float, dt: datetime) -> WeatherSnapshot:
    """Return a WeatherSnapshot for a single datetime (backward-compatible)."""
    results = await fetch_weather_range(lat, lon, dt, dt)
    return results[0][1] if results else _fallback_snapshot()


async def fetch_weather_range(
    lat: float,
    lon: float,
    start_dt: datetime,
    end_dt: datetime,
) -> list[tuple[datetime, WeatherSnapshot]]:
    """Return chronologically sorted hourly snapshots for [start_dt, end_dt].

    Both bounds are inclusive and rounded to the nearest hour.
    Returns an empty list only if Open-Meteo returns no data at all.
    """
    start_utc = start_dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end_utc   = end_dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)

    # Collect every calendar date spanned by the range
    dates_needed: list[date] = []
    cursor = start_utc.date()
    while cursor <= end_utc.date():
        dates_needed.append(cursor)
        cursor += timedelta(days=1)

    all_snapshots: list[tuple[datetime, WeatherSnapshot]] = []
    for d in dates_needed:
        try:
            day_data = await _get_day_data(lat, lon, d)
            all_snapshots.extend(_parse_day(day_data))
        except Exception as exc:
            logger.warning("Could not fetch weather for %s: %s", d, exc)

    filtered = [
        (dt, snap) for dt, snap in all_snapshots
        if start_utc <= dt <= end_utc
    ]

    # Guarantee at least one snapshot even for sub-hourly windows
    if not filtered and all_snapshots:
        closest = min(all_snapshots, key=lambda x: abs((x[0] - start_utc).total_seconds()))
        filtered = [closest]

    return sorted(filtered, key=lambda x: x[0])


# ── Cache + fetch internals ────────────────────────────────────────────────────

async def _get_day_data(lat: float, lon: float, d: date) -> dict:
    key = (round(lat, 2), round(lon, 2), str(d))
    now = time.monotonic()
    if key in _day_cache:
        data, fetched_at = _day_cache[key]
        if now - fetched_at < _CACHE_TTL_S:
            logger.debug("Weather cache hit for %s", key)
            return data
    data = await _fetch_raw_day(lat, lon, d)
    _day_cache[key] = (data, now)
    return data


async def _fetch_raw_day(lat: float, lon: float, d: date) -> dict:
    date_str = str(d)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,relativehumidity_2m,precipitation,"
        "windspeed_10m,windgusts_10m,winddirection_10m"
        "&windspeed_unit=kmh"
        f"&start_date={date_str}&end_date={date_str}"
        "&timezone=UTC"
    )
    logger.info("Fetching Open-Meteo: lat=%s lon=%s date=%s", lat, lon, date_str)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _parse_day(data: dict) -> list[tuple[datetime, WeatherSnapshot]]:
    hourly = data.get("hourly", {})
    times: list[str] = hourly.get("time", [])
    results: list[tuple[datetime, WeatherSnapshot]] = []

    def _v(field: str, idx: int, default: float = 0.0) -> float:
        values = hourly.get(field, [])
        v = values[idx] if idx < len(values) else None
        return float(v) if v is not None else default

    for i, ts in enumerate(times):
        try:
            dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        snap = WeatherSnapshot(
            windSpeedKmh=_v("windspeed_10m", i),
            windGustKmh=_v("windgusts_10m", i),
            windDirectionDegrees=_v("winddirection_10m", i),
            temperatureC=_v("temperature_2m", i),
            humidity=_v("relativehumidity_2m", i),
            precipitationMm=_v("precipitation", i),
            source="open-meteo",
        )
        results.append((dt, snap))

    return results


def _fallback_snapshot() -> WeatherSnapshot:
    """Conservative defaults used when the API is unreachable."""
    return WeatherSnapshot(
        windSpeedKmh=20.0,
        windGustKmh=35.0,
        windDirectionDegrees=270.0,
        temperatureC=20.0,
        humidity=50.0,
        precipitationMm=0.0,
        source="fallback-defaults",
    )
