"""Tests for GeoJSON geometry generation (A1–A4 zone model)."""

import pytest

from app.geometry import N_VERTICES, _circle, _ellipse, build_zones
from app.risk import A1_RADIUS_M

LAT, LON = 46.7712, 23.6236


def test_circle_vertex_count():
    assert len(_circle(LAT, LON, 500.0)) == N_VERTICES


def test_ellipse_vertex_count():
    assert len(_ellipse(LAT, LON, 500.0, 240.0)) == N_VERTICES


def test_closed_ring_circle():
    zones = build_zones(LAT, LON, 100, 200, 350, wind_speed_kmh=0.0, wind_direction_deg=0.0)
    for f in zones["features"]:
        ring = f["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]


def test_closed_ring_ellipse():
    zones = build_zones(LAT, LON, 100, 200, 350, wind_speed_kmh=20.0, wind_direction_deg=270.0)
    for f in zones["features"]:
        ring = f["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]


def test_only_a1_when_radii_below_7km():
    """When A2/A3/A4 are all < 7 km, only A1 should appear."""
    zones = build_zones(LAT, LON, r_a2=500, r_a3=1000, r_a4=1750,
                        wind_speed_kmh=5.0, wind_direction_deg=240.0)
    labels = [f["properties"]["zone"] for f in zones["features"]]
    assert labels == ["A1"]


def test_a4_appears_when_exceeds_7km():
    """A4 at 8 km should appear; A2/A3 that are below 7 km should not."""
    big_r_a4 = A1_RADIUS_M + 1000
    zones = build_zones(LAT, LON, r_a2=500, r_a3=1000, r_a4=big_r_a4,
                        wind_speed_kmh=5.0, wind_direction_deg=240.0)
    labels = {f["properties"]["zone"] for f in zones["features"]}
    assert "A1" in labels
    assert "A4" in labels
    assert "A2" not in labels
    assert "A3" not in labels


def test_all_zones_when_all_exceed_7km():
    r_a2 = A1_RADIUS_M + 100
    r_a3 = A1_RADIUS_M + 500
    r_a4 = A1_RADIUS_M + 2000
    zones = build_zones(LAT, LON, r_a2=r_a2, r_a3=r_a3, r_a4=r_a4,
                        wind_speed_kmh=10.0, wind_direction_deg=240.0)
    labels = {f["properties"]["zone"] for f in zones["features"]}
    assert labels == {"A1", "A2", "A3", "A4"}


def test_a1_radius_always_7km():
    zones = build_zones(LAT, LON, 100, 200, 350, wind_speed_kmh=5.0, wind_direction_deg=0.0)
    a1 = next(f for f in zones["features"] if f["properties"]["zone"] == "A1")
    assert a1["properties"]["radiusMeters"] == int(A1_RADIUS_M)


def test_features_ordered_largest_first():
    """Features should be sorted by radius descending so maps render correctly."""
    r_a2 = A1_RADIUS_M + 500
    r_a3 = A1_RADIUS_M + 1500
    r_a4 = A1_RADIUS_M + 3000
    zones = build_zones(LAT, LON, r_a2, r_a3, r_a4, 10.0, 240.0)
    radii = [f["properties"]["radiusMeters"] for f in zones["features"]]
    assert radii == sorted(radii, reverse=True)


def test_determinism():
    z1 = build_zones(LAT, LON, 500, 1000, 1750, 18.0, 240.0)
    z2 = build_zones(LAT, LON, 500, 1000, 1750, 18.0, 240.0)
    assert z1 == z2
