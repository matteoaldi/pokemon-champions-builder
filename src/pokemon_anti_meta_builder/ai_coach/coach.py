from __future__ import annotations

import json
import os
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
# Fallback chain when the primary model returns 429/quota. Listed from most
# preferred (cheaper/free tier reliable) to last-resort.
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash")

SETUP_HINT = (
    "AI Coach offline. Per attivarlo gratis: vai su https://aistudio.google.com, "
    "fai login col tuo account Google, clicca 'Get API key' e copia la chiave. "
    "Poi lancia il server con:\n"
    "  GEMINI_API_KEY=la_tua_chiave PYTHONPATH=src python3 -m pokemon_anti_meta_builder serve ...\n"
    "Free tier Gemini: 15 req/min, 1500 req/giorno. Nessuna carta richiesta."
)


class AICoach:
    """Gemini-backed VGC Reg M-A coach.

    The deterministic engine (TeamBuilder/ThreatAnalyzer/RecommendationService)
    owns legality, scoring and validation. Gemini only reads the structured
    state we computed and gives a human-readable summary + game plan.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None, insecure_ssl: bool = False):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.context = ssl._create_unverified_context() if insecure_ssl else None

    def advise(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return {
                "enabled": False,
                "needsSetup": True,
                "advice": _fallback_advice(state),
                "setupHint": SETUP_HINT,
            }

        prompt = _build_prompt(state)
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.6, "maxOutputTokens": 800},
        }
        payload = json.dumps(body).encode("utf-8")
        models_to_try: list[str] = []
        for name in (self.model, *FALLBACK_MODELS):
            if name and name not in models_to_try:
                models_to_try.append(name)

        last_error: str | None = None
        for model_name in models_to_try:
            url = GEMINI_ENDPOINT.format(model=model_name, key=self.api_key)
            try:
                data = self._post_json(url, payload, self.context)
            except URLError as exc:
                reason = str(exc.reason).lower() if hasattr(exc, "reason") else str(exc).lower()
                if "certificate" in reason or "ssl" in reason:
                    try:
                        data = self._post_json(url, payload, ssl._create_unverified_context())
                    except Exception as inner:  # noqa: BLE001
                        last_error = str(inner)
                        continue
                else:
                    last_error = str(exc)
                    continue
            except HTTPError as exc:
                last_error = f"HTTP {exc.code}"
                if exc.code in (429, 503):
                    # quota / overload → try next model in the chain
                    continue
                # other HTTP errors aren't fixable by switching model → bail
                return {"enabled": False, "error": last_error, "advice": _fallback_advice(state)}
            except (TimeoutError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                continue

            advice = _extract_gemini_text(data)
            if advice:
                return {"enabled": True, "model": model_name, "advice": advice}
            last_error = "empty response"

        return {"enabled": False, "error": last_error or "no model succeeded", "advice": _fallback_advice(state)}

    def _post_json(self, url: str, payload: bytes, context) -> dict[str, Any]:
        request = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=45, context=context) as response:
            return json.loads(response.read().decode("utf-8"))


def _build_prompt(state: dict[str, Any]) -> str:
    team = [
        {
            "name": m.get("species"),
            "types": m.get("types", []),
            "item": m.get("item"),
            "ability": m.get("ability"),
            "nature": m.get("nature"),
            "moves": m.get("moves", []),
        }
        for m in state.get("team", [])
    ]
    threats = [
        {"name": t.get("name"), "usage": t.get("usage"), "severity": t.get("severity"), "summary": t.get("summary")}
        for t in (state.get("threatEntries") or [])[:8]
    ]
    digest = state.get("digest") or {}
    digest_lite = {
        "team_size": digest.get("team_size"),
        "top_threats": [t.get("name") for t in (digest.get("top_threats") or [])[:5]],
        "top_counters": [c.get("name") for c in (digest.get("top_counters") or [])[:5]],
    }
    recommendations = [r.get("name") for r in (state.get("recommendations") or [])[:5]]
    warnings = state.get("warnings") or []
    synergy = state.get("synergy") or []

    return (
        "Sei un coach competitivo per Pokémon Champions, Regulation M-A. "
        "Rispondi SEMPRE in italiano, conciso (max 200 parole). "
        "Champions NON ha Tera, ma supporta Mega Evoluzioni (una sola Mega per team). "
        "L'engine deterministico ha già validato legalità e mosse, fidati di quello.\n\n"
        f"Team attuale ({len(team)}/6):\n{json.dumps(team, ensure_ascii=False, indent=2)}\n\n"
        f"Analisi minacce (top 8):\n{json.dumps(threats, ensure_ascii=False, indent=2)}\n\n"
        f"Digest aggregato:\n{json.dumps(digest_lite, ensure_ascii=False, indent=2)}\n\n"
        f"Note synergy: {synergy}\n"
        f"Top raccomandazioni: {recommendations}\n"
        f"Warnings: {warnings}\n\n"
        "Dammi in output:\n"
        "1. **Valutazione**: 1-2 frasi sulla solidità del team.\n"
        "2. **Minaccia chiave**: la threat più pericolosa attualmente e come gestirla.\n"
        "3. **Game plan**: lead consigliato, switch-in tipo, win condition.\n"
        "4. **Fix prioritari**: cosa cambiare se ci sono warning o gap di copertura.\n"
        "Usa markdown leggero con i 4 titoli in grassetto. Non parlare di Tera. Non inventare item/mosse."
    )


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()


def _fallback_advice(state: dict[str, Any]) -> str:
    team = state.get("team", [])
    recs = state.get("recommendations", [])
    warnings = state.get("warnings", [])
    synergy = state.get("synergy", [])
    threats = state.get("threatEntries") or []
    dangers = [t for t in threats if t.get("severity") == "danger"][:3]
    risky = [t for t in threats if t.get("severity") == "risky"][:3]

    lines = ["**Coach deterministico** (Gemini non configurato — vedi setupHint)\n"]
    if team:
        lines.append(f"- Team: {len(team)}/6 — {', '.join(m['species'] for m in team)}")
    else:
        lines.append("- Team vuoto. Aggiungi il primo Pokémon dal catalogo o clicca Auto build.")
    if dangers:
        names = ", ".join(f"{t['name']} ({t['usage']:.0f}%)" for t in dangers)
        lines.append(f"- Pericolose: {names}.")
    if risky:
        names = ", ".join(t["name"] for t in risky)
        lines.append(f"- Da tenere d'occhio: {names}.")
    if recs:
        best = recs[0]
        lines.append(f"- Prossimo pick suggerito: {best['name']} ({'; '.join(best.get('reasons', [])[:2])}).")
    if synergy:
        lines.append(f"- Synergy: {synergy[0]}")
    if warnings and warnings != ["none"]:
        lines.append(f"- Warning da risolvere: {warnings[0]}")
    return "\n".join(lines)
