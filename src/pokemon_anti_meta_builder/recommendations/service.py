from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pokemon_anti_meta_builder.archetypes import Archetype, get_archetype, list_archetypes
from pokemon_anti_meta_builder.data_fetcher import (
    load_meta_file,
    load_showdown_dex,
    load_showdown_learnsets,
    load_showdown_mega_forms,
)
from pokemon_anti_meta_builder.format_rules import filter_legal_meta
from pokemon_anti_meta_builder.meta_parser.normalizer import normalize_name, to_key
from pokemon_anti_meta_builder.models import BuiltTeam, PokemonMeta, PokemonSet, WeightedOption
from pokemon_anti_meta_builder.set_builder import SetBuilder
from pokemon_anti_meta_builder.showdown_exporter import ShowdownExporter
from pokemon_anti_meta_builder.team_builder import TeamBuilder
from pokemon_anti_meta_builder.threat_analyzer import ThreatAnalyzer


@dataclass
class BuilderState:
    format_id: str
    archetype_id: str
    selected: list[str]
    team: list[PokemonSet]
    recommendations: list[dict[str, Any]]
    threat_report: str
    threat_entries: list[dict[str, Any]]
    showdown: str
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
            "archetype": self.archetype_id,
            "selected": self.selected,
            "team": [_set_to_dict(member, meta_lookup, mega_lookup) for member in self.team],
            "recommendations": self.recommendations,
            "threatReport": self.threat_report,
            "threatEntries": list(self.threat_entries),
            "showdown": self.showdown,
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
    ):
        self.input_path = Path(input_path)
        self.format_id = format_id
        meta = load_meta_file(self.input_path)
        self.meta, self.legality_warnings = filter_legal_meta(meta, format_id)
        self.dex = load_showdown_dex(dex_path) if dex_path else []
        self.dex_by_key = {to_key(entry.get("name", "")): entry for entry in self.dex if entry.get("name")}
        self.off_meta = _build_off_meta_entries(self.meta, self.dex)
        self.full_pool: list[PokemonMeta] = list(self.meta) + list(self.off_meta)
        self.meta_by_key = {to_key(mon.name): mon for mon in self.full_pool}
        self.off_meta_keys = {to_key(mon.name) for mon in self.off_meta}
        self.learnsets = load_showdown_learnsets(learnsets_path) if learnsets_path else {}
        self.learnsets_by_key = {to_key(name): moves for name, moves in self.learnsets.items()}
        self.mega_forms = load_showdown_mega_forms(dex_path) if dex_path else []
        self.mega_form_lookup = _build_mega_form_lookup(self.mega_forms)
        self.set_builder = SetBuilder()
        self.team_builder = TeamBuilder()
        self.exporter = ShowdownExporter()

    def catalog(self) -> dict[str, Any]:
        return {
            "format": self.format_id,
            "archetypes": [
                {
                    "id": archetype.id,
                    "name": archetype.name,
                    "summary": archetype.summary,
                    "preferredPokemon": list(archetype.preferred_pokemon),
                    "requiredRoles": list(archetype.required_roles),
                    "countersToCover": list(archetype.counters_to_cover),
                }
                for archetype in list_archetypes()
            ],
            "pokemon": [
                {
                    "name": mon.name,
                    "usage": mon.usage,
                    "winrate": mon.winrate,
                    "types": mon.types,
                    "roles": mon.roles,
                    "topItem": mon.items[0].name if mon.items else "",
                    "offMeta": to_key(mon.name) in self.off_meta_keys,
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
        archetype_id: str = "balance",
        selected: list[str] | None = None,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> BuilderState:
        archetype = get_archetype(archetype_id)
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
        recommendations = self.recommend_next(archetype, selected_meta)
        if team:
            threat_obj = ThreatAnalyzer(mega_form_lookup=self.mega_form_lookup).analyze(team, self.meta, top_n=20)
            threat_report = threat_obj.render()
            threat_entries = [e.as_dict() for e in threat_obj.entries]
            counters_payload = self.team_counters([mon.name for mon in selected_meta], overrides=overrides)
        else:
            threat_report = "Aggiungi Pokémon per iniziare l'analisi matchup."
            threat_entries = []
            counters_payload = {"members": []}
        showdown = self.exporter.export_team(BuiltTeam(self.format_id, team, warnings)) if team else ""
        digest = self.team_digest([mon.name for mon in selected_meta]) if selected_meta else None
        state = BuilderState(
            format_id=self.format_id,
            archetype_id=archetype.id,
            selected=[mon.name for mon in selected_meta],
            team=team,
            recommendations=recommendations,
            threat_report=threat_report,
            threat_entries=threat_entries,
            showdown=showdown,
            roles=_role_counts(team),
            synergy=_synergy_notes(archetype, selected_meta, team),
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
        return self.build_state("balance", selected, overrides=overrides)

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

    def recommend_next(self, archetype: Archetype, selected_meta: list[PokemonMeta], limit: int = 6) -> list[dict[str, Any]]:
        selected_keys = {to_key(mon.name) for mon in selected_meta}
        threats = sorted(self.meta, key=lambda mon: mon.usage, reverse=True)[:12]
        team_counter_targets = self._team_counter_targets(selected_meta)
        scored: list[tuple[float, PokemonMeta, list[str]]] = []
        for candidate in self.meta:
            if to_key(candidate.name) in selected_keys:
                continue
            if _would_break_mega_rule(candidate, selected_meta):
                continue  # Reg M-A: only one Mega Stone per team
            if _would_duplicate_item(candidate, selected_meta):
                continue  # Item Clause: skip duplicates outright
            covered = _candidate_covers(candidate, team_counter_targets)
            cover_score = sum(target["weight"] for target in covered) * 1.6
            base = self.team_builder.score_candidate(candidate, selected_meta, threats)
            base *= 0.25  # de-emphasize general meta score
            bonus, reasons = _archetype_bonus(candidate, archetype)
            score = cover_score + base + bonus
            if covered:
                names = ", ".join(target["name"] for target in covered[:3])
                reasons.insert(0, f"counters team threats: {names}")
            elif team_counter_targets:
                reasons.append("does not address current team counters")
                score -= 6
            scored.append((score, candidate, reasons))
        scored.sort(key=lambda item: (item[0], item[1].usage), reverse=True)
        return [
            {
                "name": mon.name,
                "score": round(score, 2),
                "usage": mon.usage,
                "winrate": mon.winrate,
                "types": mon.types,
                "roles": mon.roles,
                "item": mon.items[0].name if mon.items else "",
                "ability": mon.abilities[0].name if mon.abilities else "",
                "moves": [move.name for move in mon.moves[:4]],
                "reasons": reasons or ["strong general score"],
            }
            for score, mon, reasons in scored[:limit]
        ]

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

        if checks_counters:
            source = "pokekipe"
            entries = []
            for option in checks_counters[:limit]:
                opt_key = to_key(option.name)
                meta_entry = self.meta_by_key.get(opt_key)
                entries.append({
                    "name": option.name,
                    "usage_vs": option.weight,
                    "meta_usage": meta_entry.usage if meta_entry else 0.0,
                    "types": list(meta_entry.types) if meta_entry else [],
                    "offMeta": opt_key in self.off_meta_keys,
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

    def combatant_payload(self, name: str) -> dict[str, Any]:
        """Build a damage-calculator-ready payload for `name`.

        Pulls types/base stats from the Showdown dex slice (when available)
        and EVs/nature/item/ability/moves from the meta-driven SetBuilder
        (or sensible fallbacks for off-meta picks). If the picked item is a
        Mega Stone, swap base stats / types / ability with the Mega form.
        """
        key = to_key(name)
        mon = self.meta_by_key.get(key)
        dex_entry = self.dex_by_key.get(key, {})
        if mon is None and not dex_entry:
            return {"error": f"unknown Pokemon: {name}"}
        if mon is None:
            mon = PokemonMeta(name=normalize_name(name), usage=0.0, types=[t.lower() for t in dex_entry.get("types", [])])
        built = self.set_builder.build_set(mon)

        display_name = built.species
        types = mon.types or [t.lower() for t in dex_entry.get("types", [])]
        base_stats = dex_entry.get("base_stats", {})
        ability = built.ability
        mega = self.mega_form_lookup.get(to_key(built.item)) if built.item else None
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
        for mon in selected_meta:
            override = overrides_by_key.get(to_key(mon.name)) or {}
            effective_types = self._effective_types_for(mon, override.get("item"))
            mega = self._mega_for(mon.name, override.get("item"))
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
                mon_key = to_key(mon.name)
                for threat in sorted(self.meta, key=lambda m: m.usage, reverse=True):
                    threat_key = to_key(threat.name)
                    if threat_key == mon_key or threat_key in seen_threat_keys:
                        continue
                    hits_se = any(_type_multiplier_dict(t, effective_types, TYPE_CHART) >= 2.0 for t in threat.types if t)
                    if hits_se:
                        entries.append(
                            {
                                "name": threat.name,
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
                    "offMeta": to_key(mon.name) in self.off_meta_keys,
                    "source": source,
                    "counters": entries,
                }
            )
        return {"members": members}

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


def _archetype_bonus(candidate: PokemonMeta, archetype: Archetype) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if candidate.name in archetype.preferred_pokemon:
        score += 18
        reasons.append(f"fits {archetype.name} core")
    matching_roles = sorted(set(candidate.roles) & set(archetype.required_roles))
    if matching_roles:
        score += 5 * len(matching_roles)
        reasons.append("covers " + ", ".join(matching_roles))
    moves = {move.name for move in candidate.moves}
    matching_moves = sorted(moves & set(archetype.preferred_moves))
    if matching_moves:
        score += 3 * len(matching_moves)
        reasons.append("brings " + ", ".join(matching_moves[:2]))
    top_item = candidate.items[0].name if candidate.items else ""
    if top_item in archetype.preferred_items:
        score += 8
        reasons.append(f"uses {top_item}")
    return score, reasons


def _team_rule_warnings(team: list[PokemonSet]) -> list[str]:
    warnings: list[str] = []
    items = [member.item for member in team if member.item]
    if len(items) != len(set(items)):
        warnings.append("Item Clause warning: duplicate held item found.")
    mega_items = [item for item in items if _is_mega_stone(item)]
    if len(mega_items) > 1:
        warnings.append("Reg M-A warning: more than one Mega Stone selected.")
    return warnings


def _synergy_notes(archetype: Archetype, selected_meta: list[PokemonMeta], team: list[PokemonSet]) -> list[str]:
    notes: list[str] = []
    names = {mon.name for mon in selected_meta}
    roles = {role for member in team for role in member.roles}
    missing = [role for role in archetype.required_roles if role not in roles]
    if missing:
        notes.append("Missing for archetype: " + ", ".join(missing) + ".")
    else:
        notes.append(f"{archetype.name} role shell is complete.")
    if "Incineroar" in names:
        notes.append("Fake Out + Intimidate pivot gives safer setup turns.")
    if {"Tyranitar", "Excadrill"} <= names:
        notes.append("Sand mode active: Tyranitar enables Excadrill pressure.")
    if "Charizard" in names and any(member.item == "Charizardite Y" for member in team):
        notes.append("Sun mode active through Mega Charizard Y.")
    if "Whimsicott" in names or "Talonflame" in names:
        notes.append("Tailwind mode available.")
    if "Farigiraf" in names or "Hatterene" in names:
        notes.append("Trick Room mode available.")
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


def _build_off_meta_entries(meta: list[PokemonMeta], dex: list[dict[str, Any]]) -> list[PokemonMeta]:
    meta_keys = {to_key(mon.name) for mon in meta}
    entries: list[PokemonMeta] = []
    for raw in dex:
        name = normalize_name(raw.get("name") or "")
        if not name or to_key(name) in meta_keys:
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
