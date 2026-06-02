"""Orchestrator for the EV Tuner.

Bridges the web layer with the four pure calculators in this package.
Builds `Combatant` instances for both sides (using the existing
`RecommendationService.combatant_payload`), applies the user-chosen
target spread (top Pokékipe spread or manual override), dispatches on
mode, and assembles the JSON response (spread + remaining suggestions +
narrator text).
"""
from __future__ import annotations

from typing import Any

from pokemon_anti_meta_builder.damage_calc.calculator import Combatant, Field, MOVE_LIBRARY
from pokemon_anti_meta_builder.ev_optimizer.meta import (
    default_target_evs,
    parse_spread_option,
    top_n_spreads,
)
from pokemon_anti_meta_builder.ev_optimizer.narrator import narrate
from pokemon_anti_meta_builder.ev_optimizer.ohko import find_min_offensive_evs
from pokemon_anti_meta_builder.ev_optimizer.outspeed import find_min_evs_to_outspeed
from pokemon_anti_meta_builder.ev_optimizer.suggest_remaining import suggest_remaining
from pokemon_anti_meta_builder.ev_optimizer.survive import (
    EV_MAX_PER_STAT,
    EV_MAX_TOTAL,
    find_min_evs_to_survive,
)
from pokemon_anti_meta_builder.ev_optimizer.dual_speed import find_dual_speed, find_universal_dual_speed
from pokemon_anti_meta_builder.ev_optimizer.spread_maker import make_spread
from pokemon_anti_meta_builder.meta_parser.normalizer import to_key
from pokemon_anti_meta_builder.models import EVSpread


VALID_MODES = ("survive", "outspeed", "ohko", "dualspeed")


