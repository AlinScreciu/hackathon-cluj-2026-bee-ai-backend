"""Acute contact LD50 values (µg/bee) for honeybees (Apis mellifera).

Source: EFSA peer review reports and EU pesticide dossiers.
All values are acute contact LD50 unless noted.

Values of 200.0 mean "practically non-toxic to bees (>200 µg/bee)" — the
real measured value is at or above that ceiling; we store the ceiling so the
formula still produces a non-zero (but small) safe zone.

Usage:
    from app.ld50_data import lookup_ld50
    ld50 = lookup_ld50("lambda-cyhalothrin")  # → 0.038
    ld50 = lookup_ld50("unknown substance")   # → None  (triggers fallback)
"""

from __future__ import annotations

# Keys are normalised: lowercase, spaces/underscores replaced by hyphens.
LD50_CONTACT_UG_PER_BEE: dict[str, float] = {

    # ── Neonicotinoids ─────────────────────────────────────────────────────────
    # Highly water-soluble; systemic uptake by plants; major bee-decline driver.
    "imidacloprid":      0.0037,   # Confidor, Gaucho
    "thiamethoxam":      0.0024,   # Actara, Cruiser
    "clothianidin":      0.0044,   # Poncho, Dantop
    "acetamiprid":       7.100,    # Mospilan — significantly safer than other neonics
    "thiacloprid":      17.320,    # Calypso — least toxic neonic, now withdrawn in EU
    "nitenpyram":        0.200,    # Capstar

    # ── Pyrethroids ───────────────────────────────────────────────────────────
    # Fast knock-down; highly toxic to bees on contact; degrade quickly.
    "deltamethrin":      0.0015,   # Decis
    "lambda-cyhalothrin":0.038,    # Karate, Kung-Fu
    "cypermethrin":      0.020,    # Ripcord, many generics
    "alpha-cypermethrin":0.059,    # Fastac
    "zeta-cypermethrin": 0.024,    # Fury
    "bifenthrin":        0.015,    # Talstar
    "permethrin":        0.029,    # many generics
    "esfenvalerate":     0.0026,   # Sumi-Alpha
    "tau-fluvalinate":   0.200,    # Mavrik — used INSIDE beehives (Varroa); rel. safe
    "tefluthrin":        0.024,    # Force (soil application)
    "beta-cyfluthrin":   0.010,    # Bulldock
    "gamma-cyhalothrin": 0.038,    # Proaxis
    "etofenprox":        0.120,    # Trebon

    # ── Organophosphates ──────────────────────────────────────────────────────
    # Acetylcholinesterase inhibitors; broad spectrum; moderate-high bee toxicity.
    "chlorpyrifos":      0.160,    # Dursban (EU ban 2020, still relevant)
    "dimethoate":        0.152,    # Rogor, Bi-58
    "malathion":         0.180,    # many generics
    "pirimiphos-methyl": 0.220,    # Actellic
    "chlorpyrifos-methyl":0.200,   # Reldan
    "phosmet":           0.066,    # Imidan
    "azinphos-methyl":   0.086,    # Gusathion

    # ── Carbamates ────────────────────────────────────────────────────────────
    "methomyl":          0.168,    # Lannate
    "thiodicarb":        0.068,    # Larvin
    "pirimicarb":       10.000,    # Pirimor — aphid-selective, relatively safe for bees

    # ── Diamides (anthranilic amides) ─────────────────────────────────────────
    # Ryanodine receptor activators; low bee contact toxicity.
    "chlorantraniliprole":200.0,   # Coragen, Altacor
    "cyantraniliprole":  200.0,    # Exirel
    "flubendiamide":     200.0,    # Belt (withdrawn EU)

    # ── Spinosyns ─────────────────────────────────────────────────────────────
    # Fermentation-derived; "organic" but ACUTELY very toxic to bees on contact.
    "spinosad":          0.0025,   # Conserve, Tracer — do not apply on flowering crops
    "spinetoram":        0.040,    # Radiant

    # ── Avermectins ──────────────────────────────────────────────────────────
    "abamectin":         0.009,    # Vertimec
    "emamectin-benzoate":0.0013,   # Affirm — very high contact toxicity

    # ── Other insecticides ────────────────────────────────────────────────────
    "indoxacarb":        1.600,    # Avaunt, Steward
    "spirotetramat":    53.400,    # Movento — low bee toxicity
    "flonicamid":      100.000,    # Teppeki — low bee toxicity, aphid-selective
    "sulfoxaflor":       0.379,    # Closer
    "flupyradifurone":   1.200,    # Sivanto
    "cyflometophen":    10.000,
    "tolfenpyrad":       0.058,    # Hachikusan
    "pyriproxyfen":     10.000,    # Sumilarv (IGR, not insecticidal to adults)
    "buprofezin":       10.000,    # IGR

    # ── Fungicides (generally low-to-no bee contact toxicity) ─────────────────
    "tebuconazole":     200.0,
    "propiconazole":    200.0,
    "epoxiconazole":    200.0,
    "azoxystrobin":     200.0,
    "carbendazim":      200.0,
    "chlorothalonil":    26.8,     # Bravo — low but measurable
    "iprodione":        100.0,     # Rovral
    "mancozeb":         200.0,
    "metalaxyl":        200.0,
    "captan":           200.0,
    "flutriafol":       200.0,
    "boscalid":         200.0,
    "trifloxystrobin":  200.0,
    "kresoxim-methyl":  200.0,
    "prothioconazole":  200.0,
    "fluopyram":        200.0,

    # ── Herbicides (practically non-toxic to bees) ────────────────────────────
    "glyphosate":       200.0,
    "2,4-d":            200.0,
    "pendimethalin":    200.0,
    "metazachlor":      200.0,
    "clomazone":        200.0,
    "isoxaflutole":     200.0,
    "s-metolachlor":    200.0,
    "flufenacet":       200.0,
    "mesotrione":       200.0,
    "nicosulfuron":     200.0,
    "foramsulfuron":    200.0,
}

