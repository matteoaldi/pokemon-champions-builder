"""Conversational agent: loops Gemini function-calls against the ToolRegistry.

The LLM only orchestrates; every number comes from a tool. `gemini_caller` is
injectable so tests run without network.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Callable

from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry

GeminiCaller = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]

SYSTEM_PROMPT = (
    "Sei un assistente per Pokémon Champions, Regulation M-A. Rispondi in italiano, "
    "conciso. Champions NON ha Tera; supporta Mega Evoluzioni (una per team). "
    "Usa SEMPRE i tool per numeri, counter, mosse, EV: non inventare valori. "
    "Traduci i nomi italiani di mosse/Pokémon in inglese canonico prima di chiamare i tool; "
    "traduci anche i nomi delle nature dall'italiano (es. Deciso=Adamant, Allegro=Jolly, Timido=Timid, Modesto=Modest, Calmo=Calm, Audace=Lonely, Ardito=Brave) prima di passarle ai tool. "
    "Se un tool torna ok=false, spiega l'errore e chiedi chiarimenti."
)


class GeminiAgent:
    def __init__(self, registry: ToolRegistry, gemini_caller: GeminiCaller, max_turns: int = 6) -> None:
        self.registry = registry
        self.gemini = gemini_caller
        self.max_turns = max_turns

    def run(self, messages: list[dict[str, Any]], team_state: dict[str, Any] | None = None) -> dict[str, Any]:
        # `contents` uses a NEUTRAL internal format (role + flat text/functionCall/
        # functionResponse). The injected gemini_caller is responsible for translating
        # it into the provider wire format (e.g. Gemini system_instruction + parts).
        # Keep this decoupled from any specific provider schema.
        contents: list[dict[str, Any]] = [{"role": "system", "text": SYSTEM_PROMPT}]
        if team_state:
            contents.append({"role": "system", "text": f"Team corrente: {team_state}"})
        contents.extend(messages)

        tool_trace: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []

        for _ in range(self.max_turns):
            resp = self.gemini(contents, self.registry.declarations())
            call = resp.get("functionCall")
            if not call:
                return {"reply": resp.get("text", ""), "proposals": proposals, "toolTrace": tool_trace}
            name, args = call.get("name", ""), call.get("args", {})
            result = self.registry.call(name, args)
            tool_trace.append({"name": name, "args": args, "ok": result.get("ok")})
            if isinstance(result, dict) and result.get("proposal"):
                proposals.append(result["proposal"])
            contents.append({"role": "model", "functionCall": call})
            contents.append({"role": "tool", "functionResponse": {"name": name, "response": result}})

        final = self.gemini(contents + [{"role": "system", "text": "Concludi senza altri tool."}], [])
        return {"reply": final.get("text", "Troppi passaggi, riprova più specifico."),
                "proposals": proposals, "toolTrace": tool_trace}


# ---------------------------------------------------------------------------
# Real Gemini REST caller (injectable into GeminiAgent)
# ---------------------------------------------------------------------------

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash")


def make_real_gemini_caller(api_key: str | None = None, model: str | None = None) -> GeminiCaller:
    """Build a gemini_caller that translates the agent's neutral `contents` into
    Gemini REST wire format. System entries -> system_instruction; functionCall /
    functionResponse -> proper parts; everything else -> text parts. Returns
    {"functionCall": {...}} or {"text": str}."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    primary = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    # macOS / Python.org builds often lack system root certs; use certifi's
    # bundle when available so HTTPS verification works without disabling it.
    try:
        import certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ssl_context = ssl.create_default_context()

    def _to_gemini_contents(contents):
        out = []
        sys_txt = []
        for c in contents:
            if c.get("role") == "system":
                sys_txt.append(c.get("text", "")); continue
            if "functionCall" in c:
                out.append({"role": "model", "parts": [{"functionCall": {
                    "name": c["functionCall"]["name"], "args": c["functionCall"].get("args", {})}}]})
            elif "functionResponse" in c:
                out.append({"role": "user", "parts": [{"functionResponse": {
                    "name": c["functionResponse"]["name"], "response": c["functionResponse"]["response"]}}]})
            else:
                role = "user" if c.get("role") == "user" else "model"
                out.append({"role": role, "parts": [{"text": c.get("text", "")}]})
        return out, "\n".join(t for t in sys_txt if t)

    def caller(contents, tools):
        if not key:
            return {"text": "Errore: GEMINI_API_KEY non configurata."}
        gem_contents, sys_txt = _to_gemini_contents(contents)
        body = {"contents": gem_contents}
        if sys_txt:
            body["systemInstruction"] = {"parts": [{"text": sys_txt}]}
        if tools:
            body["tools"] = [{"function_declarations": tools}]
        data = json.dumps(body).encode("utf-8")
        last_error = ""
        for model_name in dict.fromkeys((primary, *FALLBACK_MODELS)):
            url = GEMINI_ENDPOINT.format(model=model_name, key=key)
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30, context=ssl_context) as r:
                    payload = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_error = str(e.code)
                if e.code in (429, 503):
                    continue
                return {"text": f"Errore Gemini {e.code}."}
            except Exception as e:  # network/timeout
                return {"text": f"Errore rete: {e}"}
            parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            for p in parts:
                if "functionCall" in p:
                    fc = p["functionCall"]
                    return {"functionCall": {"name": fc.get("name", ""), "args": dict(fc.get("args", {}))}}
            text = "\n".join(p.get("text", "") for p in parts if "text" in p).strip()
            return {"text": text}
        return {"text": f"Gemini non disponibile ({last_error})."}

    return caller
