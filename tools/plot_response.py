"""
Plot the GeoJSON zones returned by POST /ai/risk-assess.

Reads the API JSON response from stdin or a file, so it works directly
in a curl pipeline:

    # Interactive window
    curl -s -X POST http://localhost:8000/ai/risk-assess \\
         -H 'Content-Type: application/json' \\
         -d @examples/request.json | python tools/plot_response.py

    # Save PNG
    curl -s -X POST http://localhost:8000/ai/risk-assess \\
         -H 'Content-Type: application/json' \\
         -d @examples/request.json | python tools/plot_response.py --output out.png

    # From a saved file
    python tools/plot_response.py --file /tmp/response.json --output out.png
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker


ZONE_STYLE = {
    "A1": {"face": "#E63946", "edge": "#9B1B26", "alpha": 0.50, "label": "A1 — Foarte ridicat (fix 7 km)"},
    "A2": {"face": "#F4A261", "edge": "#B5621A", "alpha": 0.40, "label": "A2 — Ridicat"},
    "A3": {"face": "#FFD166", "edge": "#C9A227", "alpha": 0.35, "label": "A3 — Mediu"},
    "A4": {"face": "#A8DADC", "edge": "#457B9D", "alpha": 0.25, "label": "A4 — Scăzut"},
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot /ai/risk-assess API response")
    p.add_argument("--file",   default=None, help="JSON response file (default: read stdin)")
    p.add_argument("--output", default=None, help="Save PNG instead of interactive display")
    return p.parse_args()


def _compass(deg: float) -> str:
    labels = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SV", 270: "V", 315: "NV"}
    return labels[min(labels, key=lambda d: abs(d - deg % 360))]


def _centre_of_feature(feature: dict) -> tuple[float, float]:
    """Return (centre_lon, centre_lat) approximated from the polygon ring."""
    ring = feature["geometry"]["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return sum(lons) / len(lons), sum(lats) / len(lats)


def _to_metres(ring: list, centre_lat: float, centre_lon: float) -> tuple[list, list]:
    m_lat = 111_320.0
    m_lon = m_lat * math.cos(math.radians(centre_lat))
    xs = [(p[0] - centre_lon) * m_lon for p in ring]
    ys = [(p[1] - centre_lat) * m_lat for p in ring]
    return xs, ys


def main() -> None:
    args = _parse_args()

    if args.file:
        with open(args.file) as fh:
            data = json.load(fh)
    else:
        raw = sys.stdin.read().strip()
        if not raw:
            print("ERROR: No input. Pipe curl output or use --file.", file=sys.stderr)
            sys.exit(1)
        data = json.loads(raw)

    if "detail" in data:
        print(f"API error: {data['detail']}", file=sys.stderr)
        sys.exit(1)

    # ── Extract fields ─────────────────────────────────────────────────────────
    features    = data["zones"]["features"]
    risk_score  = data["riskScore"]
    risk_level  = data["riskLevel"].upper().replace("_", " ")
    weather     = data["weatherUsed"]
    ef          = data["exposureFactors"]
    det         = data["deterministic"]
    notify_m    = data["notifyBeekeepersWithinMeters"]
    warnings    = data.get("warnings", [])

    wind_kmh    = weather["windSpeedKmh"]
    wind_dir    = weather["windDirectionDegrees"]
    gust_kmh    = weather["windGustKmh"]
    temp_c      = weather["temperatureC"]
    rain_mm     = weather["precipitationMm"]

    # Use the A1 feature centre as coordinate origin
    a1_feat = next(f for f in features if f["properties"]["zone"] == "A1")
    clon, clat = _centre_of_feature(a1_feat)

    # ── Figure ─────────────────────────────────────────────────────────────────
    fig, (ax_map, ax_info) = plt.subplots(
        1, 2, figsize=(14, 8),
        gridspec_kw={"width_ratios": [3, 1]},
    )
    fig.patch.set_facecolor("#F8F9FA")
    ax_map.set_facecolor("#EEF2F7")

    rendered: list[str] = []
    max_r = 0

    # Draw zones — features are already sorted largest-first by the API
    for feature in features:
        label  = feature["properties"]["zone"]
        radius = feature["properties"]["radiusMeters"]
        ring   = feature["geometry"]["coordinates"][0]
        style  = ZONE_STYLE.get(label, ZONE_STYLE["A4"])
        xs, ys = _to_metres(ring, clat, clon)
        ax_map.fill(xs, ys, color=style["face"], alpha=style["alpha"], zorder=2)
        ax_map.plot(xs, ys, color=style["edge"], linewidth=1.6, zorder=3)
        rendered.append(label)
        max_r = max(max_r, radius)

    # Centre marker
    ax_map.scatter([0], [0], color="#1D3557", s=130, zorder=6, marker="*")

    # Wind arrow
    downwind_rad = math.radians(wind_dir + 180)
    arrow_len = min(max_r * 0.48, 6500)
    ax_map.annotate(
        "",
        xy=(arrow_len * math.sin(downwind_rad), arrow_len * math.cos(downwind_rad)),
        xytext=(0, 0),
        arrowprops=dict(arrowstyle="-|>", color="#1D3557", lw=2.0, mutation_scale=18),
        zorder=7,
    )
    lx = arrow_len * 1.14 * math.sin(downwind_rad)
    ly = arrow_len * 1.14 * math.cos(downwind_rad)
    ax_map.text(lx, ly, f"Vânt\n{wind_kmh:.0f} km/h\n{_compass(wind_dir)}",
                ha="center", va="center", fontsize=8, color="#1D3557",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#1D3557", alpha=0.85),
                zorder=8)

    # Radius ticks
    for feature in features:
        label  = feature["properties"]["zone"]
        radius = feature["properties"]["radiusMeters"]
        color  = ZONE_STYLE.get(label, ZONE_STYLE["A4"])["edge"]
        pad    = max_r * 0.09
        ax_map.annotate(f"{label}\n{radius:,} m", xy=(radius, 0),
                        xytext=(radius, -pad), ha="center", fontsize=7.5, color=color,
                        arrowprops=dict(arrowstyle="-", color=color, lw=0.8), zorder=5)

    # Legend
    patches = [
        mpatches.Patch(fc=ZONE_STYLE[lbl]["face"], ec=ZONE_STYLE[lbl]["edge"],
                       alpha=0.85, label=ZONE_STYLE[lbl]["label"])
        for lbl in rendered
    ]
    ax_map.legend(handles=patches, loc="upper right", framealpha=0.92,
                  fontsize=8.5, title="Zone de risc", title_fontsize=9)

    # Axes
    pad = max_r * 1.22
    ax_map.set_xlim(-pad, pad)
    ax_map.set_ylim(-pad, pad)
    ax_map.set_aspect("equal")
    ax_map.grid(True, linestyle="--", alpha=0.4, color="white", zorder=1)

    def _fmt(x, _):
        return f"{x/1000:.1f} km" if abs(x) >= 1000 else f"{int(x)} m"

    ax_map.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt))
    ax_map.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt))
    ax_map.tick_params(labelsize=8)
    ax_map.set_title(
        f"Zone de risc pentru albine  ·  scor {risk_score:.2f}  ({risk_level})",
        fontsize=12, fontweight="bold", pad=10,
    )

    # ── Info panel ─────────────────────────────────────────────────────────────
    ax_info.axis("off")
    ax_info.set_facecolor("#F0F4F8")

    def _row(label: str, value: str, y: float, bold: bool = False):
        weight = "bold" if bold else "normal"
        ax_info.text(0.04, y, label, transform=ax_info.transAxes,
                     fontsize=8.5, color="#555", va="top")
        ax_info.text(0.04, y - 0.035, value, transform=ax_info.transAxes,
                     fontsize=9, color="#1D3557", va="top", fontweight=weight,
                     wrap=True)

    ld50_str = f"{det['ld50UsedUgPerBee']} µg/bee (EFSA)" if det.get("ld50UsedUgPerBee") else "fallback bucket"

    rows = [
        ("Scor risc",         f"{risk_score:.2f}  →  {risk_level}",             0.97, True),
        ("Notificare apicultori", f"{notify_m:,} m",                            0.88, True),
        ("",                  "",                                                0.81, False),
        ("Vânt (worst hour)", f"{wind_kmh:.0f} km/h · rafale {gust_kmh:.0f} km/h · {_compass(wind_dir)}", 0.79, False),
        ("Temperatură",       f"{temp_c:.0f} °C",                               0.71, False),
        ("Ploaie",            f"{rain_mm:.1f} mm/h",                            0.63, False),
        ("Worst hour UTC",    ef["worstCaseHourUtc"][:16],                       0.55, False),
        ("",                  "",                                                0.48, False),
        ("LD50 utilizat",     ld50_str,                                          0.46, False),
        ("Base radius",       f"{det['baseRadiusM']:.0f} m",                    0.38, False),
        ("Wind factor",       f"×{det['windFactor']:.3f}",                      0.30, False),
        ("Exposure mult.",    f"×{det['exposureMultiplier']:.3f}  "
                              f"(T={ef['temperatureFactor']:.1f} · "
                              f"t={ef['timeOfDayFactor']:.1f} · "
                              f"R={ef['rainFactor']:.1f})",                      0.22, False),
    ]
    for label, value, y, bold in rows:
        if label:
            _row(label, value, y, bold)

    # Warnings
    if warnings:
        ax_info.text(0.04, 0.13, "Avertizări", transform=ax_info.transAxes,
                     fontsize=8.5, color="#555", va="top")
        for i, w in enumerate(warnings[:4]):
            ax_info.text(0.04, 0.09 - i * 0.045, f"• {w}",
                         transform=ax_info.transAxes, fontsize=7.5,
                         color="#9B1B26", va="top", wrap=True)

    plt.tight_layout(pad=1.5)

    if args.output:
        plt.savefig(args.output, dpi=150, bbox_inches="tight")
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        plt.show()


if __name__ == "__main__":
    main()
