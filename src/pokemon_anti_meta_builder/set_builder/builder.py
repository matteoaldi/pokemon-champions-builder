from __future__ import annotations

import re

from pokemon_anti_meta_builder.constants import DEFAULT_MOVES_BY_TYPE, PROTECT_MOVES
from pokemon_anti_meta_builder.meta_parser.normalizer import to_key
from pokemon_anti_meta_builder.models import EVSpread, PokemonMeta, PokemonSet, WeightedOption


class SetBuilder:
    def build_set(self, mon: PokemonMeta, used_items: set[str] | None = None) -> PokemonSet:
        warnings: list[str] = []
        used_items = used_items or set()
        item = _first_available_item(mon, used_items)
        if not item:
            item = _fallback_item(mon)
            warnings.append(f"{mon.name}: missing item data; used {item}.")

        ability = _top_name(mon.abilities)
        if not ability:
            ability = "Default"
            warnings.append(f"{mon.name}: missing ability data; used Default.")

        moves = [option.name for option in mon.moves[:4]]
        if len(moves) < 4:
            warnings.append(f"{mon.name}: incomplete move data; filled fallback moves.")
            moves = _fill_moves(mon, moves)

        spread_text = _top_name(mon.ev_spreads)
        evs = _parse_evs(spread_text)
        if evs is None:
            evs = _fallback_evs(mon)
            warnings.append(f"{mon.name}: missing EV spread; used a role-based fallback.")

        nature = _top_name(mon.natures)
        if not nature:
            nature = _nature_from_spread(spread_text) or _fallback_nature(mon)
            warnings.append(f"{mon.name}: missing nature; used {nature}.")

        return PokemonSet(
            species=mon.name,
            item=item,
            ability=ability,
            moves=moves[:4],
            evs=evs,
            nature=nature,
            roles=mon.roles or ["flex"],
            explanation=_explain(mon),
            warnings=warnings,
        )


def _top_name(options: list[WeightedOption]) -> str:
    return options[0].name if options else ""


def _first_available_item(mon: PokemonMeta, used_items: set[str]) -> str:
    for option in mon.items:
        if option.name not in used_items:
            return option.name
    return _top_name(mon.items)


def _fallback_item(mon: PokemonMeta) -> str:
    roles = set(mon.roles)
    if "speed-control" in roles or "support" in roles:
        return "Covert Cloak"
    if "physical-attacker" in roles or "special-attacker" in roles:
        return "Focus Sash"
    return "Sitrus Berry"


def _fill_moves(mon: PokemonMeta, moves: list[str]) -> list[str]:
    seen = {to_key(move) for move in moves}
    for type_ in mon.types:
        fallback = DEFAULT_MOVES_BY_TYPE.get(type_)
        if fallback and to_key(fallback) not in seen:
            moves.append(fallback)
            seen.add(to_key(fallback))
    if not (seen & {to_key(move) for move in PROTECT_MOVES}):
        moves.append("Protect")
    for move in ("Helping Hand", "Tera Blast", "Protect"):
        if len(moves) >= 4:
            break
        if to_key(move) not in seen:
            moves.append(move)
            seen.add(to_key(move))
    return moves[:4]


def _parse_evs(text: str) -> EVSpread | None:
    if not text:
        return None
    raw = text.strip()
    if ":" in raw and "/" in raw.split(":", 1)[1]:
        left = raw.split(":", 1)[1].strip()
    else:
        left = raw.split(":", 1)[0].strip()
    values = {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    numeric_parts = [part.strip() for part in left.split("/")]
    if len(numeric_parts) == 6 and all(part.isdigit() for part in numeric_parts):
        hp, atk, def_, spa, spd, spe = [int(part) for part in numeric_parts]
        return EVSpread(hp, atk, def_, spa, spd, spe)
    aliases = {"hp": "hp", "atk": "atk", "def": "def", "spa": "spa", "sp.atk": "spa", "spdef": "spd", "spd": "spd", "spe": "spe", "speed": "spe"}
    for amount, stat in re.findall(r"(\d+)\s*([A-Za-z. ]+)", left):
        key = stat.strip().lower().replace(" ", "")
        mapped = aliases.get(key)
        if mapped:
            values[mapped] = int(amount)
    if not any(values.values()):
        return None
    return EVSpread(values["hp"], values["atk"], values["def"], values["spa"], values["spd"], values["spe"])


def _nature_from_spread(text: str) -> str:
    if ":" not in text:
        return ""
    nature = text.split(":", 1)[0].strip()
    if re.fullmatch(r"[A-Za-z]+", nature):
        return nature[:1].upper() + nature[1:]
    return ""


def _fallback_evs(mon: PokemonMeta) -> EVSpread:
    """Default EV spreads in the Pokemon Champions scale (0-32 per stat)."""
    roles = set(mon.roles)
    if "physical-attacker" in roles:
        return EVSpread(hp=2, atk=32, spe=32)
    if "special-attacker" in roles:
        return EVSpread(hp=2, spa=32, spe=32)
    return EVSpread(hp=32, def_=16, spd=18)


def _fallback_nature(mon: PokemonMeta) -> str:
    roles = set(mon.roles)
    if "physical-attacker" in roles:
        return "Adamant"
    if "special-attacker" in roles:
        return "Modest"
    if "speed-control" in roles:
        return "Timid"
    return "Calm"


def _explain(mon: PokemonMeta) -> str:
    usage = f"{mon.usage:.1f}% usage"
    winrate = f", {mon.winrate:.1f}% winrate" if mon.winrate is not None else ""
    roles = ", ".join(mon.roles or ["flex"])
    return f"{mon.name} covers {roles} with {usage}{winrate} and common meta set data."
