from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STAT_ORDER = ("hp", "atk", "def", "spa", "spd", "spe")


@dataclass(frozen=True)
class WeightedOption:
    name: str
    weight: float = 0.0


@dataclass(frozen=True)
class EVSpread:
    hp: int = 0
    atk: int = 0
    def_: int = 0
    spa: int = 0
    spd: int = 0
    spe: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "hp": self.hp,
            "atk": self.atk,
            "def": self.def_,
            "spa": self.spa,
            "spd": self.spd,
            "spe": self.spe,
        }


@dataclass
class PokemonMeta:
    name: str
    usage: float
    winrate: float | None = None
    types: list[str] = field(default_factory=list)
    items: list[WeightedOption] = field(default_factory=list)
    abilities: list[WeightedOption] = field(default_factory=list)
    moves: list[WeightedOption] = field(default_factory=list)
    ev_spreads: list[WeightedOption] = field(default_factory=list)
    natures: list[WeightedOption] = field(default_factory=list)
    teammates: list[WeightedOption] = field(default_factory=list)
    checks_counters: list[WeightedOption] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PokemonSet:
    species: str
    item: str
    ability: str
    moves: list[str]
    evs: EVSpread
    nature: str
    roles: list[str]
    explanation: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class BuiltTeam:
    format_id: str
    members: list[PokemonSet]
    warnings: list[str] = field(default_factory=list)
