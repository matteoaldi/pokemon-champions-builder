"""Gemini-backed narration of an EV Tuner result.

The numbers are produced by the deterministic calculators in this
package; Gemini only adds a short Italian explanation on top. If the
Gemini key is missing or the API fails, we return a template-based
fallback so the UI always has text to render.
"""
from __future__ import annotations

import json
from typing import Any

from pokemon_anti_meta_builder.ai_coach import AICoach
from pokemon_anti_meta_builder.ai_coach.coach import _build_prompt  # type: ignore[attr-defined]


def narrate(
    mode: str,
    payload: dict[str, Any],
    response: dict[str, Any],
    our_combatant: Any,
    target_combatant: Any,
) -> dict[str, Any]:
    """Produce {enabled, text, source} for the response payload."""
    template = _template(mode, payload, response, our_combatant, target_combatant)
    coach = AICoach()
    if not coach.api_key:
        return {"enabled": False, "text": template, "source": "template"}

    state = {
        "team": [_combatant_brief(our_combatant)],
        "threatEntries": [_combatant_brief(target_combatant, include_spread=True, spread=response.get("targetSpreadUsed"))],
        "digest": {"team_size": 1, "top_threats": [{"name": target_combatant.name}], "top_counters": []},
        "recommendations": [],
        "warnings": [],
        "synergy": [],
        "_ev_tuner": {
            "mode": mode,
            "result": response.get("result"),
            "remainingSuggestions": response.get("remainingSuggestions"),
            "remainingEvs": response.get("remainingEvs"),
            "assumptions": response.get("assumptions"),
            "request": {
                "move": payload.get("move"),
                "condition": payload.get("condition"),
                "threshold": payload.get("threshold"),
                "goal": payload.get("goal"),
                "field": payload.get("field"),
            },
        },
    }
    # Patch the prompt builder by appending an EV tuner section.
    base_prompt = _build_prompt(state)
    tuner_block = _tuner_prompt_block(state["_ev_tuner"])
    prompt = base_prompt + "\n\n" + tuner_block

    # Call AICoach.advise with a minimal state then override the prompt
    # via a thin shim: easier to just call the lower-level helper here.
    advice_payload = _direct_advise(coach, prompt)
    if advice_payload.get("enabled"):
        return {"enabled": True, "text": advice_payload.get("advice", "").strip() or template, "source": advice_payload.get("model", "gemini")}
    return {"enabled": False, "text": template, "source": "template", "error": advice_payload.get("error")}


# --- helpers ---------------------------------------------------------------

def _combatant_brief(c: Any, include_spread: bool = False, spread: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "name": c.name,
        "types": list(c.types),
        "nature": c.nature,
    }
    if include_spread and spread:
        out["spread"] = spread
    return out


def _tuner_prompt_block(payload: dict[str, Any]) -> str:
    return (
        "L'utente sta usando l'EV Tuner deterministico. NON ricalcolare i numeri: "
        "sono già stati prodotti da un motore matematico esatto, fidati di loro.\n"
        f"Modalità: {payload.get('mode')}\n"
        f"Richiesta utente: {json.dumps(payload.get('request'), ensure_ascii=False)}\n"
        f"Risultato matematico: {json.dumps(payload.get('result'), ensure_ascii=False)}\n"
        f"Assunzioni sul bersaglio: {json.dumps(payload.get('assumptions'), ensure_ascii=False)}\n"
        f"Suggerimenti residui: {payload.get('remainingSuggestions')}\n"
        f"EV residui disponibili: {payload.get('remainingEvs')}\n\n"
        "Scrivi in italiano (max 120 parole) un commento in markdown leggero con:\n"
        "1. **Spread consigliato**: ripeti nature + EV in scala Champions (0-32 per stat).\n"
        "2. **Cosa garantisce**: una frase sul vincolo soddisfatto.\n"
        "3. **Residui**: come spendere gli EV avanzati (riprendi i suggerimenti).\n"
        "Non parlare di Tera. Non inventare item o mosse."
    )


