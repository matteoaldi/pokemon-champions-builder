"""Conversational agent: loops Gemini function-calls against the ToolRegistry.

The LLM only orchestrates; every number comes from a tool. `gemini_caller` is
injectable so tests run without network.
"""
from __future__ import annotations

from typing import Any, Callable

from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry

GeminiCaller = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]

SYSTEM_PROMPT = (
    "Sei un assistente per Pokémon Champions, Regulation M-A. Rispondi in italiano, "
    "conciso. Champions NON ha Tera; supporta Mega Evoluzioni (una per team). "
    "Usa SEMPRE i tool per numeri, counter, mosse, EV: non inventare valori. "
    "Traduci i nomi italiani di mosse/Pokémon in inglese canonico prima di chiamare i tool. "
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
