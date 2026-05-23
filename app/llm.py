"""LLM abstraction layer.

Provides a Protocol (LLMClient) and three implementations:
  - OpenAILLM   (requires OPENAI_API_KEY)
  - GeminiLLM   (requires GEMINI_API_KEY)
  - NullLLM     (always returns None → triggers fallback)

Selected via LLM_PROVIDER env var: "openai" | "gemini" | "none" (default).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class ExplainInput:
    product_name: str
    active_substance: str
    bee_toxicity: str
    total_amount_kg: float
    application_method: str
    wind_speed_kmh: float
    wind_direction_deg: float
    temperature_c: float
    risk_score: float
    risk_level: str
    r_high_m: float
    r_low_m: float


@dataclass
class ExplainOutput:
    explanation_ro: str
    warnings: list[str]
    recommended_action: str


@runtime_checkable
class LLMClient(Protocol):
    def explain(self, payload: ExplainInput) -> Optional[ExplainOutput]: ...


_SYSTEM_PROMPT = (
    "Ești un expert în protecția albinelor. Răspunzi EXCLUSIV cu JSON valid, "
    "fără text suplimentar, cu exact aceste chei: "
    "\"explanationRo\" (string), \"warnings\" (array of strings), \"recommendedAction\" (string). "
    "Folosește limba română."
)


def _build_user_prompt(p: ExplainInput) -> str:
    return (
        f"Produs: {p.product_name} (substanță activă: {p.active_substance}). "
        f"Toxicitate albine: {p.bee_toxicity}. "
        f"Cantitate totală aplicată: {p.total_amount_kg} kg. "
        f"Metodă aplicare: {p.application_method}. "
        f"Vânt: {p.wind_speed_kmh} km/h, direcție {p.wind_direction_deg}°. "
        f"Temperatură: {p.temperature_c}°C. "
        f"Scor risc: {p.risk_score:.2f} ({p.risk_level}). "
        f"Raza maximă de pericol: {int(p.r_high_m)} m, notificare apicultori până la {int(p.r_low_m)} m. "
        "Generează o explicație scurtă, o listă de 2-4 avertizări și o acțiune recomandată."
    )


def _parse_llm_response(text: str) -> Optional[ExplainOutput]:
    try:
        # Strip potential markdown code fences
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        data = json.loads(cleaned.strip())
        return ExplainOutput(
            explanation_ro=str(data["explanationRo"]),
            warnings=[str(w) for w in data.get("warnings", [])],
            recommended_action=str(data["recommendedAction"]),
        )
    except Exception as exc:
        logger.warning("Failed to parse LLM response: %s | raw=%r", exc, text[:200])
        return None


class NullLLM:
    """Always returns None so the fallback template is used."""

    def explain(self, payload: ExplainInput) -> Optional[ExplainOutput]:
        return None


class OpenAILLM:
    def __init__(self) -> None:
        import openai  # lazy import

        self._client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def explain(self, payload: ExplainInput) -> Optional[ExplainOutput]:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(payload)},
                ],
                temperature=0.3,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or ""
            return _parse_llm_response(text)
        except Exception as exc:
            logger.error("OpenAI LLM error: %s", exc)
            return None


class GeminiLLM:
    def __init__(self) -> None:
        import google.generativeai as genai  # lazy import

        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self._model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=_SYSTEM_PROMPT,
        )

    def explain(self, payload: ExplainInput) -> Optional[ExplainOutput]:
        try:
            resp = self._model.generate_content(
                _build_user_prompt(payload),
                generation_config={"temperature": 0.3, "max_output_tokens": 512},
            )
            text = resp.text or ""
            return _parse_llm_response(text)
        except Exception as exc:
            logger.error("Gemini LLM error: %s", exc)
            return None


def build_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "none").lower()
    if provider == "openai":
        logger.info("Using OpenAI LLM provider")
        return OpenAILLM()
    if provider == "gemini":
        logger.info("Using Gemini LLM provider")
        return GeminiLLM()
    logger.info("LLM_PROVIDER=none — using NullLLM (fallback templates)")
    return NullLLM()
