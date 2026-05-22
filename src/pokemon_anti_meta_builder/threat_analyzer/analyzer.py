from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pokemon_anti_meta_builder.constants import TYPE_CHART, move_type_for
from pokemon_anti_meta_builder.meta_parser.normalizer import to_key
from pokemon_anti_meta_builder.models import PokemonMeta, PokemonSet


@dataclass
class ThreatEntry:
    name: str
    usage: float
    severity: str  # "danger" | "risky" | "safe"
    summary: str
    source: str  # "pokekipe" | "type-based"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "usage": self.usage,
            "severity": self.severity,
            "summary": self.summary,
            "source": self.source,
        }


@dataclass
class ThreatReport:
    entries: list[ThreatEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    used_pokekipe_data: bool = False
    threats_with_real_data: int = 0
    threats_with_fallback: int = 0

    # legacy string buckets kept for backward compat with older tests
    @property
    def strong_into(self) -> list[str]:
        return [e.summary for e in self.entries if e.severity == "safe"]

    @property
    def weak_into(self) -> list[str]:
        return [e.summary for e in self.entries if e.severity == "danger"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.as_dict() for e in self.entries],
            "notes": list(self.notes),
            "usedPokekipeData": self.used_pokekipe_data,
            "threatsWithRealData": self.threats_with_real_data,
            "threatsWithFallback": self.threats_with_fallback,
        }

    def render(self) -> str:
        lines: list[str] = ["Threat report"]
        if self.used_pokekipe_data and self.threats_with_real_data > 0:
            # Only mention the source mix when we actually have Pokekipe entries;
            # otherwise it's noise (every threat would be tagged "fallback").
            lines.append(
                f"Fonte: Pokekipe per {self.threats_with_real_data} minaccia/e, "
                f"stima per {self.threats_with_fallback}."
            )
        lines.append("")
        labels = {"danger": "Pericolose", "risky": "Da tenere d'occhio", "safe": "Coperte"}
        for severity in ("danger", "risky", "safe"):
            section = [e for e in self.entries if e.severity == severity]
            if not section:
                continue
            lines.append(f"{labels[severity]}:")
            lines.extend(f"  - {e.name} ({e.usage:.1f}%) — {e.summary}" for e in section)
            lines.append("")
        if self.notes:
            lines.append("Note:")
            lines.extend(f"  - {note}" for note in self.notes)
        return "\n".join(lines).strip()


