# Bee AI Risk Assessment Service

Microserviciu AI (Python / FastAPI) pentru evaluarea riscului tratamentelor agricole asupra albinelor.

## Rulare locală

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # configurați LLM_PROVIDER dacă doriți
uvicorn app.main:app --reload --port 8000
```

## Test rapid

```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/ai/risk-assess \
  -H 'Content-Type: application/json' \
  -d @examples/request.json | jq
```

## Vizualizare zone (plot)

Generează un grafic matplotlib cu cele trei zone de risc, fără să pornești serverul:

```bash
# Preview interactiv (default: high toxicity, 18 km/h wind, ground_boom)
python tools/plot_zones.py

# Salvează ca PNG
python tools/plot_zones.py --output examples/zones_preview.png

# Scenarii diferite
python tools/plot_zones.py --toxicity very_high --wind 35 --gust 60 --method aerial
python tools/plot_zones.py --toxicity low --wind 5 --total-kg 0.3
```

Toate opțiunile: `python tools/plot_zones.py --help`

## Testare

```bash
pytest -q
```

## Configurare LLM

Setați `LLM_PROVIDER` în `.env`:

| Valoare  | Cheie necesară    |
|----------|-------------------|
| `none`   | —                 |
| `openai` | `OPENAI_API_KEY`  |
| `gemini` | `GEMINI_API_KEY`  |

Fără LLM configurat, serviciul generează explicații din template-uri deterministe în română.

## Structura proiectului

```
app/
  main.py        # FastAPI app + routere /health și /ai/risk-assess
  schemas.py     # Pydantic: RiskRequest, RiskResponse, WeatherSnapshot, ...
  weather.py     # Client Open-Meteo + cache în memorie
  risk.py        # Calcul determinist scor + raze
  geometry.py    # Cerc / elipsă → Polygon GeoJSON (proiecție locală)
  llm.py         # LLMClient (Protocol) + OpenAILLM / GeminiLLM / NullLLM
  fallback.py    # Template RO pentru explicație fără LLM
tests/
  test_risk.py
  test_geometry.py
  test_endpoint.py
examples/
  request.json
```
