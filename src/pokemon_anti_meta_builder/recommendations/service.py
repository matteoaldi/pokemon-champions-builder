from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pokemon_anti_meta_builder.data_fetcher import (
    load_meta_file,
    load_showdown_dex,
    load_showdown_learnsets,
    load_showdown_mega_forms,
)
from pokemon_anti_meta_builder.format_rules import filter_legal_meta
from pokemon_anti_meta_builder.meta_parser.normalizer import normalize_name, to_key
from pokemon_anti_meta_builder.models import PokemonMeta, PokemonSet, WeightedOption
from pokemon_anti_meta_builder.set_builder import SetBuilder
from pokemon_anti_meta_builder.team_builder import TeamBuilder


@dataclass
class BuilderState:
    format_id: str
    selected: list[str]
    team: list[PokemonSet]
    recommendations: list[dict[str, Any]]
    threat_report: str
    threat_entries: list[dict[str, Any]]
    roles: dict[str, int]
    synergy: list[str]
    warnings: list[str]
    digest: dict[str, Any] = None
    counters: dict[str, Any] = None

    def as_dict(self) -> dict[str, Any]:
        meta_lookup = getattr(self, "_meta_by_key", None)
        mega_lookup = getattr(self, "_mega_lookup", None)
        return {
            "format": self.format_id,
            "selected": self.selected,
            "team": [_set_to_dict(member, meta_lookup, mega_lookup) for member in self.team],
            "recommendations": self.recommendations,
            "threatReport": self.threat_report,
            "threatEntries": list(self.threat_entries),
            "roles": self.roles,
            "synergy": self.synergy,
            "warnings": self.warnings,
            "digest": self.digest or {"team_size": 0, "top_threats": [], "top_counters": []},
            "counters": self.counters or {"members": []},
        }


