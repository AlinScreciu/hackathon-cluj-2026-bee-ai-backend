"""
Visualise bee-risk zones (A1–A4 model).

A1 = fixed 7 km — always shown (red).
A2/A3/A4 = computed — shown only if radius > 7 km (orange / yellow / teal).

Usage (from project root, with venv active):

    python tools/plot_zones.py                                 # default example
    python tools/plot_zones.py --substance deltamethrin --wind 35 --gust 60
    python tools/plot_zones.py --substance thiamethoxam --method aerial --total-kg 0.05
    python tools/plot_zones.py --help

No running server required — imports app modules directly.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker

from app.geometry import build_zones
from app.ld50_data import lookup_ld50
from app.risk import A1_RADIUS_M, compute_risk
from app.schemas import WeatherSnapshot

ZONE_STYLE = {
    "A1": {"face": "#E63946", "edge": "#9B1B26", "alpha": 0.50, "label": "A1 — Foarte ridicat (fix 7 km)"},
    "A2": {"face": "#F4A261", "edge": "#B5621A", "alpha": 0.40, "label": "A2 — Ridicat"},
    "A3": {"face": "#FFD166", "edge": "#C9A227", "alpha": 0.35, "label": "A3 — Mediu"},
    "A4": {"face": "#A8DADC", "edge": "#457B9D", "alpha": 0.25, "label": "A4 — Scăzut"},
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot bee-risk A1–A4 zones")
    p.add_argument("--substance",  default="",          help="Active substance (EFSA LD50 lookup)")
    p.add_argument("--toxicity",   default="high",      choices=["low","medium","high","very_high"])
    p.add_argument("--total-kg",   type=float, default=1.4)
    p.add_argument("--method",     default="ground_boom", choices=["ground_boom","airblast","aerial"])
    p.add_argument("--wind",       type=float, default=18.0,  help="Wind speed km/h")
    p.add_argument("--gust",       type=float, default=31.0,  help="Wind gust km/h")
    p.add_argument("--wind-dir",   type=float, default=240.0, help="Wind direction (FROM), degrees")
    p.add_argument("--temp",       type=float, default=24.0)
    p.add_argument("--rain",       type=float, default=0.0,   help="Precipitation mm/h")
    p.add_argument("--temp-factor",type=float, default=None,  help="Override temperature factor [0–1]")
    p.add_argument("--time-factor",type=float, default=1.0,   help="Time-of-day factor [0–1]")
    p.add_argument("--lat",        type=float, default=46.7712)
    p.add_argument("--lon",        type=float, default=23.6236)
    p.add_argument("--output",     default=None,               help="Save PNG instead of interactive")
    return p.parse_args()


def _compass(degrees: float) -> str:
    labels = {0:"N",45:"NE",90:"E",135:"SE",180:"S",225:"SW",270:"V",315:"NV"}
    closest = min(labels, key=lambda d: abs(d - degrees % 360))
    return labels[closest]


def _to_metres(coords_lonlat: list, center_lat: float, center_lon: float):
    m_lat = 111_320.0
    m_lon = m_lat * math.cos(math.radians(center_lat))
    xs = [(pt[0] - center_lon) * m_lon for pt in coords_lonlat]
    ys = [(pt[1] - center_lat) * m_lat for pt in coords_lonlat]
    return xs, ys


def main() -> None:
    args = _parse_args()

    from app.risk import _rain_factor, _temp_factor
    temp_f = args.temp_factor if args.temp_factor is not None else _temp_factor(args.temp)
    rain_f = _rain_factor(args.rain)

    weather = WeatherSnapshot(windSpeedKmh=args.wind, windGustKmh=args.gust,
                               windDirectionDegrees=args.wind_dir, temperatureC=args.temp,
                               humidity=50.0, precipitationMm=args.rain, source="plot-input")

    ld50 = lookup_ld50(args.substance) if args.substance else None

    risk_score, risk_level, r_a2, r_a3, r_a4, details = compute_risk(
        bee_toxicity=args.toxicity,
        active_substance=args.substance,
        total_amount_kg=args.total_kg,
        application_method=args.method,
        weather=weather,
        temp_factor=temp_f,
        time_factor=args.time_factor,
        rain_factor=rain_f,
    )

    zones = build_zones(args.lat, args.lon, r_a2, r_a3, r_a4,
                        args.wind, args.wind_dir)

    # ── figure ─────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(9, 8))
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#EEF2F7")

    rendered: list[str] = []

    # Features are already largest-first; draw in that order
    for feature in zones["features"]:
        label   = feature["properties"]["zone"]
        ring    = feature["geometry"]["coordinates"][0]
        style   = ZONE_STYLE[label]
        xs, ys  = _to_metres(ring, args.lat, args.lon)
        ax.fill(xs, ys, color=style["face"], alpha=style["alpha"], zorder=2)
        ax.plot(xs, ys, color=style["edge"], linewidth=1.6, zorder=3)
        rendered.append(label)

    # Centre marker
    ax.scatter([0], [0], color="#1D3557", s=120, zorder=6, marker="*",
               label="Centrul parcelei")

    # Wind arrow (downwind direction)
    max_r = max(A1_RADIUS_M, r_a4)
    downwind_rad = math.radians(args.wind_dir + 180)
    arrow_len = min(max_r * 0.5, A1_RADIUS_M * 0.55)
    ax.annotate("", xy=(arrow_len * math.sin(downwind_rad), arrow_len * math.cos(downwind_rad)),
                xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color="#1D3557", lw=2.0, mutation_scale=18),
                zorder=7)
    lx = arrow_len * 1.15 * math.sin(downwind_rad)
    ly = arrow_len * 1.15 * math.cos(downwind_rad)
    ax.text(lx, ly, f"Vânt\n{args.wind:.0f} km/h\n{_compass(args.wind_dir)}",
            ha="center", va="center", fontsize=8, color="#1D3557",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#1D3557", alpha=0.85), zorder=8)

    # Radius ticks on the x-axis
    tick_zones = [("A1", A1_RADIUS_M, ZONE_STYLE["A1"]["edge"])]
    for lbl, r in (("A2", r_a2), ("A3", r_a3), ("A4", r_a4)):
        if r > A1_RADIUS_M:
            tick_zones.append((lbl, r, ZONE_STYLE[lbl]["edge"]))
    for lbl, r, col in tick_zones:
        ax.annotate(f"{lbl}\n{int(round(r))} m", xy=(r, 0),
                    xytext=(r, -max_r * 0.09), ha="center", fontsize=7.5, color=col,
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.8), zorder=5)

    # Legend
    legend_patches = [
        mpatches.Patch(fc=ZONE_STYLE[lbl]["face"], ec=ZONE_STYLE[lbl]["edge"],
                       alpha=0.85, label=ZONE_STYLE[lbl]["label"])
        for lbl in rendered
    ]
    ax.legend(handles=legend_patches, loc="upper right", framealpha=0.92,
              fontsize=8.5, title="Zone de risc", title_fontsize=9)

    # Axes
    pad = max_r * 1.22
    ax.set_xlim(-pad, pad)
    ax.set_ylim(-pad, pad)
    ax.set_aspect("equal")
    ax.grid(True, linestyle="--", alpha=0.4, color="white", zorder=1)

    def _fmt(x, _):
        return f"{x/1000:.1f} km" if abs(x) >= 1000 else f"{int(x)} m"

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt))
    ax.tick_params(labelsize=8)

    # Title + info
    method_lbl = {"ground_boom": "Rampă", "airblast": "Pulverizator", "aerial": "Aeronavă"}
    subst_part = f"{args.substance}  (LD50 = {ld50} µg/bee)  ·  " if ld50 else \
                 (f"{args.substance}  (necunoscut)  ·  " if args.substance else "")

    a2a4_note = ""
    if "A2" not in rendered:
        a2a4_note = "  [A2/A3/A4 în interiorul A1 — nu sunt afișate]"

    ax.set_title(
        f"Zone risc albine  ·  scor {risk_score:.2f}  ({risk_level.upper().replace('_',' ')}){a2a4_note}",
        fontsize=12, fontweight="bold", pad=12)

    info = (
        f"{subst_part}Cantitate: {args.total_kg} kg  |  Metodă: {method_lbl[args.method]}\n"
        f"Vânt: {args.wind} km/h, rafale {args.gust} km/h, dir. {args.wind_dir:.0f}°  |  "
        f"Temp.: {args.temp}°C  |  Ploaie: {args.rain} mm/h  |  ×1.5 safety\n"
        f"temp_factor={temp_f:.2f}  ·  time_factor={args.time_factor:.2f}  ·  "
        f"rain_factor={rain_f:.2f}  ·  exposure_mult={details.exposureMultiplier:.3f}"
    )
    ax.set_xlabel(info, fontsize=7.5, labelpad=10, color="#555")

    plt.tight_layout()

    if args.output:
        plt.savefig(args.output, dpi=150, bbox_inches="tight")
        print(f"Saved to {args.output}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
