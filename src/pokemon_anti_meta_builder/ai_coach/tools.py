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
        self._mega_alias = self._build_mega_alias()
        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "find_pokemon_by_moves": self._find_pokemon_by_moves,
            "search_pokemon": self._search_pokemon,
            "get_learnset": self._get_learnset,
            "who_counters": self._who_counters,
            "countered_by": self._countered_by,
            "get_set": self._get_set,
            "min_speed_to_outspeed": self._min_speed_to_outspeed,
            "min_evs_to_survive": self._min_evs_to_survive,
            "min_evs_to_ohko": self._min_evs_to_ohko,
            "build_spread": self._build_spread,
        }

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def _build_mega_alias(self) -> dict[str, str]:
        """Map to_key(colloquial Mega name) -> canonical mega form name.

        Handles "Charizard X" / "Mega Charizard X" / "Charizard Mega X" ->
        "Charizard-Mega-X", and "Mega Garchomp" -> "Garchomp-Mega", WITHOUT ever
        shadowing a plain base-species name (so "Garchomp" stays "Garchomp")."""
        alias: dict[str, str] = {}
        for form in getattr(self.service, "mega_forms", []) or []:
            name = form.get("name") or ""
            base = form.get("base_species") or ""
            if not name or not base:
                continue
            # Mega names are "Base-Mega" or "Base-Mega-<Suffix>"; only treat the
            # 3rd segment as a variant letter when the form really has that shape,
            # so a hypothetical multi-dash name can't mis-pick a suffix token.
            parts = name.split("-")  # e.g. ["Charizard","Mega","X"] or ["Garchomp","Mega"]
            suffix = parts[2] if len(parts) == 3 and parts[1].lower() == "mega" else ""
            base_key = to_key(base)
            candidates = {
                to_key(name),                        # "charizardmegax" / "garchompmega"
                to_key(f"mega {base} {suffix}"),     # "megacharizardx" / "megagarchomp"
                to_key(f"{base} mega {suffix}"),     # "charizardmegax" / "garchompmega"
            }
            if suffix:
                candidates.add(to_key(f"{base} {suffix}"))  # "charizardx"
            for key in candidates:
                # never shadow the base species; first writer wins for any collision
                if key and key != base_key:
                    alias.setdefault(key, name)
        return alias

    def resolve_species(self, name: str) -> str:
        """Resolve a colloquial Mega name to its canonical form; pass through
        anything already canonical / unknown / non-Mega unchanged."""
        if not name:
            return name
        return self._mega_alias.get(to_key(name), name)

    def declarations(self) -> list[dict[str, Any]]:
        S = {"type": "string"}
        return [
            {"name": "find_pokemon_by_moves",
             "description": "Pokémon che imparano le mosse date. require_all=true -> intersezione (tutte), false -> unione.",
             "parameters": {"type": "object", "properties": {
                 "moves": {"type": "array", "items": S}, "require_all": {"type": "boolean"}}, "required": ["moves"]}},
            {"name": "search_pokemon",
             "description": "Cerca Pokémon del meta per tipo, ruolo e usage minimo.",
             "parameters": {"type": "object", "properties": {
                 "type": S, "role": S, "min_usage": {"type": "number"}}}},
            {"name": "get_learnset",
             "description": "Tutte le mosse legali che un Pokémon impara.",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "who_counters",
             "description": "Chi counter-a (batte) il Pokémon dato, con motivi (mosse/tipi/speed).",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "countered_by",
             "description": "Quali Pokémon il soggetto batte (inverso di who_counters).",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "get_set",
             "description": "Set reale (item/ability/mosse/EV/nature) e base stats di un Pokémon.",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "min_speed_to_outspeed",
             "description": "EV Speed minimi per superare un bersaglio. target_max_speed=true assume il bersaglio a max Speed. our_boost/target_boost = stage di Speed (+1, +2...). condition: none/tailwind_me/tailwind_opp/scarf_me/scarf_opp/paralysis_opp. nature = blocca una natura specifica (es. Adamant) invece di scegliere la più veloce.",
             "parameters": {"type": "object", "properties": {
                 "species": S, "target": S, "target_max_speed": {"type": "boolean"},
                 "our_boost": {"type": "number"}, "target_boost": {"type": "number"}, "condition": S,
                 "nature": S},
                 "required": ["species", "target"]}},
            {"name": "min_evs_to_survive",
             "description": "EV difensivi minimi per sopravvivere a una mossa di un attaccante. threshold: guaranteed/high/median. nature blocca una natura; defense_boost = stage Def/SpD (+1 Parananzia/Amnesia); reflect/light_screen/aurora_veil/weather impostano il campo.",
             "parameters": {"type": "object", "properties": {
                 "species": S, "attacker": S, "move": S, "threshold": S,
                 "nature": S, "defense_boost": {"type": "number"},
                 "light_screen": {"type": "boolean"}, "reflect": {"type": "boolean"},
                 "aurora_veil": {"type": "boolean"}, "weather": S},
                 "required": ["species", "attacker", "move"]}},
            {"name": "min_evs_to_ohko",
             "description": "EV offensivi minimi per OHKO/2HKO un bersaglio con una mossa. goal: ohko/2hko. attack_boost = stage Atk/SpA (+2 Danza Spada, +1 Nitrocarica...).",
             "parameters": {"type": "object", "properties": {
                 "species": S, "target": S, "move": S, "goal": S,
                 "attack_boost": {"type": "number"}}, "required": ["species", "target", "move"]}},
            {"name": "build_spread",
             "description": "Genera uno spread EV COMPLETO (Speed + offensiva + bulk) per un Pokémon data una natura. role: auto/offensive/defensive. fixed_evs = EV già decisi da tenere (es. {spe:16}); il bulk usa il budget residuo. Ritorna lo spread completo applicabile.",
             "parameters": {"type": "object", "properties": {
                 "species": S, "nature": S, "role": S,
                 "fixed_evs": {"type": "object"}, "meta_limit": {"type": "number"}},
                 "required": ["species", "nature"]}},
        ]

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
        species = self.resolve_species((args.get("species") or "").strip())
        if not species:
            return {"ok": False, "error": "missing species"}
        moves = self.service.learnset_for(species)
        return {"ok": True, "species": species, "moves": moves}

    def _who_counters(self, args: dict[str, Any]) -> dict[str, Any]:
        species = self.resolve_species((args.get("species") or "").strip())
        if not species:
            return {"ok": False, "error": "missing species"}
        data = self.service.counter_lookup(species)
        if data.get("notFound"):
            return {"ok": False, "error": f"unknown Pokemon: {species}"}
        return {"ok": True, "name": data["name"], "types": data["types"],
                "source": data["source"], "counters": data["counters"]}

    def _countered_by(self, args: dict[str, Any]) -> dict[str, Any]:
        species = self.resolve_species((args.get("species") or "").strip())
        if not species:
            return {"ok": False, "error": "missing species"}
        data = self.service.countered_by(species)
        result: dict[str, Any] = {"ok": True}
        result.update(data)
        return result

    def _get_set(self, args: dict[str, Any]) -> dict[str, Any]:
        species = self.resolve_species((args.get("species") or "").strip())
        if not species:
            return {"ok": False, "error": "missing species"}
        payload = self.service.combatant_payload(species)
        if payload.get("error"):
            return {"ok": False, "error": payload["error"]}
        return {"ok": True, "set": payload}

    def _min_speed_to_outspeed(self, args: dict[str, Any]) -> dict[str, Any]:
        species = self.resolve_species((args.get("species") or "").strip())
        target = self.resolve_species((args.get("target") or "").strip())
        if not species or not target:
            return {"ok": False, "error": "need species and target"}
        nature = (args.get("nature") or "").strip()
        payload = {
            "mode": "outspeed",
            "ourSpecies": species,
            "targetSpecies": target,
            "condition": args.get("condition") or "none",
            "ourBoost": int(args.get("our_boost") or 0),
            "targetBoost": int(args.get("target_boost") or 0),
        }
        if nature:
            payload["ourNatureLock"] = nature
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

    def _min_evs_to_survive(self, args: dict[str, Any]) -> dict[str, Any]:
        species = self.resolve_species((args.get("species") or "").strip())
        attacker = self.resolve_species((args.get("attacker") or "").strip())
        move = (args.get("move") or "").strip()
        if not species or not attacker or not move:
            return {"ok": False, "error": "need species, attacker and move"}
        nature = (args.get("nature") or "").strip()
        field = {
            "weather": (args.get("weather") or "").strip(),
            "lightScreen": bool(args.get("light_screen")),
            "reflect": bool(args.get("reflect")),
            "auroraVeil": bool(args.get("aurora_veil")),
        }
        payload = {
            "mode": "survive", "ourSpecies": species, "targetSpecies": attacker,
            "move": move, "threshold": args.get("threshold") or "guaranteed",
            "defenseBoost": int(args.get("defense_boost") or 0),
            "field": field,
        }
        if nature:
            payload["ourNatureLock"] = nature
        out = self.ev_tuner.optimize(payload)
        if not out.get("ok"):
            return out
        proposal = {"species": species, "evs": out["result"].get("evs", {}),
                    "note": f"regge {move} di {attacker}"} if out["result"].get("feasible") else None
        return {"ok": True, "result": out["result"], "assumptions": out.get("assumptions"), "proposal": proposal}

    def _min_evs_to_ohko(self, args: dict[str, Any]) -> dict[str, Any]:
        species = self.resolve_species((args.get("species") or "").strip())
        target = self.resolve_species((args.get("target") or "").strip())
        move = (args.get("move") or "").strip()
        if not species or not target or not move:
            return {"ok": False, "error": "need species, target and move"}
        out = self.ev_tuner.optimize({
            "mode": "ohko", "ourSpecies": species, "targetSpecies": target,
            "move": move, "goal": args.get("goal") or "ohko",
            "attackBoost": int(args.get("attack_boost") or 0),
        })
        if not out.get("ok"):
            return out
        proposal = {"species": species, "evs": out["result"].get("evs", {}),
                    "note": f"{args.get('goal') or 'ohko'} {target} con {move}"} if out["result"].get("feasible") else None
        return {"ok": True, "result": out["result"], "assumptions": out.get("assumptions"), "proposal": proposal}

    def _build_spread(self, args: dict[str, Any]) -> dict[str, Any]:
        """Generate a COMPLETE EV spread (Spe + offense + bulk) for a mon, given
        a nature and optional already-spent EVs (fixed_evs). Wraps the Spread
        Maker engine; returns the full spread plus an applicable proposal."""
        species = self.resolve_species((args.get("species") or "").strip())
        nature = (args.get("nature") or "").strip()
        if not species or not nature:
            return {"ok": False, "error": "servono species e natura (es. Modest)"}
        payload: dict[str, Any] = {
            "ourSpecies": species,
            "nature": nature,
            "role": args.get("role") or "auto",
        }
        fixed = args.get("fixed_evs")
        if isinstance(fixed, dict) and fixed:
            payload["fixedEvs"] = {k: int(v) for k, v in fixed.items() if v is not None}
        if args.get("meta_limit"):
            payload["metaLimit"] = int(args["meta_limit"])
        out = self.ev_tuner.spread_maker(payload)
        if not out.get("ok"):
            return out
        res = out["result"]
        proposal = {
            "species": species,
            "nature": res.get("nature", nature),
            "evs": res.get("evs", {}),
            "note": f"spread {res.get('role', 'auto')} completo ({res.get('totalUsed', 0)} EV)",
        }
        return {"ok": True, "result": res, "notes": res.get("notes", []), "proposal": proposal}