# Common trade name fragments → active substance (best-effort, not exhaustive)
_TRADE_NAME_HINTS: dict[str, str] = {
    "decis":        "deltamethrin",
    "karate":       "lambda-cyhalothrin",
    "fastac":       "alpha-cypermethrin",
    "actara":       "thiamethoxam",
    "mospilan":     "acetamiprid",
    "confidor":     "imidacloprid",
    "gaucho":       "imidacloprid",
    "coragen":      "chlorantraniliprole",
    "movento":      "spirotetramat",
    "teppeki":      "flonicamid",
    "sivanto":      "flupyradifurone",
    "calypso":      "thiacloprid",
    "vertimec":     "abamectin",
    "tracer":       "spinosad",
    "conserve":     "spinosad",
    "pirimor":      "pirimicarb",
    "rogor":        "dimethoate",
}


def _normalise(name: str) -> str:
    return name.lower().strip().replace(" ", "-").replace("_", "-")


def lookup_ld50(active_substance: str) -> float | None:
    """Return LD50 (µg/bee, acute contact) for the given active substance.

    Normalises the input (case, hyphens/spaces) and tries:
    1. Direct match in the LD50 table.
    2. Match ignoring hyphens (e.g. 'lambdacyhalothrin' finds 'lambda-cyhalothrin').
    3. Trade-name hint lookup.

    Returns None if the substance is not in the table, so callers can fall
    back to the toxicity-label buckets.
    """
    key = _normalise(active_substance)

    if key in LD50_CONTACT_UG_PER_BEE:
        return LD50_CONTACT_UG_PER_BEE[key]

    # Try without hyphens
    stripped = key.replace("-", "")
    for table_key, value in LD50_CONTACT_UG_PER_BEE.items():
        if table_key.replace("-", "") == stripped:
            return value

    # Try trade-name hints
    for hint, substance in _TRADE_NAME_HINTS.items():
        if hint in key:
            return LD50_CONTACT_UG_PER_BEE.get(substance)

    return None
