"""Find a Spe spread that lets `our_mon` move before `target_mon` in BOTH
Tailwind and Trick Room.

Vincolo:
  - sotto Tailwind (assumo: io ho TW, target no): my_speed * 2 > target_speed
  - sotto Trick Room (TR globale, no TW): my_speed < target_speed

Cioè my_speed deve cadere nel range strettamente aperto
    (target_speed / 2, target_speed).

Itero le nature plausibili (neutrali, +Spe, -Spe) e gli EV Spe in scala
Champions (0-32). Preferisco la nature neutrale quando funziona, altrimenti
quella che minimizza la distanza dal centro del range (più tollerante a
piccoli errori di tuning del target).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pokemon_anti_meta_builder.damage_calc.calculator import Combatant


EV_MAX_PER_STAT = 32

# Neutral, +Spe (-SpA / -Atk), then -Spe (Trick Room) natures, in priority order.
NATURES_ORDER = ("Hardy", "Timid", "Jolly", "Brave", "Quiet", "Sassy", "Relaxed")


@dataclass(frozen=True)
class DualSpeedResult:
    feasible: bool
    nature: str
    spe_ev: int
    spe_iv: int
    our_speed: int
    target_speed: int
    tw_speed: int
    target_half: int
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "nature": self.nature,
            "evs": {"spe": self.spe_ev},
            "ivs": {"spe": self.spe_iv},
            "ourSpeed": self.our_speed,
            "twSpeed": self.tw_speed,
            "targetSpeed": self.target_speed,
            "targetHalf": self.target_half,
            "note": self.note,
        }


def find_dual_speed(
    our_mon: Combatant,
    target_mon: Combatant,
    nature_lock: str | None = None,
) -> DualSpeedResult:
    """Trova lo spread minimo (EV crescenti) che soddisfi entrambi i vincoli.

    Se `nature_lock` è passata (es. nature scelta dall'utente nel team), itera
    solo quella nature, altrimenti scorre tutta `NATURES_ORDER`.

    L'ordine è: EV crescente → nature preferenziali (neutrali prima) → IV 31
    prima di 0. Il primo combo che soddisfa entrambi i vincoli è quello con
    EV minimi, cioè la spread "minima indispensabile".
    """
    target_speed = target_mon.stat("spe")
    if target_speed <= 0:
        return DualSpeedResult(
            feasible=False,
            nature=nature_lock or "Hardy",
            spe_ev=0,
            spe_iv=31,
            our_speed=0,
            target_speed=0,
            tw_speed=0,
            target_half=0,
            note="Velocità del bersaglio non disponibile.",
        )

    half = target_speed // 2
    natures_to_try = (nature_lock,) if nature_lock else NATURES_ORDER

    # Pass 1: smallest EV that satisfies both constraints.
    for ev in range(0, EV_MAX_PER_STAT + 1):
        for nature in natures_to_try:
            for spe_iv in (31, 0):
                ours = _with_spe(our_mon, ev, nature, spe_iv)
                my_speed = ours.stat("spe")
                tw_speed = my_speed * 2
                # TR: my_speed < target_speed; TW: my_speed*2 > target_speed
                if my_speed < target_speed and tw_speed > target_speed:
                    return DualSpeedResult(
                        feasible=True,
                        nature=nature,
                        spe_ev=ev,
                        spe_iv=spe_iv,
                        our_speed=my_speed,
                        target_speed=target_speed,
                        tw_speed=tw_speed,
                        target_half=half,
                    )

    # Pass 2: nothing satisfies both — report the closest attempt (min gap).
    closest = None
    closest_gap = None
    for nature in natures_to_try:
        for spe_iv in (31, 0):
            for ev in range(0, EV_MAX_PER_STAT + 1):
                ours = _with_spe(our_mon, ev, nature, spe_iv)
                my_speed = ours.stat("spe")
                tw_speed = my_speed * 2
                miss = 0
                if my_speed >= target_speed:
                    miss += my_speed - (target_speed - 1)
                if tw_speed <= target_speed:
                    miss += (target_speed + 1) - tw_speed
                if closest is None or miss < (closest_gap or 0):
                    closest = DualSpeedResult(
                        feasible=False,
                        nature=nature,
                        spe_ev=ev,
                        spe_iv=spe_iv,
                        our_speed=my_speed,
                        target_speed=target_speed,
                        tw_speed=tw_speed,
                        target_half=half,
                    )
                    closest_gap = miss

    assert closest is not None
    closest.__dict__["note"] = (
        f"Impossibile soddisfare entrambi i vincoli. Servirebbe Spe in "
        f"({half + 1}, {target_speed - 1}) ma il tuo mon con questa nature/EV/IV "
        f"arriva a {closest.our_speed} Spe."
    )
    return closest


def find_universal_dual_speed(
    our_mon: Combatant,
    meta_targets: list[tuple[str, int]],
    nature_lock: str | None = None,
) -> dict[str, Any]:
    """Find the Spe spread that 'dual-beats' the most meta targets at once.

    `meta_targets` is a list of (species_name, target_spe) tuples — typically
    the top N mons of the meta with their canonical Spe stat already computed.

    A target is "dual-beaten" by my_speed when:
        my_speed < target_spe  (TR: I move first)
      AND my_speed * 2 > target_spe  (TW: I move first)

    We search the (EV, IV, nature) space and return the combo that maximises
    the count of dual-beaten targets. Ties broken by lowest EV cost (so the
    user has stat points free for other roles). Also reports the no-field
    breakdown (who's faster than us without TW/TR) for transparency.
    """
    natures_to_try = (nature_lock,) if nature_lock else NATURES_ORDER
    best_combo = None
    best_payload = None
    for nature in natures_to_try:
        for spe_iv in (31, 0):
            for ev in range(0, EV_MAX_PER_STAT + 1):
                ours = _with_spe(our_mon, ev, nature, spe_iv)
                my_speed = ours.stat("spe")
                covered = []
                not_covered_too_fast = []
                not_covered_too_slow = []
                for name, target_spe in meta_targets:
                    info = {"name": name, "targetSpeed": target_spe}
                    if my_speed < target_spe and my_speed * 2 > target_spe:
                        covered.append(info)
                    elif my_speed >= target_spe:
                        not_covered_too_fast.append(info)
                    else:
                        not_covered_too_slow.append(info)
                count = len(covered)
                key = (-count, ev, -spe_iv, 0 if nature == "Hardy" else 1)
                if best_combo is None or key < best_combo:
                    best_combo = key
                    best_payload = {
                        "feasible": count > 0,
                        "nature": nature,
                        "spe_ev": ev,
                        "spe_iv": spe_iv,
                        "our_speed": my_speed,
                        "covered": covered,
                        "missed_too_fast_for_tr": not_covered_too_fast,
                        "missed_too_slow_for_tw": not_covered_too_slow,
                    }

    assert best_payload is not None
    return best_payload


def _with_spe(base: Combatant, spe_ev: int, nature: str, spe_iv: int) -> Combatant:
    new_evs = dict(base.evs)
    new_evs["spe"] = spe_ev
    new_ivs = dict(base.ivs)
    new_ivs["spe"] = spe_iv
    return Combatant(
        name=base.name,
        level=base.level,
        types=list(base.types),
        base_stats=dict(base.base_stats),
        evs=new_evs,
        ivs=new_ivs,
        nature=nature,
        boosts=dict(base.boosts),
        tera_type=base.tera_type,
        is_burned=base.is_burned,
    )