class ThreatAnalyzer:
    def __init__(self, mega_form_lookup: dict[str, dict[str, Any]] | None = None):
        # mega_form_lookup maps a normalized item key → {"types": [...], "name": str}
        self.mega_form_lookup = mega_form_lookup or {}

    def analyze(self, team: list[PokemonSet], meta: list[PokemonMeta], top_n: int = 10) -> ThreatReport:
        meta_by_name = {mon.name: mon for mon in meta}
        threats = sorted(meta, key=lambda mon: mon.usage, reverse=True)[:top_n]
        report = ThreatReport()
        team_keys = {to_key(member.species) for member in team}

        # Per team member: effective types (mega-aware) and offensive types from moves
        effective_team: list[dict[str, Any]] = []
        for member in team:
            base_meta = meta_by_name.get(member.species)
            types = self._effective_types(member, base_meta)
            offense = self._offensive_types(member)
            effective_team.append({"species": member.species, "types": types, "offense": offense})

        for threat in threats:
            real_checks = {to_key(option.name) for option in threat.checks_counters if option.name}
            relevant = [m for m in effective_team if to_key(m["species"]) != to_key(threat.name)]
            real_team_answers = sorted({m["species"] for m in relevant if to_key(m["species"]) in real_checks})

            offensive = sorted({m["species"] for m in relevant if self._hits_se(m["offense"], threat.types)})
            defensive = sorted({m["species"] for m in relevant if self._is_switch_in(m["types"], threat.types)})
            weak = sorted({m["species"] for m in relevant if self._is_weak(m["types"], threat.types)})

            if real_checks:
                report.threats_with_real_data += 1
                report.used_pokekipe_data = True
                if real_team_answers:
                    severity = "safe"
                    summary = f"Pokékipe la considera contrata da {_join(real_team_answers, 3)}."
                else:
                    severity = "danger"
                    suggestions = [opt.name for opt in threat.checks_counters if to_key(opt.name) not in team_keys][:3]
                    suffix = f" Considera: {', '.join(suggestions)}." if suggestions else ""
                    summary = f"Nessun tuo Pokémon è nei suoi check/counter ufficiali.{suffix}"
                source = "pokekipe"
            else:
                report.threats_with_fallback += 1
                source = "type-based"
                severity, summary = self._classify_type_based(threat, offensive, defensive, weak)

            report.entries.append(ThreatEntry(
                name=threat.name,
                usage=threat.usage,
                severity=severity,
                summary=summary,
                source=source,
            ))

        # Order: dangers first, then risky, then safe
        order_key = {"danger": 0, "risky": 1, "safe": 2}
        report.entries.sort(key=lambda e: (order_key.get(e.severity, 9), -e.usage))
        return report

    def _effective_types(self, member: PokemonSet, base_meta: PokemonMeta | None) -> list[str]:
        item_key = to_key(member.item) if member.item else ""
        mega = self.mega_form_lookup.get(item_key) if item_key else None
        if mega and mega.get("base_species") and to_key(mega["base_species"]) == to_key(member.species):
            return [str(t).lower() for t in mega.get("types", [])]
        if base_meta and base_meta.types:
            return list(base_meta.types)
        return []

    def _offensive_types(self, member: PokemonSet) -> set[str]:
        """Resolve every move on the set to its element type using the full move library."""
        # Lazy import to avoid module-level cycle
        from pokemon_anti_meta_builder.damage_calc.calculator import get_move_library
        library = get_move_library()
        types: set[str] = set()
        for move in member.moves:
            entry = library.get(move)
            if entry:
                move_type = entry.get("type")
                if move_type:
                    types.add(str(move_type).lower())
                continue
            fallback = move_type_for(move)
            if fallback:
                types.add(fallback)
        return types

    def _hits_se(self, offense: set[str], threat_types: list[str]) -> bool:
        for attack_type in offense:
            if _type_multiplier(attack_type, threat_types) >= 2.0:
                return True
        return False

    def _is_switch_in(self, defender_types: list[str], threat_types: list[str]) -> bool:
        """A switch-in is not weak to any STAB AND resists at least one STAB."""
        multipliers = [_type_multiplier(t, defender_types) for t in threat_types if t]
        if not multipliers:
            return False
        if any(m > 1.0 for m in multipliers):
            return False
        return any(m < 1.0 for m in multipliers)

    def _is_weak(self, defender_types: list[str], threat_types: list[str]) -> bool:
        return any(_type_multiplier(t, defender_types) >= 2.0 for t in threat_types if t)

    def _classify_type_based(
        self,
        threat: PokemonMeta,
        offensive: list[str],
        defensive: list[str],
        weak: list[str],
    ) -> tuple[str, str]:
        if defensive and offensive:
            return (
                "safe",
                f"colpita da {_join(offensive, 2)}, gestita da {_join(defensive, 2)}.",
            )
        if defensive and not offensive:
            return (
                "risky",
                f"{_join(defensive, 2)} resiste alle sue STAB ma nessuno la colpisce 2x.",
            )
        if offensive and not defensive:
            return (
                "risky",
                f"{_join(offensive, 2)} la colpiscono 2x, ma nessun tuo Pokémon resiste alle sue STAB.",
            )
        if weak:
            return (
                "danger",
                f"nessuna risposta: {len(weak)} membri prendono 2x dalle sue STAB.",
            )
        return ("danger", "nessuna risposta chiara né offensiva né difensiva.")


def _join(names: list[str], limit: int) -> str:
    if not names:
        return "—"
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" e altri {len(names) - limit}"


def _type_multiplier(attacking_type: str, defending_types: list[str]) -> float:
    multiplier = 1.0
    chart = TYPE_CHART.get(attacking_type, {})
    for defending_type in defending_types:
        multiplier *= chart.get(defending_type, 1.0)
    return multiplier
