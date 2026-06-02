"""Find the minimum Spe EV+nature to outspeed (or tie+1) a target.

Conditions cover the practical VGC cases:
  - tailwind_me / tailwind_opp / tailwind_both / none
  - scarf_me   / scarf_opp
  - paralysis_opp
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any

from pokemon_anti_meta_builder.damage_calc.calculator import Combatant


EV_MAX_PER_STAT = 32

NATURES_PLUS_SPE = ("Hardy", "Timid", "Jolly")  # neutral, +Spe -SpA, +Spe -Atk


@dataclass(frozen=True)
class OutspeedResult:
    feasible: bool
    nature: str
    spe_ev: int
    our_speed: int
    target_speed: int
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "nature": self.nature,
            "evs": {"spe": self.spe_ev},
            "ourSpeed": self.our_speed,
            "targetSpeed": self.target_speed,
            "note": self.note,
        }


def find_min_evs_to_outspeed(
    our_mon: Combatant,
    target_mon: Combatant,
    condition: str = "none",
    our_boost: int = 0,
    target_boost: int = 0,
) -> OutspeedResult:
    """Return the minimum (Spe EVs, nature) that makes us strictly faster.

    our_boost / target_boost are Speed stage changes (-6..+6) applied via the
    combatant boosts, so "+1 Speed" (Dragon Dance, etc.) is modelled correctly.
    """
    tw_me, tw_opp = _tailwind_flags(condition)
    scarf_me = condition == "scarf_me"
    scarf_opp = condition == "scarf_opp"
    paralysis_opp = condition == "paralysis_opp"

    target_mon = _with_spe_boost(target_mon, target_boost)
    # _with_spe (used in the loop below) copies base.boosts, so this boost is retained.
    our_mon = _with_spe_boost(our_mon, our_boost)

    target_speed = _live_speed(target_mon, tailwind=tw_opp, scarf=scarf_opp, paralyzed=paralysis_opp)

    best: OutspeedResult | None = None
    for spe_ev in range(0, EV_MAX_PER_STAT + 1):
        for nature in NATURES_PLUS_SPE:
            ours = _with_spe(our_mon, spe_ev, nature)
            our_speed = _live_speed(ours, tailwind=tw_me, scarf=scarf_me)
            if our_speed > target_speed:
                return OutspeedResult(
                    feasible=True,
                    nature=nature,
                    spe_ev=spe_ev,
                    our_speed=our_speed,
                    target_speed=target_speed,
                )
            if best is None or our_speed > best.our_speed:
                best = OutspeedResult(
                    feasible=False,
                    nature=nature,
                    spe_ev=spe_ev,
                    our_speed=our_speed,
                    target_speed=target_speed,
                )

    assert best is not None
    best.__dict__["note"] = (
        f"Impossibile superare {target_speed} Spe entro {EV_MAX_PER_STAT} EV "
        f"e nature +Spe. Miglior tentativo: {best.our_speed} Spe."
    )
    return best


def _tailwind_flags(condition: str) -> tuple[bool, bool]:
    return {
        "none": (False, False),
        "tailwind_me": (True, False),
        "tailwind_opp": (False, True),
        "tailwind_both": (True, True),
        "scarf_me": (False, False),
        "scarf_opp": (False, False),
        "paralysis_opp": (False, False),
    }.get(condition, (False, False))


def _with_spe(base: Combatant, spe_ev: int, nature: str) -> Combatant:
    new_evs = dict(base.evs)
    new_evs["spe"] = spe_ev
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


def _with_spe_boost(base: Combatant, stage: int) -> Combatant:
    new_boosts = dict(base.boosts)
    new_boosts["spe"] = max(-6, min(6, new_boosts.get("spe", 0) + stage))
    return Combatant(
        name=base.name,
        level=base.level,
        types=list(base.types),
        base_stats=dict(base.base_stats),
        evs=dict(base.evs),
        ivs=dict(base.ivs),
        nature=base.nature,
        boosts=new_boosts,
        tera_type=base.tera_type,
        is_burned=base.is_burned,
    )


def _live_speed(mon: Combatant, tailwind: bool, scarf: bool, paralyzed: bool = False) -> int:
    speed = mon.effective_speed(tailwind=tailwind, paralyzed=paralyzed)
    if scarf:
        speed = floor(speed * 1.5)
    return speed