def _direct_advise(coach: AICoach, prompt: str) -> dict[str, Any]:
    """Mirror AICoach.advise but with an already-built prompt."""
    import json as _json
    from urllib.error import HTTPError, URLError

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 500},
    }
    data = _json.dumps(body).encode("utf-8")
    models_to_try: list[str] = []
    for name in (coach.model, "gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash"):
        if name and name not in models_to_try:
            models_to_try.append(name)
    last_error: str | None = None
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={coach.api_key}"
        try:
            response = coach._post_json(url, data, coach.context)  # type: ignore[attr-defined]
        except URLError as exc:
            last_error = str(exc)
            continue
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code in (429, 503):
                continue
            return {"enabled": False, "error": last_error}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue
        text = _extract(response)
        if text:
            return {"enabled": True, "advice": text, "model": model_name}
        last_error = "empty response"
    return {"enabled": False, "error": last_error or "no model succeeded"}


def _extract(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()


def _template(
    mode: str,
    payload: dict[str, Any],
    response: dict[str, Any],
    our_combatant: Any,
    target_combatant: Any,
) -> str:
    result = response.get("result") or {}
    suggestions = response.get("remainingSuggestions") or []
    feasible = result.get("feasible", True)
    nature = result.get("nature", "?")
    evs = result.get("evs", {}) or {}
    ev_str = " / ".join(f"{v} {k.upper()}" for k, v in evs.items() if v)
    ev_str = ev_str or "0 EV"

    if mode == "survive":
        if feasible:
            head = (
                f"**Spread consigliato**: {nature} {ev_str} (scala Champions).\n"
                f"**Cosa garantisce**: sopravvivi al {result.get('survivalPct', '?')}% dei roll "
                f"di {payload.get('move','?')} da {target_combatant.name} ({result.get('maxDamage','?')}/{result.get('hp','?')} HP max)."
            )
        else:
            head = (
                f"**Sopravvivenza non garantita**: con i tuoi base stat il vincolo non è raggiungibile. "
                f"{result.get('note','')}"
            )
    elif mode == "outspeed":
        if feasible:
            head = (
                f"**Spread consigliato**: {nature} {ev_str} (scala Champions).\n"
                f"**Cosa garantisce**: sei a {result.get('ourSpeed','?')} Spe contro {result.get('targetSpeed','?')} del bersaglio."
            )
        else:
            head = f"**Outspeed impossibile**: {result.get('note','')}"
    elif mode == "ohko":
        goal = (payload.get("goal") or "ohko").upper()
        if feasible:
            head = (
                f"**Spread consigliato**: {nature} {ev_str} (scala Champions).\n"
                f"**Cosa garantisce**: {goal} con {payload.get('move','?')} "
                f"({result.get('minDamage','?')}-{result.get('maxDamage','?')} su {result.get('hpTarget','?')} HP)."
            )
        else:
            head = f"**{goal} non garantito**: {result.get('note','')}"
    elif mode == "dualspeed":
        if result.get("universal"):
            covered = result.get("covered") or []
            too_fast = result.get("missedTooFastForTr") or []
            too_slow = result.get("missedTooSlowForTw") or []
            head = (
                f"**Spread universale consigliato**: {nature} {ev_str}, IV Spe {result.get('ivs', {}).get('spe', 31)}.\n"
                f"**Cosa garantisce**: dual-batti {len(covered)} mon meta (vinci sia sotto Tailwind che sotto Trick Room).\n"
                f"**No field**: sei più veloce di {len(too_slow)} mon (li batti sempre), più lento di {len(covered) + len(too_fast)} mon (gli sopravvieni in TR)."
            )
        elif feasible:
            head = (
                f"**Spread consigliato**: {nature} {ev_str}, IV Spe {result.get('ivs', {}).get('spe', 31)}.\n"
                f"**Cosa garantisce**: Spe = {result.get('ourSpeed','?')} cade in "
                f"({result.get('targetHalf','?')}, {result.get('targetSpeed','?')}). "
                f"Sotto Tailwind: {result.get('twSpeed','?')} > {result.get('targetSpeed','?')} (più veloce). "
                f"Sotto Trick Room: {result.get('ourSpeed','?')} < {result.get('targetSpeed','?')} (più lento → muove prima)."
            )
        else:
            head = f"**Impossibile**: {result.get('note','')}"
    else:
        head = ""

    tail = ""
    if suggestions:
        tail = "\n**Residui**:\n" + "\n".join(f"- {s}" for s in suggestions)
    return head + tail
