from __future__ import annotations

from dataclasses import dataclass

from pokemon_anti_meta_builder.models import EVSpread, PokemonSet


@dataclass(frozen=True)
class EVGoal:
    kind: str
    source: str
    target: str
    detail: str


class EVOptimizer:
    """Placeholder interface for future real damage/speed benchmarks."""

    def optimize(self, pokemon_set: PokemonSet, goals: list[EVGoal] | None = None) -> tuple[PokemonSet, list[str]]:
        notes = [
            "EV optimizer placeholder: kept common/fallback spread unchanged.",
            "Future goals can target survive attack X, outspeed Pokemon Z, or OHKO/2HKO benchmarks.",
        ]
        if goals:
            notes.append(f"Received {len(goals)} goals but real optimization is not implemented yet.")
        return pokemon_set, notes

    def default_spread(self) -> EVSpread:
        return EVSpread(hp=252, def_=124, spd=132)
