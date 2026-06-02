"""Find the minimum EV/nature spread that lets `defender` survive `move` from `attacker`.

Works in Champions scale (0-32 per stat, ~66 total). Uses the same
`DamageCalculator` the rest of the project uses, so results stay aligned
with the lite engine the UI already trusts.

The search space is small:
  - HP EVs:   0..32  (33 options)
  - Def/SpD:  0..32  (33 options, the relevant defensive stat)
  - Natures:  3 options (neutral, +Def or +SpD, never -Def/-SpD)
  -> ~2k combinations, instantaneous.

We iterate by total EVs ascending and return the first feasible spread,
which is by construction the minimum-EV solution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pokemon_anti_meta_builder.damage_calc.calculator import (
    Combatant,
    DamageCalculator,
    Field,
)


EV_MAX_PER_STAT = 32
EV_MAX_TOTAL = 66  # Champions cap (32×6 hardcap soft-limited by game to 66 total)

PHYSICAL_NATURES = ("Hardy", "Impish", "Bold")  # neutral, +Def -SpA, +Def -Atk
SPECIAL_NATURES = ("Hardy", "Careful", "Calm")  # neutral, +SpD -SpA, +SpD -Atk


@dataclass(frozen=True)
class SurviveResult:
    feasible: bool
    nature: str
    hp_ev: int
    def_ev: int
    spd_ev: int
    total_used: int
    survival_pct: float  # % of rolls that the defender survives (100.0 = guaranteed)
    max_damage: int
    hp_after_calc: int
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "nature": self.nature,
            "evs": {"hp": self.hp_ev, "def": self.def_ev, "spd": self.spd_ev},
            "totalUsed": self.total_used,
            "survivalPct": round(self.survival_pct, 1),
            "maxDamage": self.max_damage,
            "hp": self.hp_after_calc,
            "note": self.note,
        }


def find_min_evs_to_survive(
    defender: Combatant,
    attacker: Combatant,
    move: str,
    field: Field | None = None,
    threshold: str = "guaranteed",
) -> SurviveResult:
    """Iterate EV+nature combinations until the defender survives.

    `threshold`:
      - "guaranteed": max damage roll must be < HP (16/16 rolls survive)
      - "high":       at least 15/16 rolls survive
      - "median":     at least 8/16 rolls survive (the 50% line)

    Returns the first spread (lowest total EVs) that meets the threshold,
    or `feasible=False` with the best attempt if no spread can satisfy it.
    """
    field = field or Field()
    calc = DamageCalculator()

    # Pick which defensive stat matters from the move's category.
    from pokemon_anti_meta_builder.damage_calc.calculator import MOVE_LIBRARY

    move_meta = MOVE_LIBRARY.get(move)
    if move_meta is None:
        raise ValueError(f"Unknown move: {move}")
    category = move_meta["category"]
    natures = PHYSICAL_NATURES if category == "physical" else SPECIAL_NATURES
    rolls_required = {"guaranteed": 16, "high": 15, "median": 8}.get(threshold, 16)

    best: SurviveResult | None = None

    candidates = _enumerate_candidates()
    for total, hp_ev, def_ev in candidates:
        for nature in natures:
            d = _clone_defender(defender, hp_ev, def_ev, category, nature)
            result = calc.calculate(attacker, d, move, field)
            hp = d.stat("hp")
            surviving_rolls = sum(1 for r in result.rolls if r < hp)
            if surviving_rolls >= rolls_required:
                spd_ev = def_ev if category == "special" else 0
                def_ev_out = 0 if category == "special" else def_ev
                return SurviveResult(
                    feasible=True,
                    nature=nature,
                    hp_ev=hp_ev,
                    def_ev=def_ev_out,
                    spd_ev=spd_ev,
                    total_used=hp_ev + def_ev,
                    survival_pct=surviving_rolls / 16 * 100,
                    max_damage=max(result.rolls),
                    hp_after_calc=hp,
                )
            # Track the best attempt in case nothing is feasible.
            pct = surviving_rolls / 16 * 100
            if best is None or pct > best.survival_pct:
                spd_ev = def_ev if category == "special" else 0
                def_ev_out = 0 if category == "special" else def_ev
                best = SurviveResult(
                    feasible=False,
                    nature=nature,
                    hp_ev=hp_ev,
                    def_ev=def_ev_out,
                    spd_ev=spd_ev,
                    total_used=hp_ev + def_ev,
                    survival_pct=pct,
                    max_damage=max(result.rolls),
                    hp_after_calc=hp,
                )

    assert best is not None  # candidates is non-empty
    best.__dict__["note"] = (
        f"Sopravvivenza '{threshold}' impossibile entro {EV_MAX_TOTAL} EV totali. "
        f"Miglior tentativo: {best.survival_pct:.0f}% di chance."
    )
    return best


def _clone_defender(base: Combatant, hp_ev: int, def_ev: int, category: str, nature: str) -> Combatant:
    """Build a Combatant identical to `base` but with the trial EV/nature."""
    new_evs = dict(base.evs)
    new_evs["hp"] = hp_ev
    if category == "physical":
        new_evs["def"] = def_ev
        new_evs["spd"] = 0
    else:
        new_evs["spd"] = def_ev
        new_evs["def"] = 0
    # Keep offensive EVs at 0 in the trial — we're only tuning bulk.
    for k in ("atk", "spa", "spe"):
        new_evs.setdefault(k, 0)
        if k not in ("atk", "spa", "spe"):
            new_evs[k] = 0
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


def _enumerate_candidates() -> list[tuple[int, int, int]]:
    """Yield (total, hp_ev, def_ev) sorted by total ascending.

    This guarantees the first feasible candidate is the minimum-EV one.
    """
    out: list[tuple[int, int, int]] = []
    for total in range(0, EV_MAX_TOTAL + 1):
        for hp_ev in range(0, min(total, EV_MAX_PER_STAT) + 1):
            def_ev = total - hp_ev
            if def_ev > EV_MAX_PER_STAT:
                continue
            out.append((total, hp_ev, def_ev))
    return out