class EVTunerService:
    """High-level entrypoint used by the web server."""

    def __init__(self, recommendation_service: Any):
        self.svc = recommendation_service

    # --- read-only helpers --------------------------------------------------

    def spreads_for(self, species: str, n: int = 3) -> dict[str, Any]:
        mon = self.svc.meta_by_key.get(to_key(species))
        if mon is None:
            return {"ok": False, "species": species, "spreads": [], "error": "off-meta"}
        return {"ok": True, "species": mon.name, "spreads": top_n_spreads(mon, n=n)}

    # --- main dispatch ------------------------------------------------------

    def optimize(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = (payload.get("mode") or "").lower()
        if mode not in VALID_MODES:
            return {"ok": False, "error": f"unknown mode '{mode}'"}

        try:
            our_species = (payload.get("ourSpecies") or "").strip()
            target_species = (payload.get("targetSpecies") or "").strip()
            is_universal_mode = mode == "dualspeed" and bool(payload.get("universal"))
            if not our_species:
                return {"ok": False, "error": "missing ourSpecies"}
            if not is_universal_mode and not target_species:
                return {"ok": False, "error": "missing targetSpecies"}

            our_combatant = self._build_combatant(our_species, role_hint=payload.get("ourRoleHint"))
            if is_universal_mode:
                # No single target; build a placeholder so downstream code that
                # references target_combatant (narrator state, fallbacks) doesn't NPE.
                target_combatant = our_combatant
                target_spread = {"source": "universal", "nature": None, "evs": {}, "usage": None}
            else:
                target_spread = self._resolve_target_spread(target_species, payload)
                target_combatant = self._apply_spread(
                    self._build_combatant(target_species),
                    target_spread,
                )
            field = _field_from(payload.get("field") or {})

            if mode == "survive":
                result = find_min_evs_to_survive(
                    defender=our_combatant,
                    attacker=target_combatant,
                    move=_require_move(payload),
                    field=field,
                    threshold=(payload.get("threshold") or "guaranteed"),
                )
                used = {"hp": result.hp_ev, "def": result.def_ev, "spd": result.spd_ev}
                role_hint = _detect_role(our_combatant)
                suggestions = suggest_remaining(used, role_hint, mode)
                response = {
                    "ok": True,
                    "mode": mode,
                    "result": result.as_dict(),
                    "remainingSuggestions": suggestions,
                    "remainingEvs": max(0, EV_MAX_TOTAL - sum(used.values())),
                    "targetSpreadUsed": target_spread,
                    "assumptions": _assumptions_payload(target_combatant, target_spread),
                }

            elif mode == "outspeed":
                result = find_min_evs_to_outspeed(
                    our_mon=our_combatant,
                    target_mon=target_combatant,
                    condition=(payload.get("condition") or "none"),
                    our_boost=int(payload.get("ourBoost") or 0),
                    target_boost=int(payload.get("targetBoost") or 0),
                )
                used = {"spe": result.spe_ev}
                role_hint = _detect_role(our_combatant)
                suggestions = suggest_remaining(used, role_hint, mode)
                response = {
                    "ok": True,
                    "mode": mode,
                    "result": result.as_dict(),
                    "remainingSuggestions": suggestions,
                    "remainingEvs": max(0, EV_MAX_TOTAL - sum(used.values())),
                    "targetSpreadUsed": target_spread,
                    "assumptions": _assumptions_payload(target_combatant, target_spread),
                }

            elif mode == "ohko":
                result = find_min_offensive_evs(
                    our_mon=our_combatant,
                    target_mon=target_combatant,
                    move=_require_move(payload),
                    field=field,
                    goal=(payload.get("goal") or "ohko"),
                )
                used = {"atk": result.atk_ev, "spa": result.spa_ev}
                role_hint = _detect_role(our_combatant)
                suggestions = suggest_remaining(used, role_hint, mode)
                response = {
                    "ok": True,
                    "mode": mode,
                    "result": result.as_dict(),
                    "remainingSuggestions": suggestions,
                    "remainingEvs": max(0, EV_MAX_TOTAL - sum(used.values())),
                    "targetSpreadUsed": target_spread,
                    "assumptions": _assumptions_payload(target_combatant, target_spread),
                }

            else:  # dualspeed
                role_hint = _detect_role(our_combatant)
                nature_lock = payload.get("ourNatureLock") or None
                if payload.get("universal"):
                    # Find a spread that dual-beats the most targets in the chosen pool.
                    pool_mode = (payload.get("pool") or "all").lower()
                    meta_targets = self._top_meta_speeds(
                        limit=int(payload.get("metaLimit") or 25),
                        pool_mode=pool_mode,
                        subject_species=our_species,
                    )
                    universal = find_universal_dual_speed(
                        our_mon=our_combatant,
                        meta_targets=meta_targets,
                        nature_lock=nature_lock,
                    )
                    # Build a result dict shaped like the single-target one
                    # so the frontend can render with minimal special-casing.
                    result_dict = {
                        "feasible": universal["feasible"],
                        "nature": universal["nature"],
                        "evs": {"spe": universal["spe_ev"]},
                        "ivs": {"spe": universal["spe_iv"]},
                        "ourSpeed": universal["our_speed"],
                        "targetSpeed": None,
                        "twSpeed": universal["our_speed"] * 2,
                        "targetHalf": None,
                        "note": "" if universal["feasible"] else "Nessun mon meta dual-battibile con questo Spe base.",
                        "universal": True,
                        "covered": universal["covered"],
                        "missedTooFastForTr": universal["missed_too_fast_for_tr"],
                        "missedTooSlowForTw": universal["missed_too_slow_for_tw"],
                    }
                    used = {"spe": universal["spe_ev"]}
                    suggestions = suggest_remaining(used, role_hint, mode)
                    response = {
                        "ok": True,
                        "mode": mode,
                        "result": result_dict,
                        "remainingSuggestions": suggestions,
                        "remainingEvs": max(0, EV_MAX_TOTAL - sum(used.values())),
                        "targetSpreadUsed": None,
                        "assumptions": {
                            "metaTargetsCount": len(meta_targets),
                            "poolMode": pool_mode,
                            "evScaleNote": f"Scala Champions: max {EV_MAX_PER_STAT}/stat, totale {EV_MAX_TOTAL}",
                        },
                    }
                    response["narration"] = narrate(
                        mode=mode, payload=payload, response=response,
                        our_combatant=our_combatant, target_combatant=our_combatant,
                    )
                    response["evScaleMax"] = {"perStat": EV_MAX_PER_STAT, "total": EV_MAX_TOTAL}
                    return response
                result = find_dual_speed(
                    our_mon=our_combatant,
                    target_mon=target_combatant,
                    nature_lock=nature_lock,
                )
                used = {"spe": result.spe_ev}
                suggestions = suggest_remaining(used, role_hint, mode)
                response = {
                    "ok": True,
                    "mode": mode,
                    "result": result.as_dict(),
                    "remainingSuggestions": suggestions,
                    "remainingEvs": max(0, EV_MAX_TOTAL - sum(used.values())),
                    "targetSpreadUsed": target_spread,
                    "assumptions": _assumptions_payload(target_combatant, target_spread),
                }

            # Gemini-generated narration (optional, with template fallback)
            response["narration"] = narrate(
                mode=mode,
                payload=payload,
                response=response,
                our_combatant=our_combatant,
                target_combatant=target_combatant,
            )
            response["evScaleMax"] = {"perStat": EV_MAX_PER_STAT, "total": EV_MAX_TOTAL}
            return response

        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def spread_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Live report for an arbitrary spread the user is editing.

        Payload: {ourSpecies, nature, evs:{hp,atk,def,spa,spd,spe}, weather}
        Returns: {damage:[...], bulk:[...]} computed without changing the EVs.
        """
        from pokemon_anti_meta_builder.ev_optimizer.spread_maker import (
            _damage_report, _best_move_against, _clone_with, _field,
        )
        from pokemon_anti_meta_builder.damage_calc.calculator import DamageCalculator, MOVE_LIBRARY
        try:
            species = (payload.get("ourSpecies") or "").strip()
            nature = (payload.get("nature") or "").strip()
            if not species or not nature:
                return {"ok": False, "error": "missing ourSpecies or nature"}
            evs_in = {k: int(v or 0) for k, v in (payload.get("evs") or {}).items()}
            weather = (payload.get("weather") or "").lower()
            meta_limit = int(payload.get("metaLimit") or 40)

            ours_override: dict[str, Any] = {}
            if payload.get("ourItem"):
                ours_override["item"] = str(payload["ourItem"]).strip()
            if payload.get("ourAbility"):
                ours_override["ability"] = str(payload["ourAbility"]).strip()
            our_combatant = self._build_combatant(species, override=ours_override or None)
            # Apply optional boosts (Swords Dance, Calm Mind, Iron Defense, ...)
            boosts_in = payload.get("boosts") or {}
            if boosts_in:
                merged = dict(our_combatant.boosts)
                for k, v in boosts_in.items():
                    merged[k] = max(-6, min(6, int(v or 0)))
                our_combatant = Combatant(
                    name=our_combatant.name, level=our_combatant.level,
                    types=list(our_combatant.types),
                    base_stats=dict(our_combatant.base_stats),
                    evs=dict(our_combatant.evs), ivs=dict(our_combatant.ivs),
                    nature=our_combatant.nature, boosts=merged,
                    tera_type=our_combatant.tera_type,
                    is_burned=our_combatant.is_burned,
                    ability=our_combatant.ability,
                )
            pool_mode = (payload.get("pool") or "meta_top").lower()
            target_filter = (payload.get("targetSpecies") or "").strip()
            meta_pairs = self._resolve_pool_targets(
                pool_mode=pool_mode, subject_species=species, limit=meta_limit,
                target_filter=target_filter,
            )
            our_set_moves = self._set_moves_for(species)
            counterables_data = self.svc.countered_by(species, limit=40)
            counterables = {v["name"] for v in counterables_data.get("victims", [])}

            # Detect offensive stat by counting the set's physical vs special
            # damage moves — consistent with spread_maker.pick_offensive_stat.
            from pokemon_anti_meta_builder.damage_calc.calculator import MOVE_LIBRARY as _ML
            phys_n = sum(1 for m in our_set_moves if _ML.get(m, {}).get("category") == "physical")
            spec_n = sum(1 for m in our_set_moves if _ML.get(m, {}).get("category") == "special")
            if spec_n > phys_n:
                off_stat = "spa"
            elif phys_n > spec_n:
                off_stat = "atk"
            else:
                base = our_combatant.base_stats
                off_stat = "atk" if base.get("atk", 0) >= base.get("spa", 0) else "spa"
            ignore_ab_weather = bool(payload.get("ignoreAbilityWeather"))
            damage = _damage_report(
                our_combatant, nature, evs_in, meta_pairs, our_set_moves,
                counterables, off_stat, weather, ignore_ab_weather,
            )
            # Enrich damage entries with types + target speed for richer UI.
            target_by_name = {t.name: t for t, _ in meta_pairs}
            for d in damage:
                t = target_by_name.get(d["name"])
                if t:
                    d["types"] = list(t.types)
                    d["targetSpeed"] = t.stat("spe")
            # Bulk report on the FULL meta pool (not just top 6), so the user
            # can scroll mon-by-mon.
            calc = DamageCalculator()
            defender = _clone_with(our_combatant, evs=evs_in, nature=nature)
            bulk: list[dict[str, Any]] = []
            for atk, threat_moves in meta_pairs:
                worst = _best_move_against(atk, defender, threat_moves, calc, weather, ignore_ab_weather)
                if worst is None:
                    continue
                move_name, r = worst
                hp = defender.stat("hp") or 1
                bulk.append({
                    "threat": atk.name,
                    "types": list(atk.types),
                    "move": move_name,
                    "minPct": round(min(r.rolls) / hp * 100, 1),
                    "maxPct": round(max(r.rolls) / hp * 100, 1),
                    "survives": max(r.rolls) < hp,
                    "koChance": r.ko_chance,
                })
            # Speed report — OVERLAPPING categories (a single mon can belong
            # to multiple). Sotto Trick Room ogni mon più veloce di me, mi
            # diventa "battibile" perché io sono più lento → muovo prima.
            # Per questo "battibili in TR" include sia chi prendo con TW sia
            # chi è troppo veloce anche per TW.
            #
            #   normal:  my_spe > target_spe        — vinco senza field
            #   tw:      my_spe < target_spe AND 2*my_spe > target_spe
            #            — TW basta per superarli
            #   tr:      my_spe < target_spe        — più veloci di me senza
            #            condizioni → in TR muovo prima (sempre)
            #   tie:     my_spe == target_spe       — speed tie 50/50
            my_spe = defender.stat("spe")
            speed_outsped: list[dict[str, Any]] = []
            speed_outsped_in_tw: list[dict[str, Any]] = []
            speed_outsped_in_tr: list[dict[str, Any]] = []
            speed_tie: list[dict[str, Any]] = []
            for t, _ in meta_pairs:
                t_spe = t.stat("spe")
                entry = {"name": t.name, "spe": t_spe}
                if my_spe == t_spe:
                    speed_tie.append(entry)
                elif my_spe > t_spe:
                    speed_outsped.append(entry)
                else:
                    # my_spe < target_spe → I lose in normal play, win in TR
                    speed_outsped_in_tr.append(entry)
                    if my_spe * 2 > t_spe:
                        # TW also catches them
                        speed_outsped_in_tw.append(entry)
            for lst in (speed_outsped, speed_outsped_in_tw, speed_outsped_in_tr, speed_tie):
                lst.sort(key=lambda e: -e["spe"])

            total_used = sum(evs_in.values())
            return {
                "ok": True,
                "species": species,
                "damage": damage,
                "bulk": bulk,
                "speed": {
                    "ourSpeed": my_spe,
                    "outsped": speed_outsped,
                    "outspedOnlyTw": speed_outsped_in_tw,
                    "outspedOnlyTr": speed_outsped_in_tr,
                    "speedTie": speed_tie,
                },
                "totalUsed": total_used,
                "remaining": max(0, EV_MAX_TOTAL - total_used),
                "overBudget": total_used > EV_MAX_TOTAL,
                "counterablesCount": len(counterables),
                "counterables": sorted(counterables),
                "ourSetMoves": our_set_moves,
                "offensiveStat": off_stat,
                "damageTargets": [t.name for t, _ in meta_pairs],
                "bulkTargets": [t.name for t, _ in meta_pairs],
                "metaTargetsCount": len(meta_pairs),
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def spread_maker(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Build a complete EV spread after Spe is already chosen.

        Payload:
          - ourSpecies (required)
          - nature (required)
          - fixedEvs: {spe: N, ...} EVs already locked in
          - role: 'auto' | 'offensive' | 'defensive'
          - metaLimit: top-N meta to use as targets (default 40)
        """
        try:
            species = (payload.get("ourSpecies") or "").strip()
            nature = (payload.get("nature") or "").strip()
            if not species or not nature:
                return {"ok": False, "error": "missing ourSpecies or nature"}
            fixed = {k: int(v) for k, v in (payload.get("fixedEvs") or {}).items() if v is not None}
            role = (payload.get("role") or "auto").lower()
            role_override = role if role in ("offensive", "defensive") else None
            meta_limit = int(payload.get("metaLimit") or 40)

            ours_override: dict[str, Any] = {}
            if payload.get("ourItem"):
                ours_override["item"] = str(payload["ourItem"]).strip()
            if payload.get("ourAbility"):
                ours_override["ability"] = str(payload["ourAbility"]).strip()
            our_combatant = self._build_combatant(species, override=ours_override or None)
            our_set_moves = self._set_moves_for(species)
            counterables_data = self.svc.countered_by(species, limit=40)
            counterables = {v["name"] for v in counterables_data.get("victims", [])}

            # Caller-controlled pool. Default to "meta_top" for BOTH roles so
            # defensive bulk tuning considers physical AND special threats
            # together — that way HP/Def/SpD get balanced realistically. The
            # user can still pick "vs counters" explicitly from the UI buttons
            # if they want to tune against the fighting/dark/etc. that battles
            # this mon specifically.
            requested_pool = (payload.get("pool") or "").lower()
            if not requested_pool:
                requested_pool = "meta_top"
            target_filter = (payload.get("targetSpecies") or "").strip()
            meta_pairs = self._resolve_pool_targets(
                pool_mode=requested_pool, subject_species=species, limit=meta_limit,
                target_filter=target_filter,
            )
            if not meta_pairs:
                meta_pairs = self._meta_targets_with_moveset(limit=meta_limit)

            weather = (payload.get("weather") or "").lower()
            ignore_ab_weather = bool(payload.get("ignoreAbilityWeather"))
            result = make_spread(
                our_mon=our_combatant,
                nature=nature,
                fixed_evs=fixed,
                meta_targets=meta_pairs,
                our_set_moves=our_set_moves,
                counterables=counterables,
                role_override=role_override,
                weather=weather,
                ignore_ab_weather=ignore_ab_weather,
            )
            return {
                "ok": True,
                "species": species,
                "result": result.as_dict(),
                "metaTargetsCount": len(meta_pairs),
                "counterablesCount": len(counterables),
                "ourSetMoves": our_set_moves,
                "weather": weather,
                "evScaleMax": {"perStat": 32, "total": EV_MAX_TOTAL},
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def _resolve_pool_targets(
        self,
        pool_mode: str,
        subject_species: str,
        limit: int = 40,
        target_filter: str = "",
    ) -> list:
        """Same as _meta_targets_with_moveset but lets the caller pick the pool.

        pool_mode ∈ {meta_top, all, counters, victims, single}.
        For 'single', `target_filter` is the species to use.
        """
        from pokemon_anti_meta_builder.damage_calc.calculator import MOVE_LIBRARY

        if pool_mode == "single":
            species = target_filter.strip()
            if not species:
                return []
            try:
                target = self._build_combatant(species)
            except ValueError:
                return []
            # Apply top Pokékipe spread if available
            spreads = top_n_spreads(self.svc.meta_by_key.get(to_key(species)), n=1) if self.svc.meta_by_key.get(to_key(species)) else []
            if spreads:
                target = self._apply_spread(target, {
                    "nature": spreads[0]["nature"], "evs": spreads[0]["evs"],
                })
            mon = self.svc.meta_by_key.get(to_key(species))
            moves: list[str] = []
            if mon and mon.moves:
                moves = [opt.name for opt in mon.moves[:4]
                         if opt.name in MOVE_LIBRARY and int(MOVE_LIBRARY[opt.name].get("bp") or 0) > 0]
            if not moves:
                moves = self._set_moves_for(species)
            return [(target, moves)] if moves else []

        if pool_mode in ("counters", "victims"):
            if pool_mode == "counters":
                data = self.svc.counter_lookup(subject_species, limit=limit)
                names = [c["name"] for c in data.get("counters", [])]
            else:
                data = self.svc.countered_by(subject_species, limit=limit)
                names = [c["name"] for c in data.get("victims", [])]
        elif pool_mode == "all":
            sorted_pool = [m for m in self.svc.full_pool if m.usage > 0 or m.ev_spreads]
            sorted_pool.sort(key=lambda m: -m.usage)
            names = [m.name for m in sorted_pool[:limit]]
        else:  # meta_top
            sorted_pool = sorted(self.svc.full_pool, key=lambda m: -m.usage)
            on_meta = [m for m in sorted_pool if m.usage > 0][:limit]
            if len(on_meta) < limit:
                rest = [m for m in sorted_pool if m.usage <= 0][:limit - len(on_meta)]
                on_meta.extend(rest)
            names = [m.name for m in on_meta]

        out: list = []
        for name in names:
            try:
                target = self._build_combatant(name)
            except ValueError:
                continue
            mon = self.svc.meta_by_key.get(to_key(name))
            if mon:
                spreads = top_n_spreads(mon, n=1)
                if spreads:
                    target = self._apply_spread(target, {
                        "nature": spreads[0]["nature"],
                        "evs": spreads[0]["evs"],
                    })
                moves = [opt.name for opt in mon.moves[:4]
                         if opt.name in MOVE_LIBRARY and int(MOVE_LIBRARY[opt.name].get("bp") or 0) > 0]
            else:
                moves = self._set_moves_for(name)
            if moves:
                out.append((target, moves))
        return out

    def _meta_targets_with_moveset(self, limit: int = 40) -> list:
        """[(combatant_with_top_spread, [moves_in_set]), ...] for top meta.

        Uses the FULL pool (Pokékipe meta + Pikalytics-hydrated off-meta) sorted
        by usage, so "top 40" really returns up to 40 species instead of being
        capped at the ~30 Pokékipe entries.
        """
        from pokemon_anti_meta_builder.damage_calc.calculator import MOVE_LIBRARY

        usage_sorted = sorted(self.svc.full_pool, key=lambda m: -m.usage)
        with_data = [m for m in usage_sorted if m.usage > 0 or m.ev_spreads]
        pool = with_data[:limit]
        out: list = []
        for mon in pool:
            try:
                target = self._build_combatant(mon.name)
            except ValueError:
                continue
            spreads = top_n_spreads(mon, n=1)
            if spreads:
                target = self._apply_spread(target, {
                    "nature": spreads[0]["nature"],
                    "evs": spreads[0]["evs"],
                })
            move_names = [
                opt.name for opt in mon.moves[:4]
                if opt.name in MOVE_LIBRARY and int(MOVE_LIBRARY[opt.name].get("bp") or 0) > 0
            ]
            if not move_names:
                continue
            out.append((target, move_names))
        return out

    def _set_moves_for(self, species: str) -> list[str]:
        """Return the canonical 4-move set for `species`, damage moves only.

        Strategy: take the moves the SetBuilder would actually put on this mon
        (top Pokékipe usage, capped at 4 — i.e. what people are really running),
        then filter to damage moves in MOVE_LIBRARY. Status moves (Protect,
        Synthesis, Will-O-Wisp, etc.) are intentionally excluded from this list
        because they don't matter for the damage report.

        Falls back to `combatant_payload` moves (also capped at 4) if Pokékipe
        has no entry for this species.
        """
        from pokemon_anti_meta_builder.damage_calc.calculator import MOVE_LIBRARY

        key = to_key(species)
        mon = self.svc.meta_by_key.get(key)
        moves: list[str] = []
        if mon and mon.moves:
            moves = [opt.name for opt in mon.moves[:4]]
        if not moves:
            payload = self.svc.combatant_payload(species)
            if isinstance(payload, dict) and payload.get("moves"):
                moves = list(payload["moves"])[:4]
        return [m for m in moves if m in MOVE_LIBRARY and int(MOVE_LIBRARY[m].get("bp") or 0) > 0]

    def _top_meta_speeds(self, limit: int = 25, pool_mode: str = "all", subject_species: str | None = None) -> list[tuple[str, int]]:
        """Return [(species, target_speed_with_top_spread), ...] for the chosen pool.

        `pool_mode`:
          - "meta_top25": classic top N Pokékipe meta (kept for retrocompat).
          - "all":        every mon in the pool that has at least one EV spread
                          available (Pokékipe meta + off-meta hydrated by
                          Pikalytics). Vastly wider coverage.
          - "counters":   only mons that counter `subject_species`.
          - "victims":    only mons that `subject_species` counters.

        Target speed is computed by applying each mon's top (nature, spread).
        """
        from pokemon_anti_meta_builder.meta_parser.normalizer import to_key

        if pool_mode in ("meta_top25", "meta_top", "top_meta"):
            # Pokékipe meta has only ~30 entries with usage>0; extend with the
            # Pikalytics-hydrated off-meta pool sorted by usage so "top 40"
            # actually returns up to 40 species, not 30.
            usage_sorted = sorted(self.svc.full_pool, key=lambda m: -m.usage)
            source_mons = [m for m in usage_sorted if m.usage > 0][:limit]
            if len(source_mons) < limit:
                # If still short, pad with the next mons (usage 0) by name.
                rest = [m for m in usage_sorted if m.usage <= 0][:limit - len(source_mons)]
                source_mons.extend(rest)
        elif pool_mode in ("counters", "victims"):
            if not subject_species:
                return []
            if pool_mode == "counters":
                data = self.svc.counter_lookup(subject_species, limit=40)
                names = [c["name"] for c in data.get("counters", [])]
            else:
                data = self.svc.countered_by(subject_species, limit=40)
                names = [c["name"] for c in data.get("victims", [])]
            by_key = {to_key(m.name): m for m in self.svc.full_pool}
            source_mons = [by_key[to_key(n)] for n in names if to_key(n) in by_key]
        else:  # "all"
            source_mons = [m for m in self.svc.full_pool if m.ev_spreads or m.raw.get("pikalytics")]

        out: list[tuple[str, int]] = []
        for mon in source_mons:
            try:
                target = self._build_combatant(mon.name)
            except ValueError:
                continue
            spreads = top_n_spreads(mon, n=1)
            if spreads:
                target = self._apply_spread(target, {
                    "nature": spreads[0]["nature"],
                    "evs": spreads[0]["evs"],
                })
            spe = target.stat("spe")
            if spe > 0:
                out.append((mon.name, spe))
        return out

    # --- helpers ------------------------------------------------------------

    def _build_combatant(self, species: str, role_hint: str | None = None, override: dict[str, Any] | None = None) -> Combatant:
        payload = self.svc.combatant_payload(species, override)
        if "error" in payload:
            raise ValueError(payload["error"])
        evs = payload.get("evs") or {}
        ivs = payload.get("ivs") or {k: 31 for k in ("hp", "atk", "def", "spa", "spd", "spe")}
        return Combatant(
            name=payload.get("name", species),
            level=int(payload.get("level", 50) or 50),
            types=[str(t).lower() for t in payload.get("types") or []],
            base_stats={k: int(v or 0) for k, v in (payload.get("baseStats") or {}).items()},
            evs={k: int(v or 0) for k, v in evs.items()},
            ivs={k: int(v if v is not None else 31) for k, v in ivs.items()},
            nature=payload.get("nature", "Hardy") or "Hardy",
            ability=str(payload.get("ability") or ""),
        )

    def _resolve_target_spread(self, species: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Pick the (nature, evs, usage) we'll apply to the target.

        Priority:
          1. `targetSpreadManual: {nature, evs}` (with validation)
          2. `targetSpreadIndex: int` (into top_n_spreads, default 0)
          3. Pokékipe top spread
          4. Generic offensive fallback for off-meta targets
        """
        manual = payload.get("targetSpreadManual")
        if isinstance(manual, dict) and manual.get("nature") and isinstance(manual.get("evs"), dict):
            _validate_manual_spread(manual)
            return {
                "source": "manual",
                "nature": str(manual["nature"]),
                "evs": {k: int(manual["evs"].get(k, 0) or 0) for k in ("hp", "atk", "def", "spa", "spd", "spe")},
                "usage": None,
            }

        mon = self.svc.meta_by_key.get(to_key(species))
        spreads = top_n_spreads(mon, n=3) if mon else []
        idx = int(payload.get("targetSpreadIndex") or 0)
        if 0 <= idx < len(spreads):
            picked = spreads[idx]
            return {"source": "pokekipe", "nature": picked["nature"], "evs": picked["evs"], "usage": picked["usage"]}

        # off-meta or empty spreads -> generic fallback
        fallback = default_target_evs()
        return {"source": "fallback", "nature": "Adamant", "evs": fallback.as_dict(), "usage": None}

    def _apply_spread(self, mon: Combatant, spread: dict[str, Any]) -> Combatant:
        evs = {k: int(spread["evs"].get(k, 0) or 0) for k in ("hp", "atk", "def", "spa", "spd", "spe")}
        return Combatant(
            name=mon.name,
            level=mon.level,
            types=list(mon.types),
            base_stats=dict(mon.base_stats),
            evs=evs,
            ivs=dict(mon.ivs),
            nature=spread["nature"],
            boosts=dict(mon.boosts),
            tera_type=mon.tera_type,
            is_burned=mon.is_burned,
            ability=mon.ability,
        )


# --- module-level helpers ---------------------------------------------------

def _field_from(raw: dict[str, Any]) -> Field:
    return Field(
        weather=str(raw.get("weather") or ""),
        terrain=str(raw.get("terrain") or ""),
        light_screen=bool(raw.get("lightScreen")),
        reflect=bool(raw.get("reflect")),
        aurora_veil=bool(raw.get("auroraVeil")),
        spread=bool(raw.get("spread", True)),
        crit=bool(raw.get("crit")),
    )


def _require_move(payload: dict[str, Any]) -> str:
    move = (payload.get("move") or "").strip()
    if not move:
        raise ValueError("Mossa mancante")
    if move not in MOVE_LIBRARY:
        raise ValueError(f"Mossa '{move}' non supportata dal lite engine")
    return move


def _validate_manual_spread(manual: dict[str, Any]) -> None:
    from pokemon_anti_meta_builder.damage_calc.calculator import NATURE_MODIFIERS

    nature = manual.get("nature")
    if nature not in NATURE_MODIFIERS:
        raise ValueError(f"Nature non valida: {nature}")
    evs = manual.get("evs") or {}
    total = 0
    for stat in ("hp", "atk", "def", "spa", "spd", "spe"):
        value = int(evs.get(stat, 0) or 0)
        if value < 0 or value > EV_MAX_PER_STAT:
            raise ValueError(f"EV {stat}={value} fuori dal range 0-{EV_MAX_PER_STAT}")
        total += value
    if total > EV_MAX_TOTAL:
        raise ValueError(f"Totale EV {total} > {EV_MAX_TOTAL} (cap Champions)")


def _detect_role(mon: Combatant) -> str:
    base = mon.base_stats or {}
    atk = base.get("atk", 0)
    spa = base.get("spa", 0)
    if atk and spa:
        if atk >= spa + 15:
            return "physical-attacker"
        if spa >= atk + 15:
            return "special-attacker"
    elif atk:
        return "physical-attacker"
    elif spa:
        return "special-attacker"
    return "flex"


def _assumptions_payload(target: Combatant, spread: dict[str, Any]) -> dict[str, Any]:
    return {
        "targetName": target.name,
        "targetTypes": list(target.types),
        "targetNature": target.nature,
        "targetEvs": dict(target.evs),
        "spreadSource": spread.get("source"),
        "spreadUsage": spread.get("usage"),
        "evScaleNote": f"Scala Champions: max {EV_MAX_PER_STAT}/stat, totale {EV_MAX_TOTAL}",
    }
