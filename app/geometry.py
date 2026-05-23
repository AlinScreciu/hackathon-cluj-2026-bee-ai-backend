"""Build GeoJSON zones for the A1–A4 bee-risk model.

A1  Fixed 7 km polygon — always included.
A2  Computed polygon — included only when radius > A1_RADIUS_M.
A3  Computed polygon — included only when radius > A1_RADIUS_M.
A4  Computed polygon — included only when radius > A1_RADIUS_M.

All polygons are full shapes from the parcel centre (not rings/donuts).
When A2/A3/A4 are rendered they extend beyond A1; the frontend/map layer
handles visual stacking. Features are ordered largest-first so renderers
that draw in list order paint smaller zones on top automatically.

Shape selection:
  wind < 5 km/h  → concentric circles
  wind ≥ 5 km/h  → ellipses elongated downwind, centre offset 25 % of R
"""

from __future__ import annotations

import math
from typing import Any

from app.risk import A1_RADIUS_M

N_VERTICES     = 64
M_PER_DEG_LAT  = 111_320.0


def _m_per_deg_lon(lat_deg: float) -> float:
    return M_PER_DEG_LAT * math.cos(math.radians(lat_deg))


def _make_polygon(coords: list[tuple[float, float]]) -> dict[str, Any]:
    ring = [[round(lon, 7), round(lat, 7)] for lat, lon in coords]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _circle(center_lat: float, center_lon: float, radius_m: float) -> list[tuple[float, float]]:
    m_lon = _m_per_deg_lon(center_lat)
    return [
        (
            center_lat + radius_m * math.cos(2 * math.pi * i / N_VERTICES) / M_PER_DEG_LAT,
            center_lon + radius_m * math.sin(2 * math.pi * i / N_VERTICES) / m_lon,
        )
        for i in range(N_VERTICES)
    ]


def _ellipse(
    center_lat: float,
    center_lon: float,
    radius_m: float,
    wind_direction_deg: float,
) -> list[tuple[float, float]]:
    """Wind-elongated ellipse offset downwind from the parcel centre.

    semi-major = radius_m  (downwind direction)
    semi-minor = radius_m × 0.6
    centre offset = 0.25 × radius_m downwind
    """
    semi_major  = radius_m
    semi_minor  = radius_m * 0.6
    offset_m    = radius_m * 0.25

    # Meteorological: FROM direction. Downwind = direction + 180°.
    downwind_rad = math.radians(wind_direction_deg + 180.0)
    m_lon = _m_per_deg_lon(center_lat)

    ell_lat = center_lat + offset_m * math.cos(downwind_rad) / M_PER_DEG_LAT
    ell_lon = center_lon + offset_m * math.sin(downwind_rad) / m_lon

    points: list[tuple[float, float]] = []
    for i in range(N_VERTICES):
        t   = 2 * math.pi * i / N_VERTICES
        u   = semi_major * math.cos(t)
        v   = semi_minor * math.sin(t)
        # Rotate: major axis aligned downwind (tilt from north toward east)
        x   = u * math.sin(downwind_rad) + v * math.cos(downwind_rad)
        y   = u * math.cos(downwind_rad) - v * math.sin(downwind_rad)
        points.append((ell_lat + y / M_PER_DEG_LAT, ell_lon + x / m_lon))

    return points


def build_zones(
    center_lat: float,
    center_lon: float,
    r_a2: float,
    r_a3: float,
    r_a4: float,
    wind_speed_kmh: float,
    wind_direction_deg: float,
) -> dict[str, Any]:
    """Return a GeoJSON FeatureCollection.

    A1 is always included at A1_RADIUS_M (7 km).
    A2/A3/A4 are full polygons from centre but only included if radius > A1_RADIUS_M,
    since inside A1 they are less important than the fixed 7 km boundary.
    Features are ordered largest-radius-first for correct visual layering.
    """
    use_ellipse = wind_speed_kmh >= 5.0

    def _shape(label: str, radius_m: float) -> list[tuple[float, float]]:
        # A1 is always a circle — it is a fixed notification perimeter,
        # not a drift model, so wind direction should not skew it.
        if label == "A1" or not use_ellipse:
            return _circle(center_lat, center_lon, radius_m)
        return _ellipse(center_lat, center_lon, radius_m, wind_direction_deg)

    def _feature(label: str, radius_m: float) -> dict[str, Any]:
        return {
            "type": "Feature",
            "properties": {"zone": label, "radiusMeters": int(round(radius_m))},
            "geometry": _make_polygon(_shape(label, radius_m)),
        }

    # Build candidate list; A2/A3/A4 only when they extend beyond A1
    candidates: list[tuple[str, float]] = [("A1", A1_RADIUS_M)]
    for label, radius in (("A2", r_a2), ("A3", r_a3), ("A4", r_a4)):
        if radius > A1_RADIUS_M:
            candidates.append((label, radius))

    # Render largest first so map layers paint smaller zones on top
    candidates.sort(key=lambda x: x[1], reverse=True)

    return {
        "type": "FeatureCollection",
        "features": [_feature(label, radius) for label, radius in candidates],
    }
