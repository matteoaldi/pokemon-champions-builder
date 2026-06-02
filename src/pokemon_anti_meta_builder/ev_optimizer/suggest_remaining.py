"""Suggest 2-3 sensible ways to spend the EVs left over after a tuning step.

Pure heuristics, no AI. The orchestrator passes the role hint and the EVs
already locked by the tuning result; we return short Italian bullet lines.
"""
from __future__ import annotations

from pokemon_anti_meta_builder.ev_optimizer.survive import EV_MAX_PER_STAT, EV_MAX_TOTAL


def suggest_remaining(used: dict[str, int], role_hint: str, mode: str) -> list[str]:
    """Return up to 3 short Italian suggestions for the remaining EVs.

    `used` is the partial EV dict (Champions scale) the tuning produced.
    `mode` is one of: survive, outspeed, ohko, dualspeed.
    """
    total_used = sum(used.values())
    left = max(0, EV_MAX_TOTAL - total_used)
    if left <= 0:
        return ["Tutti gli EV sono già spesi nel vincolo richiesto."]

    out: list[str] = []
    role = (role_hint or "").lower()

    if mode == "survive":
        # We tuned bulk; suggest offensive completions.
        if "physical" in role:
            out.append(f"Atk {_cap(left, 32)} per non perdere pressione offensiva.")
            out.append(f"Spe {_cap(left, 32)} se vuoi outspeed comuni base 95+.")
        elif "special" in role:
            out.append(f"SpA {_cap(left, 32)} per non perdere pressione offensiva.")
            out.append(f"Spe {_cap(left, 32)} se vuoi outspeed comuni base 95+.")
        else:
            out.append(f"HP {_cap(left, 32)} per più bulk generale.")
            out.append("Spe minimo (4-8) per non essere ultimissimo.")
        out.append("Lascia avanzi su Atk/SpA per pressione, anche se non massimi.")

    elif mode == "outspeed":
        # We tuned Spe; suggest offensive then bulk.
        if "physical" in role:
            out.append(f"Atk {_cap(left, 32)} per massimo danno.")
        elif "special" in role:
            out.append(f"SpA {_cap(left, 32)} per massimo danno.")
        else:
            out.append(f"HP {_cap(left, 32)} per bulk.")
        out.append(f"HP {_cap(left, 32)} se vuoi sopravvivere meglio a ritorsioni.")
        out.append("Split bulk 16/16 HP+SpDef se temi un Hydro Pump in faccia.")

    elif mode == "ohko":
        # We tuned offensive; suggest Spe + bulk.
        out.append(f"Spe {_cap(left, 32)} per outspeed e colpire prima.")
        out.append(f"HP {_cap(left, 32)} per non morire in cambio.")
        out.append("Tieni 8-12 in difesa secondaria se temi priority/spread.")

    elif mode == "dualspeed":
        out.append(f"HP {_cap(left, 32)} per bulk in entrambi gli scenari.")
        if "physical" in role:
            out.append(f"Atk {_cap(left, 32)} per pressione offensiva.")
        elif "special" in role:
            out.append(f"SpA {_cap(left, 32)} per pressione offensiva.")
        else:
            out.append(f"HP {_cap(left, 32)} extra in difensive.")
        out.append("Split bulk 16/16 HP+SpDef o HP+Def per resistere a Tailwind/TR.")

    else:
        out.append(f"Avanzano {left} EV: distribuiscili come preferisci.")

    return out[:3]


def _cap(left: int, single_max: int) -> int:
    return min(left, single_max)
