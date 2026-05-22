from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pokemon_anti_meta_builder.constants import DISRUPTION_MOVES, PROTECT_MOVES, SPEED_CONTROL_MOVES, move_category_for
from pokemon_anti_meta_builder.meta_parser.normalizer import normalize_name, normalize_role, normalize_type, to_key
from pokemon_anti_meta_builder.models import PokemonMeta, WeightedOption


class MetaParser:
    """Parse local CSV/JSON meta data into the internal uniform model."""

    def parse_file(self, path: str | Path) -> list[PokemonMeta]:
        source = Path(path)
        if source.suffix.lower() == ".csv":
            with source.open(newline="", encoding="utf-8") as handle:
                return self.parse_rows(csv.DictReader(handle))
        if source.suffix.lower() == ".json":
            with source.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            rows = _json_rows(payload)
            return self.parse_rows(rows)
        raise ValueError(f"Unsupported input extension for {source}")

    def parse_rows(self, rows: Any) -> list[PokemonMeta]:
        parsed: list[PokemonMeta] = []
        for row in rows:
            if not row:
                continue
            mon = self._parse_row(dict(row))
            if mon.name:
                parsed.append(mon)
        return sorted(parsed, key=lambda mon: mon.usage, reverse=True)

    def _parse_row(self, row: dict[str, Any]) -> PokemonMeta:
        name = normalize_name(_first(row, "pokemon", "name", "species"))
        moves = _weighted_options(_first(row, "moves", "moveset", default=""), normalize_name)
        roles = [normalize_role(role.name) for role in _weighted_options(_first(row, "roles", "role", default=""))]
        roles = sorted(set(roles + _infer_roles(moves)))
        return PokemonMeta(
            name=name,
            usage=_percent(_first(row, "usage", "usage_percent", "usage %", default=0)),
            winrate=_optional_percent(_first(row, "winrate", "win_rate", "win %", default=None)),
            types=[normalize_type(t.name) for t in _weighted_options(_first(row, "types", "type", default=""))],
            items=_weighted_options(_first(row, "items", "item", default=""), normalize_name),
            abilities=_weighted_options(_first(row, "abilities", "ability", default=""), normalize_name),
            moves=moves,
            ev_spreads=_weighted_options(_first(row, "ev_spreads", "evs", "ev spread", default="")),
            natures=_weighted_options(_first(row, "natures", "nature", default=""), normalize_name),
            teammates=_weighted_options(_first(row, "teammates", "partners", default=""), normalize_name),
            checks_counters=_weighted_options(
                _first(row, "checks_counters", "checks_and_counters", "checks", "counters", default=""),
                normalize_name,
            ),
            roles=roles,
            raw=row,
        )


def _first(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] not in (None, ""):
            return lowered[key.lower()]
    return default


def _json_rows(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data")
    if isinstance(data, dict):
        rows = []
        for name, stats in data.items():
            if not isinstance(stats, dict):
                continue
            rows.append(
                {
                    "pokemon": stats.get("displayName", name),
                    "usage": stats.get("usage", 0),
                    "items": stats.get("Items", {}),
                    "abilities": stats.get("Abilities", {}),
                    "moves": stats.get("Moves", {}),
                    "ev_spreads": stats.get("Spreads", {}),
                    "natures": stats.get("Natures", {}),
                    "teammates": stats.get("Teammates", {}),
                    "checks_counters": stats.get("Checks and Counters", stats.get("ChecksAndCounters", {})),
                }
            )
        return rows
    return payload.get("pokemon", payload)


def _percent(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) * 100 if 0 < float(value) <= 1 else float(value)
    text = str(value).strip().replace("%", "")
    return float(text) if text else 0.0


def _optional_percent(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _percent(value)


def _weighted_options(value: Any, normalizer=lambda x: str(x).strip()) -> list[WeightedOption]:
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        return _sort_options([WeightedOption(str(normalizer(k)), _percent(v)) for k, v in value.items()])
    if isinstance(value, list):
        options = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("value") or item.get("move") or item.get("item")
                weight = item.get("weight", item.get("usage", item.get("percent", 0)))
                if name:
                    options.append(WeightedOption(str(normalizer(name)), _percent(weight)))
            else:
                options.append(_parse_option(str(item), normalizer))
        return _sort_options(options)
    text = str(value)
    separators = [";", "|"]
    for sep in separators:
        if sep in text:
            return _sort_options([_parse_option(part, normalizer) for part in text.split(sep) if part.strip()])
    if "," in text and ":" not in text:
        return _sort_options([WeightedOption(str(normalizer(part)), 0.0) for part in text.split(",") if part.strip()])
    return _sort_options([_parse_option(text, normalizer)])


def _parse_option(text: str, normalizer) -> WeightedOption:
    chunk = text.strip()
    if not chunk:
        return WeightedOption("", 0.0)
    for sep in (":", "="):
        if sep in chunk:
            name, weight = chunk.rsplit(sep, 1)
            try:
                return WeightedOption(str(normalizer(name.strip())), _percent(weight.strip()))
            except ValueError:
                return WeightedOption(str(normalizer(chunk)), 0.0)
    return WeightedOption(str(normalizer(chunk)), 0.0)


def _sort_options(options: list[WeightedOption]) -> list[WeightedOption]:
    clean = [option for option in options if option.name]
    return sorted(clean, key=lambda option: option.weight, reverse=True)


def _infer_roles(moves: list[WeightedOption]) -> list[str]:
    keys = {to_key(move.name) for move in moves}
    pretty = {move.name.lower() for move in moves}
    roles: set[str] = set()
    if keys & {to_key(move) for move in SPEED_CONTROL_MOVES}:
        roles.add("speed-control")
    if keys & {to_key(move) for move in DISRUPTION_MOVES}:
        roles.add("disruption")
    if keys & {to_key(move) for move in PROTECT_MOVES}:
        roles.add("protect-user")
    physical = sum(1 for move in pretty if move_category_for(move) == "physical")
    special = sum(1 for move in pretty if move_category_for(move) == "special")
    if physical > special:
        roles.add("physical-attacker")
    elif special > physical:
        roles.add("special-attacker")
    return list(roles)
