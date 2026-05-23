"""Deterministic Romanian-language fallback templates.

Used when LLM_PROVIDER=none or when the LLM call fails.
"""

from __future__ import annotations

import math

from app.llm import ExplainInput, ExplainOutput

_TOXICITY_LABEL = {
    "low": "scăzută",
    "medium": "medie",
    "high": "ridicată",
    "very_high": "foarte ridicată",
}

_RISK_LABEL = {
    "low": "scăzut",
    "medium": "moderat",
    "high": "ridicat",
    "very_high": "foarte ridicat",
}

_METHOD_LABEL = {
    "ground_boom": "rampa terestră",
    "airblast": "pulverizator cu ventilator",
    "aerial": "aeronavă",
}

_DIRECTION_LABEL = {
    0: "nord",
    45: "nord-est",
    90: "est",
    135: "sud-est",
    180: "sud",
    225: "sud-vest",
    270: "vest",
    315: "nord-vest",
}


def _compass(degrees: float) -> str:
    normalized = degrees % 360
    closest = min(_DIRECTION_LABEL.keys(), key=lambda d: abs(d - normalized))
    return _DIRECTION_LABEL[closest]


def generate_fallback(p: ExplainInput) -> ExplainOutput:
    toxicity_ro = _TOXICITY_LABEL.get(p.bee_toxicity, p.bee_toxicity)
    risk_ro = _RISK_LABEL.get(p.risk_level, p.risk_level)
    method_ro = _METHOD_LABEL.get(p.application_method, p.application_method)
    wind_dir_ro = _compass(p.wind_direction_deg)
    notify_km = round(p.r_low_m / 1000, 1)
    high_km = round(p.r_high_m / 1000, 1)

    explanation = (
        f"Riscul pentru albine este {risk_ro} (scor {p.risk_score:.2f}). "
        f"Produsul '{p.product_name}' conține substanța activă '{p.active_substance}', "
        f"cu toxicitate {toxicity_ro} pentru albine. "
        f"Au fost aplicate {p.total_amount_kg} kg prin {method_ro}. "
        f"Vântul de {p.wind_speed_kmh:.0f} km/h din direcția {wind_dir_ro} "
        f"extinde zona de pericol imediat până la {high_km} km "
        f"și zona de avertizare până la {notify_km} km."
    )

    warnings: list[str] = [
        f"Substanță activă cu toxicitate {toxicity_ro} pentru albine.",
    ]

    if p.wind_speed_kmh >= 5:
        warnings.append(
            f"Vântul de {p.wind_speed_kmh:.0f} km/h extinde zona afectată spre {wind_dir_ro}."
        )

    if p.temperature_c >= 20:
        warnings.append(
            f"Temperatura ridicată ({p.temperature_c:.0f}°C) crește activitatea albinelor în câmp."
        )

    if p.bee_toxicity in ("high", "very_high"):
        warnings.append(
            f"Avertizați apicultorii pe minim {notify_km} km în direcția vântului."
        )

    # Recommended action
    if p.risk_score >= 0.75:
        action = (
            f"Anunțați apicultorii pe o rază de {notify_km} km cu minim 48h înainte; "
            "aplicați seara, după ora 21:00, când albinele sunt în stup."
        )
    elif p.risk_score >= 0.50:
        action = (
            f"Anunțați apicultorii pe o rază de {notify_km} km cu minim 24h înainte; "
            "evitați aplicarea în perioadele de zbor intens (09:00–17:00)."
        )
    elif p.risk_score >= 0.25:
        action = (
            f"Informați apicultorii din zona {notify_km} km; "
            "preferați aplicarea dimineața devreme sau seara."
        )
    else:
        action = (
            "Riscul este redus, dar respectați bunele practici agricole: "
            "evitați aplicarea pe flori deschise și pe vânt puternic."
        )

    return ExplainOutput(
        explanation_ro=explanation,
        warnings=warnings,
        recommended_action=action,
    )
