from __future__ import annotations

from pokemon_anti_meta_builder.models import BuiltTeam, EVSpread, PokemonSet


class ShowdownExporter:
    def export_team(self, team: BuiltTeam | list[PokemonSet]) -> str:
        members = team.members if isinstance(team, BuiltTeam) else team
        return "\n\n".join(self.export_set(member) for member in members)

    def export_set(self, member: PokemonSet) -> str:
        lines = [
            f"{member.species} @ {member.item}",
            f"Ability: {member.ability}",
            f"EVs: {_format_evs(member.evs)}",
            f"{member.nature} Nature",
        ]
        lines.extend(f"- {move}" for move in member.moves[:4])
        return "\n".join(lines)


def _format_evs(evs: EVSpread) -> str:
    """Render EVs in Showdown-compatible 0-252 scale.

    Internal storage uses the Pokemon Champions scale (0-32 per stat). We
    convert by multiplying by 8 and capping at 252 so the exported team can
    be loaded into standard Showdown teambuilders/calculators.
    """
    labels = [("hp", "HP"), ("atk", "Atk"), ("def", "Def"), ("spa", "SpA"), ("spd", "SpD"), ("spe", "Spe")]
    parts = []
    values = evs.as_dict()
    for key, label in labels:
        value = values[key]
        if not value:
            continue
        if value <= 32:
            # Treat as Champions scale; convert to 0-252 standard
            scaled = min(252, value * 8)
        else:
            scaled = min(252, value)
        parts.append(f"{scaled} {label}")
    return " / ".join(parts) if parts else "0 HP"
