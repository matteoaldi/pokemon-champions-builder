"""Top spread + nature lookup for a species, used by the EV Tuner.

Reads from `RecommendationService.meta_by_key` (Pokékipe data) and returns
the top N (nature, evs, usage) tuples already parsed.
"""
from __future__ import annotations

from typing import Any

from pokemon_anti_meta_builder.meta_parser.normalizer import to_key
from pokemon_anti_meta_builder.models import EVSpread, PokemonMeta
from pokemon_anti_meta_builder.set_builder.builder import _nature_from_spread, _parse_evs


def parse_spread_option(raw_name: str, weight: float) -> dict[str, Any] | None:
    """Parse a `WeightedOption` whose name is `Nature:hp/atk/def/spa/spd/spe`.

    Returns a dict {nature, evs, usage} or None if the string is malformed.
    """
    nature = _nature_from_spread(raw_name)
    evs = _parse_evs(raw_name)
    if not nature or evs is None:
        return None
    return {"nature": nature, "evs": evs.as_dict(), "usage": float(weight)}


def top_n_spreads(mon: PokemonMeta, n: int = 3) -> list[dict[str, Any]]:
    """Return the top N parsed spreads for `mon`, by usage."""
    out: list[dict[str, Any]] = []
    for option in mon.ev_spreads:
        parsed = parse_spread_option(option.name, option.weight)
        if parsed:
            out.append(parsed)
        if len(out) >= n:
            break
    return out


def spreads_for_species(meta_by_key: dict[str, PokemonMeta], species: str, n: int = 3) -> list[dict[str, Any]]:
    mon = meta_by_key.get(to_key(species))
    if not mon:
        return []
    return top_n_spreads(mon, n)


def default_target_evs() -> EVSpread:
    """Generic fallback for off-meta targets: balanced offensive Champions spread."""
    return EVSpread(hp=2, atk=32, spe=32)
