"""Spread Maker: build a complete EV spread after Spe is fixed.

Flow:
  1. Detect role (offensive vs defensive) from base stats unless forced.
  2. For offensive role:
     - pump mainstat (Atk or SpA, whichever is higher) up to 32 EVs,
     - report weighted damage % on top-meta targets (2x weight on
       counterables: the mons this Pokémon is supposed to handle),
     - try to use leftover EVs for bulk, but only if the chosen split
       lets the mon survive a 'significant' attack (max roll of the
       most-used STAB from the top-3 meta mons).
  3. For defensive role:
     - compute the minimum bulk to survive each of the top-3 most-used
       STAB attacks in the meta,
     - distribute HP + Def/SpDef to satisfy as many as possible within
       the budget,
     - use leftover EVs on the offensive stat only if it 2HKOs an
       important meta target.

All math uses the existing DamageCalculator (Champions scale 0–32 EVs).
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
EV_MAX_TOTAL = 66


@dataclass
class SpreadMakerResult:
    role: str
    offensive_stat: str          # "atk" or "spa"
    defensive_stat: str          # "def" or "spd" (the bulk leg picked)
    nature: str
    evs: dict[str, int]
    total_used: int
    damage_report: list[dict[str, Any]]    # per-target damage% summary
    bulk_report: list[dict[str, Any]]      # per-threat survive summary
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "offensiveStat": self.offensive_stat,
            "defensiveStat": self.defensive_stat,
            "nature": self.nature,
            "evs": self.evs,
            "totalUsed": self.total_used,
            "damageReport": self.damage_report,
            "bulkReport": self.bulk_report,
            "notes": self.notes,
        }


def detect_role(our_mon: Combatant) -> str:
    """Auto-classify a mon as 'offensive' or 'defensive' from base stats."""
    base = our_mon.base_stats
    off = max(base.get("atk", 0), base.get("spa", 0))
    bulk = base.get("hp", 0) + max(base.get("def", 0), base.get("spd", 0))
    if off >= 105 and off * 2 > bulk:
        return "offensive"
    return "defensive"


def pick_offensive_stat(our_mon: Combatant, our_set_moves: list[str] | None = None) -> str:
    """Decide whether the mon attacks physically or specially.

    If we know the actual moveset, count how many physical vs special damage
    moves it carries — that's far more reliable than guessing from base stats
    (e.g. Mega Charizard Y has high SpA AND Atk, but its set is all special).
    Fall back to base stats only when the moveset is unavailable.
    """
    if our_set_moves:
        phys = sum(1 for m in our_set_moves if MOVE_LIBRARY.get(m, {}).get("category") == "physical")
        spec = sum(1 for m in our_set_moves if MOVE_LIBRARY.get(m, {}).get("category") == "special")
        if spec > phys:
            return "spa"
        if phys > spec:
            return "atk"
    base = our_mon.base_stats
    return "atk" if base.get("atk", 0) >= base.get("spa", 0) else "spa"


def make_spread(
    our_mon: Combatant,
    nature: str,
    fixed_evs: dict[str, int],
    meta_targets: list[tuple[Combatant, list[str]]],
    our_set_moves: list[str],
    counterables: set[str] | None = None,
    role_override: str | None = None,
    weather: str = "",
    ignore_ab_weather: bool = False,
) -> SpreadMakerResult:
    """Allocate the remaining EVs after Spe is fixed.

    Args:
      our_mon: Combatant (base stats, types, ivs already correct)
      nature: pre-chosen nature
      fixed_evs: dict like {"spe": 28} of EVs already committed
      meta_targets: [(target_combatant, [move_names]), ...] — each target
                    carries its full set so we can pick the worst move
                    against us per matchup.
      our_set_moves: our own moveset (Pokékipe-ordered) — we'll pick the
                     highest-damage move from this set per target, not
                     just the highest-BP STAB in the library.
      counterables: optional set of species names this mon should counter
                    (their entries get 2x weight in damage scoring)
      role_override: force 'offensive' or 'defensive' (else autodetected)

    Returns: SpreadMakerResult with full EV spread + reports.
    """
    counterables = counterables or set()
    role = role_override or detect_role(our_mon)
    off_stat = pick_offensive_stat(our_mon, our_set_moves)

    used_so_far = sum(int(v) for v in fixed_evs.values())
    budget = max(0, EV_MAX_TOTAL - used_so_far)
    evs = {k: int(v) for k, v in fixed_evs.items()}
    notes: list[str] = []

    if role == "offensive":
        spread_evs, off_ev, leftover = _allocate_offensive(
            our_mon, evs, budget, off_stat, nature,
            meta_targets=meta_targets, our_set_moves=our_set_moves,
            weather=weather, ignore_ab_weather=ignore_ab_weather,
        )
        evs.update(spread_evs)
        damage_report = _damage_report(
            our_mon, nature, evs, meta_targets, our_set_moves,
            counterables, off_stat, weather, ignore_ab_weather,
        )
        bulk_evs, bulk_report = _try_opportunistic_bulk(
            our_mon, nature, evs, leftover, meta_targets, notes,
            weather, ignore_ab_weather,
        )
        evs.update(bulk_evs)
        defensive_stat = _picked_defensive_stat(bulk_evs)
    else:
        spread_evs, defensive_stat, bulk_report = _allocate_defensive(
            our_mon, evs, budget, meta_targets, nature,
            weather, ignore_ab_weather,
        )
        evs.update(spread_evs)
        leftover = max(0, EV_MAX_TOTAL - sum(evs.values()))
        off_evs, damage_report = _try_opportunistic_offense(
            our_mon, nature, evs, leftover, meta_targets, our_set_moves,
            counterables, off_stat, notes, weather, ignore_ab_weather,
        )
        evs.update(off_evs)

    for stat in ("hp", "atk", "def", "spa", "spd", "spe"):
        evs.setdefault(stat, 0)

    return SpreadMakerResult(
        role=role,
        offensive_stat=off_stat,
        defensive_stat=defensive_stat or "def",
        nature=nature,
        evs=evs,
        total_used=sum(evs.values()),
        damage_report=damage_report,
        bulk_report=bulk_report,
        notes=notes,
    )


# ---------- offensive role ------------------------------------------------

def _allocate_offensive(
    our_mon: Combatant,
    fixed_evs: dict[str, int],
    budget: int,
    off_stat: str,
    nature: str,
    meta_targets: list[tuple[Combatant, list[str]]] | None = None,
    our_set_moves: list[str] | None = None,
    weather: str = "",
    ignore_ab_weather: bool = False,
) -> tuple[dict[str, int], int, int]:
    """Find the MIN EV in `off_stat` that keeps the same KO signature as 32 EV.

    Rationale: putting 32 EV when 16 already gives the same OHKO/2HKO chance on
    every relevant target is wasted — those points should go into bulk. We
    compute the signature (tuple of `ko_chance` per target) at 32 EV, then walk
    from 0 upward and pick the first EV that matches.
    """
    max_ev = min(EV_MAX_PER_STAT, budget)
    if not meta_targets or not our_set_moves:
        return {off_stat: max_ev}, max_ev, budget - max_ev

    calc = DamageCalculator()

    def signature(ev_value: int) -> tuple[str, ...]:
        trial = {**fixed_evs, off_stat: ev_value}
        attacker = _clone_with(our_mon, evs=trial, nature=nature)
        out: list[str] = []
        for target, _ in meta_targets:
            best = _best_move_against(attacker, target, our_set_moves, calc, weather, ignore_ab_weather)
            out.append(best[1].ko_chance if best else "?")
        return tuple(out)

    target_sig = signature(max_ev)
    for ev in range(0, max_ev + 1):
        if signature(ev) == target_sig:
            return {off_stat: ev}, ev, budget - ev
    return {off_stat: max_ev}, max_ev, budget - max_ev


def _damage_report(
    our_mon: Combatant,
    nature: str,
    evs: dict[str, int],
    meta_targets: list[tuple[Combatant, list[str]]],
    our_set_moves: list[str],
    counterables: set[str],
    off_stat: str,
    weather: str = "",
    ignore_ab_weather: bool = False,
) -> list[dict[str, Any]]:
    """Per target, pick the best move from our_set_moves and report damage %."""
    calc = DamageCalculator()
    attacker = _clone_with(our_mon, evs=evs, nature=nature)
    out: list[dict[str, Any]] = []
    for target, _target_moves in meta_targets:
        best = _best_move_against(attacker, target, our_set_moves, calc, weather, ignore_ab_weather)
        if best is None:
            continue
        move_name, result = best
        hp = target.stat("hp") or 1
        out.append({
            "name": target.name,
            "move": move_name,
            "minPct": round(min(result.rolls) / hp * 100, 1),
            "maxPct": round(max(result.rolls) / hp * 100, 1),
            "koChance": result.ko_chance,
            "counterPriority": target.name in counterables,
        })
    out.sort(key=lambda d: (not d["counterPriority"], -d["maxPct"]))
    return out


def _best_move_against(
    attacker: Combatant,
    defender: Combatant,
    moves: list[str],
    calc: DamageCalculator,
    weather: str = "",
    ignore_ab_weather: bool = False,
) -> tuple[str, Any] | None:
    """Return (move_name, CalcResult) for the move in `moves` that deals the
    highest max-roll damage to `defender`. Skips moves not in MOVE_LIBRARY."""
    best: tuple[int, str, Any] | None = None
    for move_name in moves:
        if move_name not in MOVE_LIBRARY:
            continue
        try:
            r = calc.calculate(attacker, defender, move_name, _field(weather, ignore_ab_weather))
        except Exception:  # noqa: BLE001
            continue
        max_dmg = max(r.rolls)
        if best is None or max_dmg > best[0]:
            best = (max_dmg, move_name, r)
    return (best[1], best[2]) if best else None


def _try_opportunistic_bulk(
    our_mon: Combatant,
    nature: str,
    evs_in: dict[str, int],
    leftover: int,
    meta_targets: list[tuple[Combatant, list[str]]],
    notes: list[str],
    weather: str = "",
    ignore_ab_weather: bool = False,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Try to survive the most-significant attack from the top-3 threats.

    For each threat, look at their FULL set and pick whichever move would
    hurt us most (not just whatever happens to be their "top STAB"). Then
    find the cheapest HP+Def/SpDef split that survives the max roll.
    """
    if leftover <= 0:
        return {}, []
    threats = list(meta_targets)
    if not threats:
        notes.append("Avanzati EV non assegnati (nessun threat tracciabile).")
        return {}, []

    best: tuple[int, dict[str, int], dict[str, Any]] | None = None
    calc = DamageCalculator()
    bare_defender = _clone_with(our_mon, evs=evs_in, nature=nature)
    for threat_attacker, threat_moves in threats:
        worst = _best_move_against(threat_attacker, bare_defender, threat_moves, calc, weather, ignore_ab_weather)
        if worst is None:
            continue
        move_name, _ = worst
        move_meta = MOVE_LIBRARY.get(move_name)
        if move_meta is None:
            continue
        category = move_meta["category"]
        def_stat = "def" if category == "physical" else "spd"
        for hp_ev in range(0, min(EV_MAX_PER_STAT, leftover) + 1):
            d_ev = min(EV_MAX_PER_STAT, leftover - hp_ev)
            trial = dict(evs_in)
            trial["hp"] = trial.get("hp", 0) + hp_ev
            trial[def_stat] = trial.get(def_stat, 0) + d_ev
            defender = _clone_with(our_mon, evs=trial, nature=nature)
            try:
                result = calc.calculate(threat_attacker, defender, move_name, _field(weather, ignore_ab_weather))
            except Exception:  # noqa: BLE001
                continue
            if max(result.rolls) < defender.stat("hp"):
                cost = hp_ev + d_ev
                if best is None or cost < best[0]:
                    best = (cost, {"hp": hp_ev, def_stat: d_ev}, {
                        "threat": threat_attacker.name,
                        "move": move_name,
                        "hpEv": hp_ev,
                        "defEv": d_ev,
                        "defStat": def_stat,
                        "survives": True,
                    })
                break

    if best is None:
        notes.append(
            "Avanzati EV non assegnati: nessuna allocazione bulk fa sopravvivere garantito a un threat significativo."
        )
        return {}, []
    _, bulk_evs, report = best
    return bulk_evs, [report]


