"""Deterministic tools the conversational assistant can call.

Each tool is a thin wrapper over RecommendationService / EVTunerService that
returns compact JSON. Numbers come from the engine — the LLM only orchestrates.
Every tool returns a dict with at least {"ok": bool}; on failure {"ok": False,
"error": str}. `to_key` keeps name matching tolerant.
"""
from __future__ import annotations

from typing import Any, Callable

from pokemon_anti_meta_builder.meta_parser.normalizer import to_key


class ToolRegistry:
    def __init__(self, service, ev_tuner) -> None:
        self.service = service
        self.ev_tuner = ev_tuner
        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "find_pokemon_by_moves": self._find_pokemon_by_moves,
            "search_pokemon": self._search_pokemon,
            "get_learnset": self._get_learnset,
            "who_counters": self._who_counters,
            "countered_by": self._countered_by,
            "get_set": self._get_set,
            "min_speed_to_outspeed": self._min_speed_to_outspeed,
        }

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = self._tools.get(name)
        if fn is None:
            return {"ok": False, "error": f"unknown tool '{name}'"}
        try:
            return fn(args or {})
        except Exception as exc:  # tools must never crash the agent loop
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _find_pokemon_by_moves(self, args: dict[str, Any]) -> dict[str, Any]:
        moves = [m for m in (args.get("moves") or []) if m]
        if not moves:
            return {"ok": False, "error": "missing moves"}
        require_all = args.get("require_all", True)
        sets = [set(map(to_key, self.service.species_with_move(m))) for m in moves]
        keys = set.intersection(*sets) if require_all else set.union(*sets)
        ordered: list[str] = []
        seen: set[str] = set()
        for m in moves:
            for name in self.service.species_with_move(m):
                k = to_key(name)
                if k in keys and k not in seen:
                    seen.add(k)
                    ordered.append(name)
        return {"ok": True, "moves": moves, "require_all": bool(require_all), "species": ordered[:30]}

    def _search_pokemon(self, args: dict[str, Any]) -> dict[str, Any]:
        want_type = (args.get("type") or "").lower().strip()
        want_role = (args.get("role") or "").lower().strip()
        min_usage = float(args.get("min_usage") or 0.0)
        out = []
        for p in self.service.catalog()["pokemon"]:
            if want_type and want_type not in [t.lower() for t in p["types"]]:
                continue
            if want_role and want_role not in [r.lower() for r in (p.get("roles") or [])]:
                continue
            if (p.get("usage") or 0.0) < min_usage:
                continue
            out.append({"name": p["name"], "types": p["types"], "usage": p.get("usage"), "roles": p.get("roles")})
        out.sort(key=lambda x: -(x["usage"] or 0.0))
        return {"ok": True, "count": len(out), "pokemon": out[:40]}

    def _get_learnset(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        moves = self.service.learnset_for(species)
        return {"ok": True, "species": species, "moves": moves}

    def _who_counters(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        data = self.service.counter_lookup(species)
        if data.get("notFound"):
            return {"ok": False, "error": f"unknown Pokemon: {species}"}
        return {"ok": True, "name": data["name"], "types": data["types"],
                "source": data["source"], "counters": data["counters"]}

    def _countered_by(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        data = self.service.countered_by(species)
        result: dict[str, Any] = {"ok": True}
        result.update(data)
        return result

    def _get_set(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        payload = self.service.combatant_payload(species)
        if payload.get("error"):
            return {"ok": False, "error": payload["error"]}
        return {"ok": True, "set": payload}

    def _min_speed_to_outspeed(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        target = (args.get("target") or "").strip()
        if not species or not target:
            return {"ok": False, "error": "need species and target"}
        payload = {
            "mode": "outspeed",
            "ourSpecies": species,
            "targetSpecies": target,
            "condition": args.get("condition") or "none",
            "ourBoost": int(args.get("our_boost") or 0),
            "targetBoost": int(args.get("target_boost") or 0),
        }
        if args.get("target_max_speed"):
            payload["targetSpreadManual"] = {"nature": "Jolly", "evs": {"spe": 32}}
        out = self.ev_tuner.optimize(payload)
        if not out.get("ok"):
            return out
        result = out["result"]
        proposal = None
        if result.get("feasible"):
            proposal = {
                "species": species,
                "nature": result.get("nature"),
                "evs": result.get("evs", {}),
                "note": f"{result['evs'].get('spe', 0)} Spe EV per superare {target}",
            }
        return {"ok": True, "result": result, "assumptions": out.get("assumptions"), "proposal": proposal}