class RecommendationService:
    def __init__(
        self,
        input_path: str | Path,
        format_id: str = "reg-ma",
        dex_path: str | Path | None = None,
        learnsets_path: str | Path | None = None,
        pikalytics_path: str | Path | None = None,
    ):
        self.input_path = Path(input_path)
        self.format_id = format_id
        meta = load_meta_file(self.input_path)
        self.meta, self.legality_warnings = filter_legal_meta(meta, format_id)
        self.dex = load_showdown_dex(dex_path) if dex_path else []
        self.dex_by_key = {to_key(entry.get("name", "")): entry for entry in self.dex if entry.get("name")}
        # Extend dex lookup so alt_forms (Rotom-Wash, Slowking-Galar, ecc.) fall
        # back to their base entry's stats — better than empty base_stats which
        # would make HP=0 and damage% explode.
        for entry in self.dex:
            for form_name in (entry.get("alt_forms") or []):
                fk = to_key(form_name)
                if fk and fk not in self.dex_by_key:
                    self.dex_by_key[fk] = entry
        self.off_meta = _build_off_meta_entries(self.meta, self.dex, format_id)
        # Optionally hydrate off-meta entries with Pikalytics-sourced sets
        # (items/abilities/moves/spread/nature) so the SetBuilder produces
        # something better than the role-based fallback for mons like
        # Aggron/Primarina that Pokekipe doesn't track.
        self.pikalytics_sets: dict[str, dict] = {}
        if pikalytics_path:
            from pokemon_anti_meta_builder.data_fetcher.pikalytics import load_cache
            self.pikalytics_sets = load_cache(pikalytics_path)
            self._apply_pikalytics_to_off_meta()
        self.full_pool: list[PokemonMeta] = list(self.meta) + list(self.off_meta)
        self.meta_by_key = {to_key(mon.name): mon for mon in self.full_pool}
        self.off_meta_keys = {to_key(mon.name) for mon in self.off_meta}
        self.learnsets = load_showdown_learnsets(learnsets_path) if learnsets_path else {}
        self.learnsets_by_key = {to_key(name): moves for name, moves in self.learnsets.items()}
        self.mega_forms = load_showdown_mega_forms(dex_path) if dex_path else []
        self.mega_form_lookup = _build_mega_form_lookup(self.mega_forms)
        self.set_builder = SetBuilder()
        self.team_builder = TeamBuilder()

    def _apply_pikalytics_to_off_meta(self) -> None:
        """Hydrate self.off_meta entries with Pikalytics-sourced data.

        For each off-meta species we have parsed Pikalytics data for, populate
        items/abilities/moves/ev_spreads/natures so the SetBuilder picks them
        up instead of falling back to a role-based default. Items are filtered
        against the Reg M-A legal whitelist to avoid Life Orb/Specs/etc.
        """
        from pokemon_anti_meta_builder.format_rules.reg_ma import REG_MA_LEGAL_ITEMS

        legal_lower = {item.lower() for item in REG_MA_LEGAL_ITEMS}
        for i, mon in enumerate(self.off_meta):
            data = self.pikalytics_sets.get(mon.name)
            if not data:
                continue
            items = [
                WeightedOption(name=it["name"], weight=float(it["pct"]))
                for it in (data.get("items") or [])
                if it.get("name") and it["name"].lower() in legal_lower
            ]
            abilities = [
                WeightedOption(name=ab["name"], weight=float(ab["pct"]))
                for ab in (data.get("abilities") or [])
                if ab.get("name")
            ]
            moves = [
                WeightedOption(name=mv["name"], weight=float(mv["pct"]))
                for mv in (data.get("moves") or [])
                if mv.get("name")
            ]
            ev_spreads: list[WeightedOption] = []
            natures: list[WeightedOption] = []
            if data.get("topNature") and data.get("topSpread"):
                spread_text = f"{data['topNature']}:{data['topSpread']}"
                pct = float(data.get("topSpreadPct") or 0.0)
                ev_spreads.append(WeightedOption(name=spread_text, weight=pct))
                natures.append(WeightedOption(name=data["topNature"], weight=pct))

            self.off_meta[i] = PokemonMeta(
                name=mon.name,
                usage=float(data.get("usage") or 0.0),
                winrate=float(data.get("winrate") or 0.0) if data.get("winrate") else mon.winrate,
                types=list(mon.types),
                items=items or list(mon.items),
                abilities=abilities or list(mon.abilities),
                moves=moves or list(mon.moves),
                ev_spreads=ev_spreads or list(mon.ev_spreads),
                natures=natures or list(mon.natures),
                teammates=list(mon.teammates),
                checks_counters=list(mon.checks_counters),
                roles=list(mon.roles),
                raw={**mon.raw, "pikalytics": True},
            )

    def catalog(self) -> dict[str, Any]:
        return {
            "format": self.format_id,
            "pokemon": [
                {
                    "name": mon.name,
                    "usage": mon.usage,
                    "winrate": mon.winrate,
                    "types": mon.types,
                    "roles": mon.roles,
                    "topItem": mon.items[0].name if mon.items else "",
                    "offMeta": to_key(mon.name) in self.off_meta_keys,
                    # hasData=False -> legal in Reg M-A but nobody plays it (no Pikalytics
                    # set, no Pokékipe usage); the UI hides these by default.
                    "hasData": (to_key(mon.name) not in self.off_meta_keys) or bool(mon.raw.get("pikalytics")),
                    "num": self.dex_by_key.get(to_key(mon.name), {}).get("num"),
                }
                for mon in self.full_pool
            ],
            "megaForms": [
                {
                    "name": form.get("name"),
                    "baseSpecies": form.get("base_species"),
                    "types": form.get("types", []),
                    "item": form.get("required_item"),
                    "num": form.get("num"),
                }
                for form in self.mega_forms
            ],
        }

    def build_state(
        self,
        selected: list[str] | None = None,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> BuilderState:
        selected_meta = self._selected_meta(selected or [])
        warnings = list(self.legality_warnings)
        if len(selected_meta) > 6:
            warnings.append("Team has more than 6 Pokemon; only the first 6 are used.")
            selected_meta = selected_meta[:6]
        overrides_by_key = {to_key(name): payload for name, payload in (overrides or {}).items()}
        team = []
        used_items: set[str] = set()
        for mon in selected_meta:
            member = self.set_builder.build_set(mon, used_items=used_items)
            override = overrides_by_key.get(to_key(mon.name))
            if override:
                member = _apply_overrides(member, override)
            team.append(member)
            if member.item:
                used_items.add(member.item)
        warnings.extend(warning for member in team for warning in member.warnings)
        warnings.extend(_team_rule_warnings(team))
        recommendations = self.recommend_next(selected_meta)
        if team:
            counters_payload = self.team_counters(
                [mon.name for mon in selected_meta], overrides=overrides, team_sets=team
            )
            threat_entries = counters_payload.get("threats", [])
            threat_report = _render_threat_report(threat_entries)
        else:
            threat_report = "Aggiungi Pokémon per iniziare l'analisi matchup."
            threat_entries = []
            counters_payload = {"members": [], "threats": []}
        digest = self.team_digest([mon.name for mon in selected_meta]) if selected_meta else None
        state = BuilderState(
            format_id=self.format_id,
            selected=[mon.name for mon in selected_meta],
            team=team,
            recommendations=recommendations,
            threat_report=threat_report,
            threat_entries=threat_entries,
            roles=_role_counts(team),
            synergy=_synergy_notes(selected_meta, team),
            warnings=warnings,
            digest=digest,
            counters=counters_payload,
        )
        state._meta_by_key = self.meta_by_key
        state._mega_lookup = self.mega_form_lookup
        return state

    def auto_build(
        self,
        seed: list[str] | None = None,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> BuilderState:
        """Fill empty slots of the team with picks that minimize counter exposure.

        Keeps the seed (Pokémon already chosen by the user) untouched and
        extends it up to 6 members using `_best_counter_minimizing_candidate`.
        No archetype influence — pure "what hurts our team the least".
        Hard rules (mega clause / item clause) are enforced as exclusions.
        """
        selected = list(seed or [])
        while len(selected) < 6:
            current = self._selected_meta(selected)
            best = self._best_counter_minimizing_candidate(current, selected)
            if not best:
                break
            selected.append(best.name)
        return self.build_state(selected, overrides=overrides)

    def _best_counter_minimizing_candidate(
        self,
        current: list[PokemonMeta],
        selected_names: list[str],
    ) -> PokemonMeta | None:
        selected_keys = {to_key(name) for name in selected_names}
        best: PokemonMeta | None = None
        best_score: float | None = None
        for candidate in self.meta:
            if to_key(candidate.name) in selected_keys:
                continue
            if _would_break_mega_rule(candidate, current):
                continue
            if _would_duplicate_item(candidate, current):
                continue

            hypothetical = current + [candidate]
            targets = self._team_counter_targets(hypothetical)
            total_weight = sum(t["weight"] for t in targets)
            unique_threats = len(targets)

            # Lower score = better. usage is a tiebreaker so we prefer proven
            # meta picks among candidates that tie on counter exposure.
            score = unique_threats * 12 + total_weight - candidate.usage * 0.2
            if best_score is None or score < best_score:
                best_score = score
                best = candidate
        return best

    # Recommend v2 component weights (sum 100). Priority: team synergy first,
    # then counter coverage, then recurring teammates, then raw meta strength.
    RECO_WEIGHTS = {"synergy": 0.35, "counter": 0.30, "teammate": 0.20, "meta": 0.15}

    def recommend_next(self, selected_meta: list[PokemonMeta], limit: int = 6) -> list[dict[str, Any]]:
        """Score candidates with four normalized (0..1) components, weighted.

        Candidate pool is every mon WITH real data (on-meta + Pikalytics-hydrated
        off-meta); the 24 no-data legal mons are excluded. Each recommendation
        carries a `breakdown` of the four weighted contributions for transparency.
        """
        selected_keys = {to_key(mon.name) for mon in selected_meta}
        targets = self._team_counter_targets(selected_meta)
        total_target_weight = sum(t["weight"] for t in targets) or 1.0
        team_weak = self._team_weakness_profile(selected_meta)
        team_names = {mon.name for mon in selected_meta}
        team_roles = {role for mon in selected_meta for role in mon.roles}
        from pokemon_anti_meta_builder.team_builder.builder import TARGET_ROLES
        missing_roles = set(TARGET_ROLES) - team_roles
        W = self.RECO_WEIGHTS

        candidates = [
            c for c in self.full_pool
            if to_key(c.name) not in selected_keys
            and (to_key(c.name) not in self.off_meta_keys or bool(c.raw.get("pikalytics")))
        ]

        scored: list[tuple[float, PokemonMeta, list[str], dict[str, float]]] = []
        for candidate in candidates:
            if _would_break_mega_rule(candidate, selected_meta):
                continue  # Reg M-A: only one Mega Stone per team
            if _would_duplicate_item(candidate, selected_meta):
                continue  # Item Clause: skip duplicates outright

            reasons: list[str] = []

            # (1) Synergy + types to cover (0..1): defensive type synergy + missing roles.
            synergy_c, syn_reasons = _synergy_component(candidate, team_weak, missing_roles)
            reasons.extend(syn_reasons)

            # (2) Counter coverage (0..1): how much of the team's current counters it answers.
            covered = _candidate_covers(candidate, targets)
            counter_c = min(1.0, sum(t["weight"] for t in covered) / total_target_weight) if targets else 0.0
            if covered:
                reasons.append("batte i tuoi counter: " + ", ".join(t["name"] for t in covered[:3]))

            # (3) Teammate synergy (0..1): recurring Pokékipe teammates already on the team.
            tm_weight = sum(opt.weight for opt in candidate.teammates if opt.name in team_names)
            teammate_c = min(1.0, tm_weight / 30.0)
            if teammate_c > 0:
                reasons.append("compagno ricorrente con il tuo team")

            # (4) Meta strength (0..1): usage + winrate.
            usage_c = min(1.0, (candidate.usage or 0.0) / 40.0)
            wr = candidate.winrate
            wr_c = min(1.0, max(0.0, (wr - 45.0) / 15.0)) if wr is not None else 0.0
            meta_c = 0.6 * usage_c + 0.4 * wr_c

            breakdown = {
                "synergy": round(100 * W["synergy"] * synergy_c, 1),
                "counter": round(100 * W["counter"] * counter_c, 1),
                "teammate": round(100 * W["teammate"] * teammate_c, 1),
                "meta": round(100 * W["meta"] * meta_c, 1),
            }
            total = sum(breakdown.values())
            scored.append((total, candidate, reasons, breakdown))

        scored.sort(key=lambda item: (item[0], item[1].usage), reverse=True)
        return [
            {
                "name": mon.name,
                "score": round(total, 1),
                "breakdown": breakdown,
                "usage": mon.usage,
                "winrate": mon.winrate,
                "types": mon.types,
                "roles": mon.roles,
                "offMeta": to_key(mon.name) in self.off_meta_keys,
                "item": mon.items[0].name if mon.items else "",
                "ability": mon.abilities[0].name if mon.abilities else "",
                "moves": [move.name for move in mon.moves[:4]],
                "reasons": reasons or ["buon profilo generale"],
            }
            for total, mon, reasons, breakdown in scored[:limit]
        ]

    def _team_weakness_profile(self, selected_meta: list[PokemonMeta]) -> dict[str, int]:
        """Map attacking_type -> how many team members take super-effective damage from it."""
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        profile: dict[str, int] = {}
        for mon in selected_meta:
            for attack_type, chart in TYPE_CHART.items():
                mult = 1.0
                for def_type in mon.types:
                    mult *= chart.get(def_type, 1.0)
                if mult >= 2.0:
                    profile[attack_type] = profile.get(attack_type, 0) + 1
        return profile

    def _team_counter_targets(self, selected_meta: list[PokemonMeta]) -> list[dict[str, Any]]:
        """Aggregate threats that currently counter the team.

        Each entry: {name, key, types, weight, counter_keys} where:
          - weight: how much this threat presses the team (Pokekipe usage % vs
            the picked mon, summed across team; or meta usage as fallback).
          - counter_keys: set of normalized keys of Pokemon that Pokekipe lists
            as checks/counters of this threat. Used to decide if a candidate
            answers the threat without relying on type matchup.
        """
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        meta_by_key = {to_key(mon.name): mon for mon in self.meta}
        aggregated: dict[str, dict[str, Any]] = {}

        def bucket_for(threat: PokemonMeta) -> dict[str, Any]:
            key = to_key(threat.name)
            existing = aggregated.get(key)
            if existing is None:
                existing = {
                    "name": threat.name,
                    "key": key,
                    "types": threat.types,
                    "weight": 0.0,
                    "counter_keys": {to_key(option.name) for option in threat.checks_counters},
                }
                aggregated[key] = existing
            return existing

        for mon in selected_meta:
            if mon.checks_counters:
                for option in mon.checks_counters:
                    threat_meta = meta_by_key.get(to_key(option.name))
                    if threat_meta is None:
                        continue
                    bucket_for(threat_meta)["weight"] += option.weight
            else:
                for threat in self.meta:
                    if to_key(threat.name) == to_key(mon.name):
                        continue
                    if _stab_super_effective(threat, mon, TYPE_CHART):
                        bucket_for(threat)["weight"] += threat.usage * 0.5
        return sorted(aggregated.values(), key=lambda entry: entry["weight"], reverse=True)

    def team_digest(self, selected: list[str]) -> dict[str, Any]:
        """Compact summary of biggest threats and counters across the picked team.

        Returns top_threats (mons that pressure most of the team) and
        top_counters (mons that appear as counter to most members). Used to
        give a quick verdict once the team is mostly built.
        """
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        selected_meta = self._selected_meta(selected)
        if not selected_meta:
            return {"top_threats": [], "top_counters": [], "team_size": 0}

        threat_score: dict[str, dict[str, Any]] = {}
        counter_score: dict[str, dict[str, Any]] = {}
        for mon in selected_meta:
            # Threats: meta mon whose STABs are super-effective against this team mon
            for threat in self.meta:
                if to_key(threat.name) == to_key(mon.name):
                    continue
                if _stab_super_effective(threat, mon, TYPE_CHART):
                    bucket = threat_score.setdefault(
                        to_key(threat.name),
                        {"name": threat.name, "weight": 0.0, "hits": 0, "types": threat.types},
                    )
                    bucket["weight"] += threat.usage
                    bucket["hits"] += 1
            # Counters: from Pokekipe data on this mon (if any), else from type fallback
            if mon.checks_counters:
                for option in mon.checks_counters:
                    bucket = counter_score.setdefault(
                        to_key(option.name),
                        {"name": option.name, "weight": 0.0, "hits": 0, "source": "pokekipe"},
                    )
                    bucket["weight"] += option.weight
                    bucket["hits"] += 1
            else:
                for threat in self.meta:
                    if to_key(threat.name) == to_key(mon.name):
                        continue
                    if _stab_super_effective(threat, mon, TYPE_CHART):
                        bucket = counter_score.setdefault(
                            to_key(threat.name),
                            {"name": threat.name, "weight": 0.0, "hits": 0, "source": "type-fallback"},
                        )
                        bucket["weight"] += threat.usage * 0.5
                        bucket["hits"] += 1

        top_threats = sorted(threat_score.values(), key=lambda e: (e["hits"], e["weight"]), reverse=True)[:5]
        top_counters = sorted(counter_score.values(), key=lambda e: (e["hits"], e["weight"]), reverse=True)[:5]
        return {
            "team_size": len(selected_meta),
            "top_threats": [
                {"name": t["name"], "hits": t["hits"], "weight": round(t["weight"], 1)}
                for t in top_threats
            ],
            "top_counters": [
                {"name": c["name"], "hits": c["hits"], "weight": round(c["weight"], 1), "source": c["source"]}
                for c in top_counters
            ],
        }

    def edit_options(self, name: str) -> dict[str, Any]:
        """Legal item/ability/move lists for the slot-edit UI.

        - Items: REG_MA_LEGAL_ITEMS sorted (every legal Reg M-A item, so the
          user can pick anything legal). The mega stone keyed to this species
          is bubbled to the top.
        - Abilities: from the Showdown dex entry, plus the mega form's ability
          when applicable.
        - Moves: from the gen-9 learnset; sorted alphabetically.
        """
        from pokemon_anti_meta_builder.format_rules.reg_ma import REG_MA_LEGAL_ITEMS

        key = to_key(name)
        dex_entry = self.dex_by_key.get(key, {})
        mon = self.meta_by_key.get(key)
        if mon is None and not dex_entry:
            return {"notFound": True, "name": name}

        abilities: list[str] = []
        seen_ability_keys: set[str] = set()

        def add_ability(name: str) -> None:
            normalized_key = to_key(name)
            if not name or normalized_key in seen_ability_keys:
                return
            abilities.append(name)
            seen_ability_keys.add(normalized_key)

        for ability in dex_entry.get("abilities", []):
            add_ability(ability)
        if mon and mon.abilities:
            for option in mon.abilities:
                add_ability(option.name)

        # Mega form ability for this species (if any)
        species_mega = None
        for form in self.mega_forms:
            if to_key(form.get("base_species", "")) == key:
                species_mega = form
                for ability in form.get("abilities", []):
                    add_ability(ability)
                break

        items = sorted(REG_MA_LEGAL_ITEMS)
        mega_item = species_mega.get("required_item") if species_mega else None
        if mega_item and mega_item in items:
            items.remove(mega_item)
            items.insert(0, mega_item)

        learnset = self.learnsets_by_key.get(key, [])
        moves = sorted(learnset)

        return {
            "name": mon.name if mon else (dex_entry.get("name") or normalize_name(name)),
            "legalItems": items,
            "legalAbilities": abilities,
            "legalMoves": moves,
            "megaItem": mega_item,
            "megaForm": species_mega.get("name") if species_mega else None,
        }

    def _built_set(self, name: str):
        """Build (and cache) the meta/Pikalytics set for `name`. Mega form names
        resolve to the base species (megas share the base movepool). Returns the
        built PokemonSet, or None when the mon is unknown / build fails."""
        cache = getattr(self, "_built_set_cache", None)
        if cache is None:
            cache = self._built_set_cache = {}
        key = to_key(name)
        if key in cache:
            return cache[key]
        direct_mega = next(
            (f for f in self.mega_forms if to_key(f.get("name", "")) == key), None
        )
        mon_key = to_key(direct_mega.get("base_species", "")) if direct_mega else key
        mon = self.meta_by_key.get(mon_key)
        built = None
        if mon is not None:
            try:
                built = self.set_builder.build_set(mon)
            except Exception:
                built = None
        cache[key] = built
        return built

    def _offensive_moves_vs(
        self, name: str, target_types: list[str]
    ) -> tuple[list[tuple[str, float]], bool]:
        """Real damaging moves from `name`'s set that hit `target_types` super-
        effectively. Returns (hits, has_set): hits is [(move_name, multiplier)];
        has_set is True only when the set actually had damaging moves we could
        read (so callers know whether to trust this over the STAB proxy)."""
        from pokemon_anti_meta_builder.constants import TYPE_CHART
        from pokemon_anti_meta_builder.damage_calc.calculator import get_move_library

        built = self._built_set(name)
        if built is None:
            return [], False
        library = get_move_library()
        hits: list[tuple[str, float]] = []
        has_damaging = False
        for move in built.moves:
            entry = library.get(move)
            if not entry or entry.get("category") == "status" or not entry.get("bp"):
                continue
            move_type = str(entry.get("type") or "").lower()
            if not move_type:
                continue
            has_damaging = True
            mult = _type_multiplier_dict(move_type, target_types, TYPE_CHART)
            if mult >= 2.0:
                hits.append((move, mult))
        return hits, has_damaging

    def _matchup_reasons(
        self,
        target_types: list[str],
        target_speed: int | None,
        counter_name: str,
        counter_types: list[str],
    ) -> dict[str, Any]:
        """Why `counter_name` beats the looked-up target: offensive edge (real
        damaging moves from the Pikalytics/meta set that hit SE, falling back to
        STAB types when no set is available), defensive resistances/immunities vs
        the target's STABs, and base-Speed comparison."""
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        reasons: list[str] = []
        # offense: prefer the counter's real moves; STAB types only as fallback
        move_hits, has_set = self._offensive_moves_vs(counter_name, target_types)
        if move_hits:
            seen: set[str] = set()
            for move, mult in sorted(move_hits, key=lambda x: -x[1])[:3]:
                if move in seen:
                    continue
                seen.add(move)
                reasons.append(f"{move} ×{int(mult)}")
        elif not has_set:
            stab_hits = [
                (t, _type_multiplier_dict(t, target_types, TYPE_CHART))
                for t in counter_types if t
            ]
            for t, mult in sorted((h for h in stab_hits if h[1] >= 2.0), key=lambda x: -x[1]):
                reasons.append(f"colpisce {t.capitalize()} ×{int(mult)}")

        # defense: target STAB types the counter resists / is immune to
        for t in target_types:
            if not t:
                continue
            mult = _type_multiplier_dict(t, counter_types, TYPE_CHART)
            if mult == 0:
                reasons.append(f"immune a {t.capitalize()}")
            elif mult <= 0.5:
                reasons.append(f"resiste {t.capitalize()}")

        # speed: base-Speed comparison (only when both known)
        counter_speed = self._base_speed(counter_name)
        speed_cmp = None
        if counter_speed is not None and target_speed is not None:
            if counter_speed > target_speed:
                speed_cmp = "faster"
                reasons.append(f"più veloce ({counter_speed} vs {target_speed})")
            elif counter_speed < target_speed:
                speed_cmp = "slower"
                reasons.append(f"più lento ({counter_speed} vs {target_speed})")
            else:
                speed_cmp = "tie"
                reasons.append(f"speed tie ({counter_speed})")
        return {"reasons": reasons, "speedCmp": speed_cmp}

    def counter_lookup(self, name: str, limit: int = 12) -> dict[str, Any]:
        """Stand-alone "who counters X" lookup, for the search-a-mon panel.

        Accepts base species names OR mega form names (e.g. "Charizard-Mega-X"):
        when given a mega form, the lookup uses the mega's types and abilities
        instead of the base — because Mega Charizard X being Fire/Dragon is
        counter-checked very differently from base Fire/Flying Charizard.

        Candidates come from the full pool (meta + off-meta). Meta picks come
        first sorted by usage; off-meta picks follow, marked with offMeta=true
        so the UI can group/style them. This lets the user discover counters
        outside the meta usage list (es. Quagsire vs Garchomp).
        """
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        key = to_key(name)

        # Mega form direct lookup (Garchomp-Mega, Charizard-Mega-X, ...)
        mega = next(
            (form for form in self.mega_forms if to_key(form.get("name", "")) == key),
            None,
        )
        is_mega = bool(mega)
        if is_mega:
            base_key = to_key(mega.get("base_species", ""))
            target = self.meta_by_key.get(base_key)
            target_types = [t.lower() for t in (mega.get("types") or [])]
            display = mega.get("name") or name
            checks_counters = []  # Pokekipe doesn't expose checks for mega forms separately
            usage = target.usage if target else 0.0
        else:
            target = self.meta_by_key.get(key)
            dex_entry = self.dex_by_key.get(key, {})
            if target is None and not dex_entry:
                return {"notFound": True, "name": name}

            if target is None:
                target_types = [t.lower() for t in dex_entry.get("types", [])]
                display = normalize_name(name)
                checks_counters = []
                usage = 0.0
            else:
                target_types = list(target.types)
                display = target.name
                checks_counters = list(target.checks_counters)
                usage = target.usage

        if is_mega:
            target_speed = (mega.get("base_stats") or {}).get("spe")
            target_speed = int(target_speed) if target_speed is not None else None
        else:
            target_speed = self._base_speed(key)

        if checks_counters:
            source = "pokekipe"
            entries = []
            for option in checks_counters[:limit]:
                opt_key = to_key(option.name)
                meta_entry = self.meta_by_key.get(opt_key)
                counter_types = list(meta_entry.types) if meta_entry else []
                entries.append({
                    "name": option.name,
                    "usage_vs": option.weight,
                    "meta_usage": meta_entry.usage if meta_entry else 0.0,
                    "types": counter_types,
                    "offMeta": opt_key in self.off_meta_keys,
                    **self._matchup_reasons(target_types, target_speed, option.name, counter_types),
                })
        else:
            source = "type-based"
            entries = []
            seen_keys: set[str] = set()

            # Iterate meta first (sorted by usage) so high-relevance picks
            # come first. Then off-meta (alphabetical) so the user sees
            # creative options below the well-known picks.
            ordered_candidates: list[PokemonMeta] = sorted(self.meta, key=lambda m: m.usage, reverse=True)
            ordered_candidates += sorted(self.off_meta, key=lambda m: m.name)

            for candidate in ordered_candidates:
                candidate_key = to_key(candidate.name)
                if candidate_key == key or candidate_key in seen_keys:
                    continue
                # type fallback: candidate hits target SE AND isn't weak to target's STABs
                hits_se = any(_type_multiplier_dict(t, target_types, TYPE_CHART) >= 2.0 for t in candidate.types if t)
                safe_from_x = all(_type_multiplier_dict(t, candidate.types, TYPE_CHART) <= 1.0 for t in target_types if t) if target_types else True
                if hits_se and safe_from_x:
                    entries.append({
                        "name": candidate.name,
                        "usage_vs": 0.0,
                        "meta_usage": candidate.usage,
                        "types": list(candidate.types),
                        "offMeta": candidate_key in self.off_meta_keys,
                        **self._matchup_reasons(target_types, target_speed, candidate.name, list(candidate.types)),
                    })
                    seen_keys.add(candidate_key)
                if len(entries) >= limit:
                    break

        return {
            "name": display,
            "types": target_types,
            "usage": usage,
            "offMeta": key in self.off_meta_keys,
            "isMega": is_mega,
            "source": source,
            "counters": entries,
        }

    def learnset_for(self, name: str) -> list[str]:
        """Return the gen-9 legal move list for `name` if loaded."""
        return list(self.learnsets_by_key.get(to_key(name), []))

    def countered_by(self, name: str, limit: int = 12) -> dict[str, Any]:
        """Inverse of counter_lookup: list mons that `name` itself counters.

        Combines two signals:
        - Pokekipe: every meta mon whose `checks_counters` includes `name`
          → that mon is naturally countered by `name`.
        - Type-based fallback: meta mons whose effective types are hit 2x
          by any of `name`'s STAB types AND whose own STABs are resisted by
          `name`.
        """
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        key = to_key(name)
        subject = self.meta_by_key.get(key)
        subject_types: list[str] = []
        if subject:
            subject_types = list(subject.types)
        else:
            dex_entry = self.dex_by_key.get(key, {})
            subject_types = [t.lower() for t in dex_entry.get("types", [])]
        if not subject_types:
            return {"name": name, "types": [], "victims": [], "source": "unknown"}

        # 1) Pokékipe explicit: meta mons that list `name` as a check/counter.
        explicit_hits: dict[str, dict[str, Any]] = {}
        for victim in self.meta:
            for opt in victim.checks_counters:
                if to_key(opt.name) == key:
                    explicit_hits[to_key(victim.name)] = {
                        "name": victim.name,
                        "usage_vs": float(opt.weight),
                        "meta_usage": victim.usage,
                        "types": list(victim.types),
                        "offMeta": False,
                        "source": "pokekipe",
                    }
                    break

        # 2) Type-based supplement, only for meta mons not already in explicit.
        type_hits: list[dict[str, Any]] = []
        for victim in self.meta:
            vkey = to_key(victim.name)
            if vkey == key or vkey in explicit_hits:
                continue
            hits_se = any(
                _type_multiplier_dict(t, victim.types, TYPE_CHART) >= 2.0
                for t in subject_types if t
            )
            safe_from_victim = all(
                _type_multiplier_dict(t, subject_types, TYPE_CHART) <= 1.0
                for t in victim.types if t
            ) if victim.types else True
            if hits_se and safe_from_victim:
                type_hits.append({
                    "name": victim.name,
                    "usage_vs": 0.0,
                    "meta_usage": victim.usage,
                    "types": list(victim.types),
                    "offMeta": False,
                    "source": "type-fallback",
                })

        explicit_list = sorted(explicit_hits.values(), key=lambda d: d["meta_usage"], reverse=True)
        type_hits.sort(key=lambda d: d["meta_usage"], reverse=True)
        merged = (explicit_list + type_hits)[:limit]
        return {
            "name": subject.name if subject else name,
            "types": subject_types,
            "victims": merged,
            "source": "mixed" if explicit_list and type_hits else ("pokekipe" if explicit_list else "type-fallback"),
        }

    def all_known_moves(self) -> list[str]:
        """All unique move names across loaded learnsets, sorted."""
        seen: set[str] = set()
        for moves in self.learnsets.values():
            for m in moves:
                seen.add(m)
        return sorted(seen)

    def species_with_move(self, move: str) -> list[str]:
        """Return all species (Reg M-A pool) whose learnset includes `move`.

        Match is case-insensitive on the move name. Only species present in
        the catalog (meta + off-meta) are returned, sorted with meta picks
        first (by usage desc) and off-meta after (alphabetical).
        """
        target = to_key(move)
        if not target or not self.learnsets_by_key:
            return []
        meta_keys = {to_key(mon.name): mon for mon in self.full_pool}
        on_meta: list[tuple[float, str]] = []
        off_meta_hits: list[str] = []
        for species_name, moves in self.learnsets.items():
            key = to_key(species_name)
            if key not in meta_keys:
                continue
            if not any(to_key(m) == target for m in moves):
                continue
            mon = meta_keys[key]
            if key in self.off_meta_keys:
                off_meta_hits.append(mon.name)
            else:
                on_meta.append((-mon.usage, mon.name))
        on_meta.sort()
        off_meta_hits.sort()
        return [name for _, name in on_meta] + off_meta_hits

    def combatant_payload(self, name: str, override: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build a damage-calculator-ready payload for `name`.

        Pulls types/base stats from the Showdown dex slice (when available)
        and EVs/nature/item/ability/moves from the meta-driven SetBuilder
        (or sensible fallbacks for off-meta picks). If the picked item is a
        Mega Stone, swap base stats / types / ability with the Mega form.
        """
        key = to_key(name)
        # 1) Direct mega form lookup. If `name` is e.g. "Charizard-Mega-Y",
        #    resolve to the base species (Charizard) for set data but swap in
        #    the mega's base stats/types/ability for stat math.
        direct_mega = next(
            (form for form in self.mega_forms if to_key(form.get("name", "")) == key),
            None,
        )
        if direct_mega:
            base_species_key = to_key(direct_mega.get("base_species", ""))
            mon = self.meta_by_key.get(base_species_key)
            dex_entry = self.dex_by_key.get(base_species_key, {})
        else:
            mon = self.meta_by_key.get(key)
            dex_entry = self.dex_by_key.get(key, {})
        if mon is None and not dex_entry:
            return {"error": f"unknown Pokemon: {name}"}
        if mon is None:
            mon = PokemonMeta(name=normalize_name(name), usage=0.0, types=[t.lower() for t in dex_entry.get("types", [])])
        built = self.set_builder.build_set(mon)
        # Apply optional override (item/ability/nature/moves/evs) — same shape
        # as the team `overrides` dict. This lets /api/combatant respect manual
        # tweaks (e.g. removed the mega stone) so the mega swap below sees the
        # post-override item.
        if override:
            built = _apply_overrides(built, override)

        display_name = built.species
        types = mon.types or [t.lower() for t in dex_entry.get("types", [])]
        base_stats = dex_entry.get("base_stats", {})
        ability = built.ability
        # Mega swap: prefer the direct lookup (user explicitly picked the mega
        # form name) over the item-based detection (legacy path for base
        # species + mega stone item).
        mega = direct_mega
        if mega is None and built.item:
            mega = self.mega_form_lookup.get(to_key(built.item))
        if mega and to_key(mega.get("base_species", "")) == to_key(built.species):
            display_name = mega["name"] or display_name
            types = mega["types"] or types
            base_stats = mega["base_stats"] or base_stats
            if mega["abilities"]:
                ability = mega["abilities"][0]

        return {
            "name": display_name,
            "speciesBase": built.species,
            "types": types,
            "baseStats": base_stats,
            "ability": ability,
            "item": built.item,
            "moves": built.moves,
            "evs": built.evs.as_dict(),
            "nature": built.nature,
            "level": 50,
            "offMeta": key in self.off_meta_keys,
            "isMega": bool(mega) and to_key(mega.get("base_species", "")) == to_key(built.species),
            "megaForm": mega["name"] if mega else None,
            "num": dex_entry.get("num"),
            "warnings": built.warnings,
        }

    def team_counters(
        self,
        selected: list[str],
        limit_per_mon: int = 6,
        overrides: dict[str, dict[str, Any]] | None = None,
        team_sets: list[PokemonSet] | None = None,
    ) -> dict[str, Any]:
        """For each picked Pokemon, list who counters it.

        We prefer Pokekipe's real `checks_counters` data. When a picked Pokemon
        is off-meta or has no Pokekipe entry, we fall back to a type-based
        guess: meta threats whose STABs deal >=2x to this Pokemon's effective
        types. The "effective types" account for the mega form when the team
        member is currently holding the matching mega stone (read from
        overrides[species].item).
        """
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        overrides_by_key = {to_key(name): payload for name, payload in (overrides or {}).items()}
        members: list[dict[str, Any]] = []
        selected_meta = self._selected_meta(selected)
        meta_by_key = {to_key(mon.name): mon for mon in self.meta}

        # Per-member profile reused by both the per-member list and the
        # team-wide threat-coverage view below. When the built team sets are
        # available we capture each member's real offensive move types so the
        # coverage view answers with actual coverage, not just STAB.
        sets_by_key = {to_key(m.species): m for m in (team_sets or [])}
        profiles: list[dict[str, Any]] = []
        for mon in selected_meta:
            override = overrides_by_key.get(to_key(mon.name)) or {}
            item = override.get("item")
            member_set = sets_by_key.get(to_key(mon.name))
            profiles.append(
                {
                    "meta": mon,
                    "key": to_key(mon.name),
                    "eff_types": self._effective_types_for(mon, item),
                    "counter_keys": {to_key(o.name) for o in mon.checks_counters},
                    "speed": self._base_speed(mon.name, item),
                    "mega": self._mega_for(mon.name, item),
                    "offense": self._offensive_types(member_set) if member_set else set(),
                }
            )

        for profile in profiles:
            mon = profile["meta"]
            effective_types = profile["eff_types"]
            mega = profile["mega"]
            display_name = mega["name"] if mega else mon.name

            real = mon.checks_counters
            if real and not mega:
                source = "pokekipe"
                entries = [
                    {
                        "name": option.name,
                        "usage": option.weight,
                        "meta_usage": (meta_by_key.get(to_key(option.name)) or PokemonMeta(name="", usage=0.0)).usage,
                    }
                    for option in real[:limit_per_mon]
                ]
            else:
                source = "type-fallback"
                entries = []
                seen_threat_keys: set[str] = set()
                mon_key = profile["key"]
                for threat in sorted(self.meta, key=lambda m: m.usage, reverse=True):
                    threat_key = to_key(threat.name)
                    if threat_key == mon_key or threat_key in seen_threat_keys:
                        continue
                    eff = self._effective_threat(threat)
                    if self._threat_pressures(eff["types"], eff["speed"], effective_types, profile["speed"]):
                        entries.append(
                            {
                                "name": threat.name,
                                "form": eff["form_name"],
                                "isMega": eff["is_mega"],
                                "usage": 0.0,
                                "meta_usage": threat.usage,
                            }
                        )
                        seen_threat_keys.add(threat_key)
                    if len(entries) >= limit_per_mon:
                        break
            members.append(
                {
                    "species": display_name,
                    "baseSpecies": mon.name,
                    "isMega": bool(mega),
                    "megaFallback": bool(mega and source == "type-fallback"),
                    "offMeta": to_key(mon.name) in self.off_meta_keys,
                    "source": source,
                    "counters": entries,
                }
            )
        threats = self._team_threat_coverage(profiles)
        return {"members": members, "threats": threats}

    def _base_speed(self, name: str, item: str | None = None) -> int | None:
        """Base Speed of the effective form (mega when the matching stone is held)."""
        if item:
            mega = self._mega_for(name, item)
            if mega and (mega.get("base_stats") or {}).get("spe") is not None:
                return mega["base_stats"]["spe"]
        bs = self.dex_by_key.get(to_key(name), {}).get("base_stats") or {}
        spe = bs.get("spe")
        return int(spe) if spe is not None else None

    def _effective_threat(self, threat: PokemonMeta) -> dict[str, Any]:
        """Resolve a meta threat to its effective battle form. When a mega stone
        is among the threat's most-used items, use the mega's types/Speed (e.g.
        Charizard → Charizard-Mega-Y, Fire/Flying). Mega defines these mons, so
        assessing them in base form would understate the threat."""
        types = list(threat.types)
        speed = self._base_speed(threat.name)
        form_name = threat.name
        is_mega = False
        for option in threat.items[:2]:
            form = self.mega_form_lookup.get(to_key(option.name))
            if form and to_key(form.get("base_species", "")) == to_key(threat.name):
                types = list(form.get("types") or types)
                base_stats = form.get("base_stats") or {}
                if base_stats.get("spe") is not None:
                    speed = int(base_stats["spe"])
                form_name = form.get("name") or form_name
                is_mega = True
                break
        return {"types": types, "speed": speed, "form_name": form_name, "is_mega": is_mega}

    def _threat_pressures(
        self,
        threat_types: list[str],
        threat_speed: int | None,
        defender_types: list[str],
        defender_speed: int | None,
    ) -> bool:
        """Type-fallback: do `threat_types` pressure a member with `defender_types`?

        True when the threat has a STAB super-effective vs the member — but NOT
        when the member clearly wins first (outspeeds it AND threatens it back
        with a super-effective STAB). Speed filter only applies when both base
        speeds are known; otherwise it stays conservative (counts the pressure).
        Threat types/Speed are the effective (mega-aware) form."""
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        hits = any(_type_multiplier_dict(t, defender_types, TYPE_CHART) >= 2.0 for t in threat_types if t)
        if not hits:
            return False
        if defender_speed is not None and threat_speed is not None and defender_speed > threat_speed:
            beats_back = any(
                _type_multiplier_dict(t, threat_types, TYPE_CHART) >= 2.0 for t in defender_types if t
            )
            if beats_back:
                return False  # member outspeeds and OHKO-threatens back → not a real counter
        return True

    def _offensive_types(self, member: PokemonSet | None) -> set[str]:
        """Element types of every move on a built set (real coverage, not STAB)."""
        if member is None:
            return set()
        from pokemon_anti_meta_builder.constants import move_type_for
        from pokemon_anti_meta_builder.damage_calc.calculator import get_move_library

        library = get_move_library()
        types: set[str] = set()
        for move in member.moves:
            entry = library.get(move)
            move_type = entry.get("type") if entry else move_type_for(move)
            if move_type:
                types.add(str(move_type).lower())
        return types

    def _team_threat_coverage(self, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Team-wide view (B6+B7 unified): which meta Pokemon pressure the most
        members, and whether the team has a valid answer — via Pokekipe checks, a
        real offensive move that hits super-effectively, or a defensive switch-in.
        Mega- and speed-aware. Diagnostic only: it flags exposure, it does not
        prescribe picks (synergy lives in the recommend/synergy views)."""
        from pokemon_anti_meta_builder.constants import TYPE_CHART

        if not profiles:
            return []
        member_keys = {p["key"] for p in profiles}
        rows: list[dict[str, Any]] = []
        seen_threats: set[str] = set()
        for threat in self.meta:
            tkey = to_key(threat.name)
            if tkey in member_keys or tkey in seen_threats:
                continue
            seen_threats.add(tkey)
            threat_counter_keys = {to_key(o.name) for o in threat.checks_counters}
            eff = self._effective_threat(threat)
            eff_types = eff["types"]

            pressured: list[str] = []
            offensive_answers: list[str] = []
            defensive_answers: list[str] = []
            clean_answers: list[str] = []
            for p in profiles:
                mon = p["meta"]
                pk = tkey in p["counter_keys"] or self._threat_pressures(
                    eff_types, eff["speed"], p["eff_types"], p["speed"]
                )
                if pk:
                    pressured.append(mon.name)
                # Offensive answer: a real move (or STAB fallback) hits SE.
                attack_types = p["offense"] or set(t for t in p["eff_types"] if t)
                hits_se = any(_type_multiplier_dict(t, eff_types, TYPE_CHART) >= 2.0 for t in attack_types)
                # Defensive answer: resists a STAB and is weak to none (switch-in).
                switch_in = _is_switch_in(p["eff_types"], eff_types, TYPE_CHART)
                beats = p["key"] in threat_counter_keys or hits_se or switch_in
                if beats:
                    if hits_se:
                        offensive_answers.append(mon.name)
                    if switch_in:
                        defensive_answers.append(mon.name)
                    if not pk:
                        clean_answers.append(mon.name)
            if not pressured:
                continue
            answers = clean_answers or sorted(set(offensive_answers) | set(defensive_answers))
            if clean_answers:
                status, severity = "covered", "safe"
            elif answers:
                status, severity = "soft", "risky"
            else:
                status, severity = "exposed", "danger"
            rows.append(
                {
                    "name": threat.name,
                    "form": eff["form_name"],
                    "isMega": eff["is_mega"],
                    "usage": threat.usage,
                    "meta_usage": threat.usage,
                    "pressures": pressured,
                    "answers": answers,
                    "offensive": sorted(set(offensive_answers)),
                    "defensive": sorted(set(defensive_answers)),
                    "status": status,
                    "severity": severity,
                    "source": "pokekipe" if threat_counter_keys else "type-based",
                    "summary": _threat_summary(pressured, offensive_answers, defensive_answers, clean_answers, status),
                }
            )
        rows.sort(key=lambda r: (-len(r["pressures"]), -r["meta_usage"]))
        return rows[:20]

    def _effective_types_for(self, mon: PokemonMeta, item: str | None) -> list[str]:
        if item:
            mega = self.mega_form_lookup.get(to_key(item))
            if mega and to_key(mega.get("base_species", "")) == to_key(mon.name):
                return list(mega.get("types") or mon.types)
        return list(mon.types)

    def _mega_for(self, species: str, item: str | None) -> dict[str, Any] | None:
        if not item:
            return None
        mega = self.mega_form_lookup.get(to_key(item))
        if mega and to_key(mega.get("base_species", "")) == to_key(species):
            return mega
        return None

    def _selected_meta(self, selected: list[str]) -> list[PokemonMeta]:
        result = []
        for name in selected:
            mon = self.meta_by_key.get(to_key(name))
            if mon:
                result.append(mon)
        return result


def _synergy_component(
    candidate: PokemonMeta,
    team_weak: dict[str, int],
    missing_roles: set[str],
) -> tuple[float, list[str]]:
    """Normalized (0..1) team-synergy score: defensive type fit + missing roles.

    - Rewards resisting the types the team is *commonly* weak to (>=2 members).
    - Rewards covering core roles the team still lacks.
    - Penalizes adding to a shared weakness (redundant frailty).
    """
    from pokemon_anti_meta_builder.constants import TYPE_CHART

    reasons: list[str] = []
    shared = [atk for atk, count in team_weak.items() if count >= 2]

    def_score = 0.0
    redundancy = 0.0
    if shared:
        resisted = added = 0
        for atk in shared:
            chart = TYPE_CHART.get(atk, {})
            mult = 1.0
            for def_type in candidate.types:
                mult *= chart.get(def_type, 1.0)
            if mult < 1.0:
                resisted += 1
            elif mult >= 2.0:
                added += 1
        def_score = resisted / len(shared)
        redundancy = added / len(shared)
        if resisted:
            reasons.append(f"resiste a {resisted} debolezze condivise del team")

    role_score = 0.0
    if missing_roles:
        covered_roles = set(candidate.roles) & missing_roles
        role_score = len(covered_roles) / len(missing_roles)
        if covered_roles:
            reasons.append("copre ruoli mancanti: " + ", ".join(sorted(covered_roles)))

    synergy = 0.55 * def_score + 0.45 * role_score - 0.30 * redundancy
    return max(0.0, min(1.0, synergy)), reasons


def _team_rule_warnings(team: list[PokemonSet]) -> list[str]:
    warnings: list[str] = []
    items = [member.item for member in team if member.item]
    if len(items) != len(set(items)):
        warnings.append("Item Clause warning: duplicate held item found.")
    mega_items = [item for item in items if _is_mega_stone(item)]
    if len(mega_items) > 1:
        warnings.append("Reg M-A warning: more than one Mega Stone selected.")
    return warnings


# Core roles a balanced VGC team usually wants covered (archetype-agnostic).
_CORE_TEAM_ROLES = ("speed-control", "disruption", "protect-user")

# Weather set by a move (move name -> weather), complements ability setters.
_WEATHER_SETTER_MOVES: dict[str, str] = {
    "sunny day": "sun",
    "rain dance": "rain",
    "sandstorm": "sand",
    "snowscape": "snow",
    "hail": "snow",
    "chilly reception": "snow",
}

# Abilities that gain a speed boost under a given weather (weather abuser).
_WEATHER_SPEED_ABILITIES: dict[str, str] = {
    "chlorophyll": "sun",
    "swift swim": "rain",
    "sand rush": "sand",
    "slush rush": "snow",
}

_WEATHER_LABEL = {"sun": "Sun", "rain": "Rain", "sand": "Sand", "snow": "Snow"}


def _synergy_notes(selected_meta: list[PokemonMeta], team: list[PokemonSet]) -> list[str]:
    """Data-driven team synergy notes: missing roles, active modes (detected from
    real abilities/items/moves, not hardcoded species names), and a defensive
    type profile (shared weaknesses + unresisted threats)."""
    notes: list[str] = []
    if not team:
        return notes

    # (1) Core role shell.
    roles = {role for member in team for role in member.roles}
    missing = [role for role in _CORE_TEAM_ROLES if role not in roles]
    if missing:
        notes.append("Missing core roles: " + ", ".join(missing) + ".")
    else:
        notes.append("Core role shell is complete.")

    # (2) Active modes, detected from the actual sets.
    notes.extend(_mode_notes(team))

    # (3) Defensive type profile: shared weaknesses and unanswered threats.
    notes.extend(_defensive_profile_notes(selected_meta))

    return notes


def _mode_notes(team: list[PokemonSet]) -> list[str]:
    from pokemon_anti_meta_builder.damage_calc.calculator import _WEATHER_SETTER_ABILITIES

    notes: list[str] = []
    weather_setters: dict[str, list[str]] = {}
    speed_abusers: dict[str, list[str]] = {}
    tailwind: list[str] = []
    trick_room: list[str] = []
    intimidate: list[str] = []
    redirection: list[str] = []

    for member in team:
        species = member.species
        ability = (member.ability or "").lower()
        moves = {(mv or "").lower() for mv in member.moves}

        weather = _WEATHER_SETTER_ABILITIES.get(ability)
        if not weather:
            for mv, w in _WEATHER_SETTER_MOVES.items():
                if mv in moves:
                    weather = w
                    break
        if weather:
            weather_setters.setdefault(weather, []).append(species)

        abuse = _WEATHER_SPEED_ABILITIES.get(ability)
        if abuse:
            speed_abusers.setdefault(abuse, []).append(species)

        if "tailwind" in moves:
            tailwind.append(species)
        if "trick room" in moves:
            trick_room.append(species)
        if ability == "intimidate":
            intimidate.append(species)
        if "follow me" in moves or "rage powder" in moves:
            redirection.append(species)

    for weather, setters in weather_setters.items():
        label = _WEATHER_LABEL.get(weather, weather.title())
        note = f"{label} mode active via {', '.join(setters)}."
        abusers = speed_abusers.get(weather)
        if abusers:
            note = note[:-1] + f"; {', '.join(abusers)} abuse it for speed."
        notes.append(note)
    # Speed abusers whose weather isn't being set by the team yet.
    for weather, abusers in speed_abusers.items():
        if weather not in weather_setters:
            label = _WEATHER_LABEL.get(weather, weather.title())
            notes.append(f"{', '.join(abusers)} want {label} but no setter on team.")

    if tailwind:
        notes.append(f"Tailwind speed control via {', '.join(tailwind)}.")
    if trick_room:
        notes.append(f"Trick Room mode via {', '.join(trick_room)}.")
    if len(intimidate) >= 2:
        notes.append(f"Stacked Intimidate pressure ({', '.join(intimidate)}).")
    elif intimidate:
        notes.append(f"Intimidate pivot ({intimidate[0]}).")
    if redirection:
        notes.append(f"Redirection support via {', '.join(redirection)}.")
    return notes


def _defensive_profile_notes(selected_meta: list[PokemonMeta]) -> list[str]:
    """Shared weaknesses (>=2 members weak) and unanswered threats (members weak,
    none resist) computed from team types against the type chart."""
    from pokemon_anti_meta_builder.constants import TYPE_CHART

    if len(selected_meta) < 2:
        return []

    notes: list[str] = []
    unanswered: list[tuple[str, int]] = []
    shared: list[tuple[str, int]] = []
    for attack_type, chart in TYPE_CHART.items():
        weak = 0
        resist = 0
        for mon in selected_meta:
            mult = 1.0
            for def_type in mon.types:
                mult *= chart.get(def_type, 1.0)
            if mult >= 2.0:
                weak += 1
            elif mult <= 0.5:
                resist += 1
        if weak >= 2 and resist == 0:
            unanswered.append((attack_type, weak))
        elif weak >= 2:
            shared.append((attack_type, weak))

    unanswered.sort(key=lambda x: (-x[1], x[0]))
    shared.sort(key=lambda x: (-x[1], x[0]))
    if unanswered:
        parts = ", ".join(f"{t.title()} ({n}× weak, none resist)" for t, n in unanswered)
        notes.append("⚠ Unanswered: " + parts + ".")
    if shared:
        parts = ", ".join(f"{t.title()} ({n})" for t, n in shared[:4])
        notes.append("Shared weakness: " + parts + ".")
    return notes


def _role_counts(team: list[PokemonSet]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for member in team:
        for role in member.roles:
            counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def _would_duplicate_item(candidate: PokemonMeta, selected: list[PokemonMeta]) -> bool:
    item = candidate.items[0].name if candidate.items else ""
    return bool(item and item in {mon.items[0].name for mon in selected if mon.items})


def _would_break_mega_rule(candidate: PokemonMeta, selected: list[PokemonMeta]) -> bool:
    item = candidate.items[0].name if candidate.items else ""
    return _is_mega_stone(item) and any(_is_mega_stone(mon.items[0].name) for mon in selected if mon.items)


def _is_mega_stone(item: str) -> bool:
    return item.endswith("ite") or item in {"Charizardite X", "Charizardite Y"}


def _candidate_covers(candidate: PokemonMeta, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the subset of `targets` (counters of the team) that `candidate` answers.

    A candidate answers a target when:
      - candidate's normalized name is in the target's Pokekipe counter_keys
        (Pokekipe lists candidate as a real check/counter of the threat); OR
      - candidate has STAB super-effective vs the target's types (type fallback,
        used when Pokekipe counter_keys are missing or do not list this mon).
    """
    from pokemon_anti_meta_builder.constants import TYPE_CHART

    candidate_key = to_key(candidate.name)
    covered: list[dict[str, Any]] = []
    for target in targets:
        if candidate_key in target.get("counter_keys", set()):
            covered.append(target)
            continue
        matched = False
        for attack_type in candidate.types:
            chart = TYPE_CHART.get(attack_type, {})
            multiplier = 1.0
            for defend_type in target["types"]:
                multiplier *= chart.get(defend_type, 1.0)
            if multiplier >= 2.0:
                matched = True
                break
        if matched:
            covered.append(target)
    return covered


def _type_multiplier_dict(attacking_type: str, defending_types: list[str], type_chart: dict[str, dict[str, float]]) -> float:
    multiplier = 1.0
    chart = type_chart.get(attacking_type, {})
    for defending_type in defending_types:
        multiplier *= chart.get(defending_type, 1.0)
    return multiplier


def _is_switch_in(defender_types: list[str], attacker_types: list[str], type_chart: dict[str, dict[str, float]]) -> bool:
    """A defensive switch-in resists at least one of the attacker's STABs and is
    weak to none of them."""
    multipliers = [_type_multiplier_dict(t, defender_types, type_chart) for t in attacker_types if t]
    if not multipliers:
        return False
    if any(m > 1.0 for m in multipliers):
        return False
    return any(m < 1.0 for m in multipliers)


def _threat_summary(
    pressured: list[str],
    offensive: list[str],
    defensive: list[str],
    clean: list[str],
    status: str,
) -> str:
    """Human-readable Italian summary for a threat-coverage row (feeds the UI
    cards and the AI coach)."""
    n = len(pressured)
    head = f"Preme {n} membr{'o' if n == 1 else 'i'}" if n else "Non preme il team"
    if status == "covered":
        bits = []
        if [m for m in offensive if m in clean]:
            bits.append(f"colpita da {_join_names([m for m in offensive if m in clean], 2)}")
        if [m for m in defensive if m in clean]:
            bits.append(f"murata da {_join_names([m for m in defensive if m in clean], 2)}")
        if not bits:
            bits.append(f"contrata da {_join_names(clean, 2)}")
        return head + ". Risposta pulita: " + "; ".join(bits) + "."
    if status == "soft":
        answers = sorted(set(offensive) | set(defensive))
        return head + f". Solo risposte sotto pressione: {_join_names(answers, 3)}."
    return head + ". Nessuna risposta nel team."


def _join_names(names: list[str], limit: int) -> str:
    if not names:
        return "—"
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" e altri {len(names) - limit}"


def _render_threat_report(threats: list[dict[str, Any]]) -> str:
    """Plain-text threat report rendered from the unified coverage rows."""
    if not threats:
        return "Aggiungi Pokémon per iniziare l'analisi matchup."
    labels = {"danger": "Scoperte", "risky": "Da tenere d'occhio", "safe": "Coperte"}
    lines: list[str] = ["Threat report"]
    for severity in ("danger", "risky", "safe"):
        section = [t for t in threats if t["severity"] == severity]
        if not section:
            continue
        lines.append("")
        lines.append(f"{labels[severity]}:")
        for t in section:
            label = t.get("form") or t["name"]
            lines.append(f"  - {label} ({t['meta_usage']:.1f}%) — {t['summary']}")
    return "\n".join(lines).strip()


def _stab_super_effective(attacker: PokemonMeta, defender: PokemonMeta, type_chart: dict[str, dict[str, float]]) -> bool:
    for attack_type in attacker.types:
        chart = type_chart.get(attack_type, {})
        multiplier = 1.0
        for defend_type in defender.types:
            multiplier *= chart.get(defend_type, 1.0)
        if multiplier >= 2.0:
            return True
    return False


def _build_mega_form_lookup(mega_forms: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index Mega forms by both required item key and form name key.

    Result entries: {name, base_species, types, base_stats, abilities, item}.
    The lookup is keyed by `to_key(item_name)` so callers can pass any item the
    user picked and immediately find the matching mega form (if any).
    """
    lookup: dict[str, dict[str, Any]] = {}
    for form in mega_forms:
        item = form.get("required_item") or ""
        entry = {
            "name": form.get("name"),
            "base_species": form.get("base_species"),
            "types": [t.lower() for t in (form.get("types") or [])],
            "base_stats": dict(form.get("base_stats") or {}),
            "abilities": list(form.get("abilities") or []),
            "item": item,
        }
        if item:
            lookup[to_key(item)] = entry
        # also key by form name for direct lookup
        if form.get("name"):
            lookup[to_key(form["name"])] = entry
    return lookup


def _apply_overrides(member: PokemonSet, override: dict[str, Any]) -> PokemonSet:
    """Return a copy of `member` with manual overrides applied.

    Recognized keys: item, ability, moves (list[str]), evs (dict), nature.
    Unknown/empty values are ignored so partial overrides work cleanly.
    """
    from dataclasses import replace
    from pokemon_anti_meta_builder.models import EVSpread

    updates: dict[str, Any] = {}
    if override.get("item"):
        updates["item"] = str(override["item"]).strip()
    if override.get("ability"):
        updates["ability"] = str(override["ability"]).strip()
    moves = override.get("moves")
    if isinstance(moves, list) and moves:
        cleaned = [str(m).strip() for m in moves if str(m).strip()]
        if cleaned:
            updates["moves"] = cleaned[:4]
    if override.get("nature"):
        updates["nature"] = str(override["nature"]).strip()
    evs = override.get("evs")
    if isinstance(evs, dict):
        updates["evs"] = EVSpread(
            hp=int(evs.get("hp", member.evs.hp) or 0),
            atk=int(evs.get("atk", member.evs.atk) or 0),
            def_=int(evs.get("def", member.evs.def_) or 0),
            spa=int(evs.get("spa", member.evs.spa) or 0),
            spd=int(evs.get("spd", member.evs.spd) or 0),
            spe=int(evs.get("spe", member.evs.spe) or 0),
        )
    if not updates:
        return member
    return replace(member, **updates)


def _build_off_meta_entries(meta: list[PokemonMeta], dex: list[dict[str, Any]], format_id: str = "") -> list[PokemonMeta]:
    meta_keys = {to_key(mon.name) for mon in meta}
    # Only add dex mons that are actually legal in the format — the Showdown dex
    # carries species (incl. pre-evolutions) that are NOT in Pokemon Champions.
    from pokemon_anti_meta_builder.format_rules.reg_ma import REG_MA_LEGAL_POKEMON, is_reg_ma, _species_key
    legal_keys = {to_key(name) for name in REG_MA_LEGAL_POKEMON} if is_reg_ma(format_id) else None
    entries: list[PokemonMeta] = []
    for raw in dex:
        name = normalize_name(raw.get("name") or "")
        if not name or to_key(name) in meta_keys:
            continue
        if legal_keys is not None and _species_key(name) not in legal_keys:
            continue
        types = [t.lower() for t in raw.get("types") or []]
        abilities = [
            WeightedOption(str(ability).strip(), 0.0)
            for ability in raw.get("abilities") or []
            if str(ability).strip()
        ]
        entries.append(
            PokemonMeta(
                name=name,
                usage=0.0,
                types=types,
                abilities=abilities,
                raw={"source": "showdown_dex", **raw},
            )
        )
    return entries


def _set_to_dict(member: PokemonSet, meta_by_key: dict[str, PokemonMeta] | None = None, mega_lookup: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    types: list[str] = []
    if meta_by_key:
        mon = meta_by_key.get(to_key(member.species))
        if mon:
            types = list(mon.types)
    if mega_lookup and member.item:
        mega = mega_lookup.get(to_key(member.item))
        if mega and to_key(mega.get("base_species", "")) == to_key(member.species):
            types = list(mega.get("types") or types)
    return {
        "species": member.species,
        "item": member.item,
        "ability": member.ability,
        "moves": member.moves,
        "evs": member.evs.as_dict(),
        "nature": member.nature,
        "roles": member.roles,
        "types": types,
        "explanation": member.explanation,
        "warnings": member.warnings,
    }