# ---------- defensive role ------------------------------------------------

def _allocate_defensive(
    our_mon: Combatant,
    fixed_evs: dict[str, int],
    budget: int,
    meta_targets: list[tuple[Combatant, list[str]]],
    nature: str,
    weather: str = "",
    ignore_ab_weather: bool = False,
) -> tuple[dict[str, int], str, list[dict[str, Any]]]:
    """Pump HP + the defensive stat hit hardest by the meta's top STABs.

    Strategy: pick top-3 threats; for each, compute the category-weighted
    average damage; allocate primary bulk on the side that's hit harder.
    Return spread + the bulk report (which threats it survives).
    """
    threats = list(meta_targets)
    if not threats:
        # No threats → just dump in HP.
        ev_hp = min(EV_MAX_PER_STAT, budget)
        return {"hp": ev_hp}, "def", []

    physical_pressure = 0
    special_pressure = 0
    calc = DamageCalculator()
    bare = _clone_with(our_mon, evs={}, nature=nature)
    # Resolve each threat's WORST move against us from its actual moveset.
    resolved_threats: list[tuple[Combatant, str]] = []
    for atk, threat_moves in threats:
        worst = _best_move_against(atk, bare, threat_moves, calc, weather, ignore_ab_weather)
        if worst is None:
            continue
        move_name, r = worst
        meta = MOVE_LIBRARY.get(move_name)
        if meta is None:
            continue
        resolved_threats.append((atk, move_name))
        damage = (min(r.rolls) + max(r.rolls)) / 2
        if meta["category"] == "physical":
            physical_pressure += damage
        else:
            special_pressure += damage
    def_stat = "def" if physical_pressure >= special_pressure else "spd"

    # Iterate the full 3D space HP × Def × SpD. HP boosts both sides of bulk
    # so it's typically the most EV-efficient; this loop discovers that
    # automatically. We also keep separate Def vs SpD allocations so mons
    # facing both physical AND special threats get a proper split.
    bulk_report: list[dict[str, Any]] = []
    best_evs: dict[str, int] = {"hp": 0, "def": 0, "spd": 0}
    best_count = -1
    best_avg_pct = 99999.0
    best_total = 999999
    for hp_ev in range(0, min(EV_MAX_PER_STAT, budget) + 1):
        rem_after_hp = budget - hp_ev
        for d_ev in range(0, min(EV_MAX_PER_STAT, rem_after_hp) + 1):
            rem_after_def = rem_after_hp - d_ev
            for s_ev in range(0, min(EV_MAX_PER_STAT, rem_after_def) + 1):
                total = hp_ev + d_ev + s_ev
                trial = {"hp": hp_ev, "def": d_ev, "spd": s_ev, **fixed_evs}
                defender = _clone_with(our_mon, evs=trial, nature=nature)
                hp_total = defender.stat("hp") or 1
                count = 0
                sum_pct = 0.0
                n = 0
                for atk, move in resolved_threats:
                    try:
                        r = calc.calculate(atk, defender, move, _field(weather, ignore_ab_weather))
                    except Exception:  # noqa: BLE001
                        continue
                    if max(r.rolls) < hp_total:
                        count += 1
                    # Average damage % across threats — captures "how much
                    # damage I'm taking from the majority", not just whether
                    # I lethally die.
                    sum_pct += max(r.rolls) / hp_total * 100
                    n += 1
                avg_pct = sum_pct / n if n else 999.0
                # Scoring (lexicographic):
                #   1) max survivals
                #   2) min avg damage% (bucketed at 1% so near-ties are
                #      treated equal — avoids picking weird splits to shave
                #      0.3%)
                #   3) max HP (it protects BOTH defensive sides equally → if
                #      two splits are within 1% avg damage, prefer the more
                #      versatile HP-heavy one)
                #   4) min total EVs
                key = (-count, round(avg_pct), -hp_ev, total)
                best_key = (-best_count, round(best_avg_pct), -best_evs.get("hp", 0), best_total)
                if key < best_key:
                    best_count = count
                    best_avg_pct = avg_pct
                    best_total = total
                    best_evs = {"hp": hp_ev, "def": d_ev, "spd": s_ev}

    defender = _clone_with(our_mon, evs={**best_evs, **fixed_evs}, nature=nature)
    for atk, move in resolved_threats:
        try:
            r = calc.calculate(atk, defender, move, _field(weather, ignore_ab_weather))
        except Exception:  # noqa: BLE001
            continue
        hp = defender.stat("hp") or 1
        bulk_report.append({
            "threat": atk.name,
            "move": move,
            "minPct": round(min(r.rolls) / hp * 100, 1),
            "maxPct": round(max(r.rolls) / hp * 100, 1),
            "survives": max(r.rolls) < hp,
            "koChance": r.ko_chance,
        })

    # Pick a "primary" defensive leg for reporting (whichever EV ended up higher).
    primary_def = "spd" if best_evs.get("spd", 0) > best_evs.get("def", 0) else "def"
    return best_evs, primary_def, bulk_report


