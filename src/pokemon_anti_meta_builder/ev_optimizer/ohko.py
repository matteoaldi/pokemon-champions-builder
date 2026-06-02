"""Find the minimum Atk/SpA EV+nature to guarantee an OHKO (or 2HKO).

Iterates `our_mon` Atk or SpA in Champions scale (0..32) plus +Atk/+SpA
natures until the move's min damage roll is >= target HP (OHKO) or
2 * min roll >= target HP (2HKO).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pokemon_anti_meta_builder.damage_calc.calculator import (
    Combatant,
    DamageCalculator,
    Field,
    MOVE_LIBRARY,
)


EV_MAX_PER_STAT = 32

NATURES_PHYS = ("Hardy", "Adamant")   # neutral, +Atk -SpA
NATURES_SPEC = ("Hardy", "Modest")    # neutral, +SpA -Atk


@dataclass(frozen=True)
class OhkoResult:
    feasible: bool
    goal: str  # "ohko" or "2hko"
    nature: str
    atk_ev: int
    spa_ev: int
    min_damage: int
    max_damage: int
    hp_target: int
    ko_chance: str
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "goal": self.goal,
            "nature": self.nature,
            "evs": {"atk": self.atk_ev, "spa": self.spa_ev},
            "minDamage": self.min_damage,
            "maxDamage": self.max_damage,
            "hpTarget": self.hp_target,
            "koChance": self.ko_chance,
            "note": self.note,
        }


def find_min_offensive_evs(
    our_mon: Combatant,
    target_mon: Combatant,
    move: str,
    field: Field | None = None,
    goal: str = "ohko",
) -> OhkoResult:
    field = field or Field()
    move_meta = MOVE_LIBRARY.get(move)
    if move_meta is None:
        raise ValueError(f"Unknown move: {move}")
    category = move_meta["category"]
    natures = NATURES_PHYS if category == "physical" else NATURES_SPEC
    calc = DamageCalculator()
    hp_target = target_mon.stat("hp") or 1

    best: OhkoResult | None = None
    for ev in range(0, EV_MAX_PER_STAT + 1):
        for nature in natures:
            ours = _with_offensive(our_mon, ev, category, nature)
            result = calc.calculate(ours, target_mon, move, field)
            min_dmg = min(result.rolls)
            max_dmg = max(result.rolls)
            meets = (min_dmg >= hp_target) if goal == "ohko" else (2 * min_dmg >= hp_target)
            if meets:
                return OhkoResult(
                    feasible=True,
                    goal=goal,
                    nature=nature,
                    atk_ev=ev if category == "physical" else 0,
                    spa_ev=ev if category == "special" else 0,
                    min_damage=min_dmg,
                    max_damage=max_dmg,
                    hp_target=hp_target,
                    ko_chance=result.ko_chance,
                )
            if best is None or min_dmg > best.min_damage:
                best = OhkoResult(
                    feasible=False,
                    goal=goal,
                    nature=nature,
                    atk_ev=ev if category == "physical" else 0,
                    spa_ev=ev if category == "special" else 0,
                    min_damage=min_dmg,
                    max_damage=max_dmg,
                    hp_target=hp_target,
                    ko_chance=result.ko_chance,
                )

    assert best is not None
    best.__dict__["note"] = (
        f"{goal.upper()} non garantito entro {EV_MAX_PER_STAT} EV e nature +offensive. "
        f"Miglior tentativo: {best.min_damage}-{best.max_damage} HP, KO chance {best.ko_chance}."
    )
    return best


def _with_offensive(base: Combatant, ev: int, category: str, nature: str) -> Combatant:
    new_evs = dict(base.evs)
    if category == "physical":
        new_evs["atk"] = ev
        new_evs["spa"] = 0
    else:
        new_evs["spa"] = ev
        new_evs["atk"] = 0
    return Combatant(
        name=base.name,
        level=base.level,
        types=list(base.types),
        base_stats=dict(base.base_stats),
        evs=new_evs,
        ivs=dict(base.ivs),
        nature=nature,
        boosts=dict(base.boosts),
        tera_type=base.tera_type,
        is_burned=base.is_burned,
    )