def _try_opportunistic_offense(
    our_mon: Combatant,
    nature: str,
    evs_in: dict[str, int],
    leftover: int,
    meta_targets: list[tuple[Combatant, list[str]]],
    our_set_moves: list[str],
    counterables: set[str],
    off_stat: str,
    notes: list[str],
    weather: str = "",
    ignore_ab_weather: bool = False,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """For defensive role: try the offensive stat only if it 2HKOs a relevant
    target with one of our SET moves (not a library STAB)."""
    if leftover <= 0:
        return {}, []
    if not our_set_moves:
        return {}, []
    calc = DamageCalculator()
    important = [(t, mvs) for (t, mvs) in meta_targets if t.name in counterables] or meta_targets[:5]
    for ev in range(0, min(EV_MAX_PER_STAT, leftover) + 1):
        trial = {**evs_in, off_stat: ev}
        attacker = _clone_with(our_mon, evs=trial, nature=nature)
        for target, _ in important:
            best = _best_move_against(attacker, target, our_set_moves, calc, weather, ignore_ab_weather)
            if best is None:
                continue
            move_name, r = best
            hp = target.stat("hp") or 1
            if 2 * min(r.rolls) >= hp:
                rep = [{
                    "name": target.name,
                    "move": move_name,
                    "minPct": round(min(r.rolls) / hp * 100, 1),
                    "maxPct": round(max(r.rolls) / hp * 100, 1),
                    "koChance": r.ko_chance,
                    "counterPriority": target.name in counterables,
                }]
                return {off_stat: ev}, rep
    notes.append("Nessun EV offensivo allocato: con questo budget non 2HKO niente di rilevante.")
    return {}, []


# ---------- shared helpers ------------------------------------------------

def _pick_our_stab_move(our_mon: Combatant, off_stat: str) -> str | None:
    """Pick a STAB move of the right category that exists in MOVE_LIBRARY."""
    category = "physical" if off_stat == "atk" else "special"
    candidates: list[tuple[int, str]] = []
    for move_name, meta in MOVE_LIBRARY.items():
        if meta.get("category") != category:
            continue
        if meta.get("type") not in our_mon.types:
            continue
        bp = int(meta.get("bp") or 0)
        if bp <= 0:
            continue
        # Skip multi-turn moves
        if move_name in ("Solar Beam",):
            continue
        candidates.append((bp, move_name))
    if not candidates:
        # Fall back to any STAB-less move of the right category
        for move_name, meta in MOVE_LIBRARY.items():
            if meta.get("category") == category and int(meta.get("bp") or 0) >= 70:
                return move_name
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _top_threats(
    meta_targets: list[tuple[Combatant, str]],
    n: int = 3,
) -> list[tuple[Combatant, str]]:
    """First n entries from meta_targets — caller already passed them
    usage-sorted, so this is just a slice."""
    return list(meta_targets[:n])


def _field(weather: str = "", ignore_ab_weather: bool = False) -> Field:
    """Build a Field with the given weather, doubles spread off."""
    return Field(
        weather=weather or "", spread=False,
        ignore_ability_weather=ignore_ab_weather,
    )


def _picked_defensive_stat(bulk_evs: dict[str, int]) -> str:
    if bulk_evs.get("spd", 0) > bulk_evs.get("def", 0):
        return "spd"
    if bulk_evs.get("def", 0) > 0:
        return "def"
    return ""


def _clone_with(base: Combatant, evs: dict[str, int], nature: str) -> Combatant:
    full = {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    for k, v in (evs or {}).items():
        full[k] = int(v)
    return Combatant(
        name=base.name,
        level=base.level,
        types=list(base.types),
        base_stats=dict(base.base_stats),
        evs=full,
        ivs=dict(base.ivs),
        nature=nature,
        boosts=dict(base.boosts),
        tera_type=base.tera_type,
        is_burned=base.is_burned,
        ability=base.ability,
    )
