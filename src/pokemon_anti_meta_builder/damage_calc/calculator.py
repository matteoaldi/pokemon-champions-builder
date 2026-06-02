"""Generation 9 single-target damage calculator (lite).

Implements the standard formula from Bulbapedia / Smogon:
  damage = floor((((2*L/5)+2) * BP * A / D) / 50 + 2)
  damage *= STAB * type * crit * burn * weather * terrain * screens * spread * random
  random is a uniform integer in [85..100] inclusive (the 16 rolls).

This is intentionally a subset: no abilities, no items, no status beyond
burn, no Tera. It exists to give the UI a working calc even before the
JS bundle of @smogon/calc is wired in. The JS side, when present,
overrides the result by calling @smogon/calc client-side.

The move library is loaded dynamically from `data/raw/showdown_moves.json`
(produced by `sync-moves`) when present; otherwise the small hardcoded
`_BUILTIN_MOVE_LIBRARY` is used as fallback.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from math import floor
from pathlib import Path
from typing import Any

from pokemon_anti_meta_builder.constants import TYPE_CHART


NATURE_MODIFIERS: dict[str, dict[str, float]] = {
    "Adamant": {"atk": 1.1, "spa": 0.9},
    "Modest": {"spa": 1.1, "atk": 0.9},
    "Jolly": {"spe": 1.1, "spa": 0.9},
    "Timid": {"spe": 1.1, "atk": 0.9},
    "Bold": {"def": 1.1, "atk": 0.9},
    "Impish": {"def": 1.1, "spa": 0.9},
    "Calm": {"spd": 1.1, "atk": 0.9},
    "Careful": {"spd": 1.1, "spa": 0.9},
    "Naive": {"spe": 1.1, "spd": 0.9},
    "Hasty": {"spe": 1.1, "def": 0.9},
    "Brave": {"atk": 1.1, "spe": 0.9},
    "Quiet": {"spa": 1.1, "spe": 0.9},
    "Relaxed": {"def": 1.1, "spe": 0.9},
    "Sassy": {"spd": 1.1, "spe": 0.9},
    "Mild": {"spa": 1.1, "def": 0.9},
    "Lonely": {"atk": 1.1, "def": 0.9},
    "Naughty": {"atk": 1.1, "spd": 0.9},
    "Rash": {"spa": 1.1, "spd": 0.9},
    "Gentle": {"spd": 1.1, "def": 0.9},
    "Hardy": {},
    "Serious": {},
    "Docile": {},
    "Bashful": {},
    "Quirky": {},
}


# Special-behaviour overrides: moves whose mechanics need a custom flag
# beyond what we can derive from Showdown's raw JSON.
_MOVE_OVERRIDES: dict[str, dict[str, Any]] = {
    "Body Press": {"uses_defense_as_attack": True},
    "Foul Play": {"uses_target_attack": True},
}


# Fallback hardcoded library. Used when data/raw/showdown_moves.json is not
# present. Powers are the standard gen 9 BP. Spread=true means the move
# targets multiple Pokemon in doubles and gets the 0.75x spread mod.
_BUILTIN_MOVE_LIBRARY: dict[str, dict[str, Any]] = {
    "Earthquake":        {"type": "ground",   "category": "physical", "bp": 100, "spread": True},
    "Rock Slide":        {"type": "rock",     "category": "physical", "bp":  75, "spread": True},
    "Dragon Claw":       {"type": "dragon",   "category": "physical", "bp":  80},
    "Close Combat":      {"type": "fighting", "category": "physical", "bp": 120},
    "Flare Blitz":       {"type": "fire",     "category": "physical", "bp": 120},
    "Wave Crash":        {"type": "water",    "category": "physical", "bp": 120},
    "Liquidation":       {"type": "water",    "category": "physical", "bp":  85},
    "Iron Head":         {"type": "steel",    "category": "physical", "bp":  80},
    "Last Respects":     {"type": "ghost",    "category": "physical", "bp":  50},
    "Aqua Jet":          {"type": "water",    "category": "physical", "bp":  40, "priority": 1},
    "Sucker Punch":      {"type": "dark",     "category": "physical", "bp":  70, "priority": 1},
    "Fake Out":          {"type": "normal",   "category": "physical", "bp":  40, "priority": 3},
    "Knock Off":         {"type": "dark",     "category": "physical", "bp":  65},
    "Throat Chop":       {"type": "dark",     "category": "physical", "bp":  80},
    "Kowtow Cleave":     {"type": "dark",     "category": "physical", "bp":  85},
    "Dire Claw":         {"type": "poison",   "category": "physical", "bp":  80},
    "Heat Wave":         {"type": "fire",     "category": "special",  "bp":  95, "spread": True},
    "Hurricane":         {"type": "flying",   "category": "special",  "bp": 110},
    "Hyper Voice":       {"type": "normal",   "category": "special",  "bp":  90, "spread": True},
    "Moonblast":         {"type": "fairy",    "category": "special",  "bp":  95},
    "Dazzling Gleam":    {"type": "fairy",    "category": "special",  "bp":  80, "spread": True},
    "Shadow Ball":       {"type": "ghost",    "category": "special",  "bp":  80},
    "Sludge Bomb":       {"type": "poison",   "category": "special",  "bp":  90},
    "Draco Meteor":      {"type": "dragon",   "category": "special",  "bp": 130},
    "Earth Power":       {"type": "ground",   "category": "special",  "bp":  90},
    "Ice Beam":          {"type": "ice",      "category": "special",  "bp":  90},
    "Icy Wind":          {"type": "ice",      "category": "special",  "bp":  55, "spread": True},
    "Thunderbolt":       {"type": "electric", "category": "special",  "bp":  90},
    "Electro Shot":      {"type": "electric", "category": "special",  "bp": 130},
    "Flash Cannon":      {"type": "steel",    "category": "special",  "bp":  80},
    "Sparkling Aria":    {"type": "water",    "category": "special",  "bp":  90, "spread": True},
    "Solar Beam":        {"type": "grass",    "category": "special",  "bp": 120},
    "Air Slash":         {"type": "flying",   "category": "special",  "bp":  75},
    "Body Press":        {"type": "fighting", "category": "physical", "bp":  80},
    "Brave Bird":        {"type": "flying",   "category": "physical", "bp": 120},
    "Foul Play":         {"type": "dark",     "category": "physical", "bp":  95},
    "Weather Ball":      {"type": "normal",   "category": "special",  "bp":  50},
    "Tera Blast":        {"type": "normal",   "category": "special",  "bp":  80},
    "Power Gem":         {"type": "rock",     "category": "special",  "bp":  80},
    "Mortal Spin":       {"type": "poison",   "category": "physical", "bp":  30},
}


DEFAULT_MOVES_JSON = Path("data/raw/showdown_moves.json")

_RUNTIME_MOVE_LIBRARY: dict[str, dict[str, Any]] | None = None


def load_move_library(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Build the full move library used by the calculator.

    Priority:
      1. Showdown JSON at `path` (default data/raw/showdown_moves.json) if it
         exists — gives full coverage with metadata (type, category, bp,
         accuracy, priority, target, spread, flags, secondary).
      2. `_BUILTIN_MOVE_LIBRARY` hardcoded fallback.

    Custom mechanics overrides in `_MOVE_OVERRIDES` (e.g. Body Press uses
    defense as attack) are merged on top in either case.
    """
    source = Path(path) if path is not None else DEFAULT_MOVES_JSON
    library: dict[str, dict[str, Any]] = {}
    if source.exists():
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - malformed JSON falls back to builtin
            payload = {}
        moves_raw = (payload.get("moves") if isinstance(payload, dict) else None) or {}
        for name, raw in moves_raw.items():
            if not isinstance(raw, dict):
                continue
            if raw.get("category") not in ("physical", "special"):
                # status moves are not directly usable by the lite calculator
                continue
            if not int(raw.get("bp") or 0):
                continue
            library[name] = {
                "type": raw.get("type", "normal"),
                "category": raw.get("category", "physical"),
                "bp": int(raw.get("bp") or 0),
                "spread": bool(raw.get("spread")),
                "priority": int(raw.get("priority") or 0),
                "accuracy": raw.get("accuracy", True),
                "target": raw.get("target", "normal"),
                "flags": dict(raw.get("flags") or {}),
                "secondary": raw.get("secondary"),
            }
    if not library:
        library = {name: dict(meta) for name, meta in _BUILTIN_MOVE_LIBRARY.items()}
    for name, override in _MOVE_OVERRIDES.items():
        if name in library:
            library[name] = {**library[name], **override}
    return library


def get_move_library() -> dict[str, dict[str, Any]]:
    """Cached accessor; reset_move_library() forces a reload."""
    global _RUNTIME_MOVE_LIBRARY
    if _RUNTIME_MOVE_LIBRARY is None:
        _RUNTIME_MOVE_LIBRARY = load_move_library()
    return _RUNTIME_MOVE_LIBRARY


def reset_move_library() -> None:
    global _RUNTIME_MOVE_LIBRARY
    _RUNTIME_MOVE_LIBRARY = None


# Public alias kept for backward compatibility; resolved lazily on first
# attribute access through a thin wrapper that always reflects the current
# loaded JSON.
class _MoveLibraryProxy:
    def __getitem__(self, key: str) -> dict[str, Any]:
        return get_move_library()[key]

    def __contains__(self, key: object) -> bool:
        return key in get_move_library()

    def __iter__(self):
        return iter(get_move_library())

    def __len__(self) -> int:
        return len(get_move_library())

    def get(self, key: str, default: Any = None) -> Any:
        return get_move_library().get(key, default)

    def keys(self):
        return get_move_library().keys()

    def items(self):
        return get_move_library().items()

    def values(self):
        return get_move_library().values()


MOVE_LIBRARY = _MoveLibraryProxy()


@dataclass
class Combatant:
    name: str
    level: int = 50
    types: list[str] = field(default_factory=list)
    base_stats: dict[str, int] = field(default_factory=dict)
    evs: dict[str, int] = field(default_factory=lambda: {k: 0 for k in ("hp", "atk", "def", "spa", "spd", "spe")})
    ivs: dict[str, int] = field(default_factory=lambda: {k: 31 for k in ("hp", "atk", "def", "spa", "spd", "spe")})
    nature: str = "Hardy"
    boosts: dict[str, int] = field(default_factory=lambda: {k: 0 for k in ("atk", "def", "spa", "spd", "spe")})
    tera_type: str | None = None
    is_burned: bool = False
    ability: str = ""

    def stat(self, key: str) -> int:
        """Compute the live stat using the Pokemon Champions EV scale (0-32).

        Champions caps EVs at 32 per stat (≈ 66 total). Compared with the gen 9
        standard 252-cap formula, 32 Champion EVs match what 252 standard EVs
        would do, so the formula becomes `2 * champion_ev` where the standard
        formula uses `floor(ev/4)`.
        """
        base = self.base_stats.get(key, 0)
        if not base:
            return 0
        iv = self.ivs.get(key, 31)
        ev = self.evs.get(key, 0)
        ev_term = ev * 2  # Champions scale (0-32) → equivalent of floor(252/4)
        if key == "hp":
            return floor(((2 * base + iv + ev_term) * self.level) / 100) + self.level + 10
        raw = floor(((2 * base + iv + ev_term) * self.level) / 100) + 5
        modifier = NATURE_MODIFIERS.get(self.nature, {}).get(key, 1.0)
        return floor(raw * modifier)

    def stats_breakdown(self) -> dict[str, int]:
        return {key: self.stat(key) for key in ("hp", "atk", "def", "spa", "spd", "spe")}

    def effective_speed(self, tailwind: bool = False, paralyzed: bool = False) -> int:
        speed = _boosted(self.stat("spe"), self.boosts.get("spe", 0))
        if tailwind:
            speed *= 2
        if paralyzed:
            speed = floor(speed * 0.5)
        return speed


@dataclass
class Field:
    weather: str = ""  # "sun", "rain", "sand", "snow", ""
    terrain: str = ""  # "electric", "grassy", "psychic", "misty", ""
    light_screen: bool = False
    reflect: bool = False
    aurora_veil: bool = False
    spread: bool = True  # doubles by default
    crit: bool = False
    ignore_ability_weather: bool = False  # skip auto-weather from Drought/etc.


@dataclass
class CalcResult:
    move: str
    type: str
    category: str
    rolls: list[int]
    percentages: list[float]
    ko_chance: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "move": self.move,
            "type": self.type,
            "category": self.category,
            "min": min(self.rolls),
            "max": max(self.rolls),
            "minPercent": round(min(self.percentages), 1),
            "maxPercent": round(max(self.percentages), 1),
            "rolls": self.rolls,
            "koChance": self.ko_chance,
        }


def _ability(c: Combatant) -> str:
    return (c.ability or "").strip().lower()


# Type-immunity abilities: {ability_name_lower: move_type that becomes 0x damage}
# Auto-applied weather from on-entry abilities (when field has no weather set)
_WEATHER_SETTER_ABILITIES: dict[str, str] = {
    "drought": "sun",
    "orichalcum pulse": "sun",
    "mega solar": "sun",
    "mega sol": "sun",
    "megasol": "sun",
    "drizzle": "rain",
    "sea of pearl": "rain",
    "sand stream": "sand",
    "snow warning": "snow",
    "sleet rush": "snow",
}


_IMMUNITY_ABILITIES: dict[str, str] = {
    "levitate": "ground",
    "earth eater": "ground",
    "flash fire": "fire",
    "well-baked body": "fire",
    "water absorb": "water",
    "dry skin": "water",
    "storm drain": "water",
    "volt absorb": "electric",
    "lightning rod": "electric",
    "motor drive": "electric",
    "sap sipper": "grass",
}


class DamageCalculator:
    def calculate(self, attacker: Combatant, defender: Combatant, move_name: str, field: Field | None = None) -> CalcResult:
        field = field or Field()
        move = MOVE_LIBRARY.get(move_name)
        if move is None:
            raise ValueError(f"Unknown move: {move_name}")

        category = move["category"]
        bp = int(move["bp"])
        move_type = move["type"]
        atk_ab = _ability(attacker)
        def_ab = _ability(defender)
        mold_breaker = atk_ab in ("mold breaker", "teravolt", "turboblaze")
        # Auto-apply weather from on-entry abilities when field is neutral.
        if not field.weather and not field.ignore_ability_weather:
            atk_setter = _WEATHER_SETTER_ABILITIES.get(atk_ab)
            def_setter = _WEATHER_SETTER_ABILITIES.get(def_ab)
            if atk_setter:
                field = dataclasses.replace(field, weather=atk_setter)
            elif def_setter:
                field = dataclasses.replace(field, weather=def_setter)

        # Type-change attacker abilities applied to Normal-type moves
        if move_type == "normal":
            if atk_ab == "aerilate":
                move_type = "flying"; bp = int(bp * 1.2)
            elif atk_ab == "pixilate":
                move_type = "fairy"; bp = int(bp * 1.2)
            elif atk_ab == "refrigerate":
                move_type = "ice"; bp = int(bp * 1.2)
            elif atk_ab == "galvanize":
                move_type = "electric"; bp = int(bp * 1.2)
        if atk_ab == "liquid voice" and (move.get("flags") or {}).get("sound"):
            move_type = "water"

        if move_type == "normal" and move_name == "Weather Ball":
            move_type = _weather_ball_type(field.weather)
            if field.weather:
                bp = 100

        # Type-immunity defensive abilities (skipped if attacker has Mold Breaker)
        if not mold_breaker and _IMMUNITY_ABILITIES.get(def_ab) == move_type:
            rolls = [0] * 16
            hp = defender.stat("hp") or 1
            return CalcResult(
                move=move_name, type=move_type, category=category,
                rolls=rolls, percentages=[0.0] * 16,
                ko_chance=f"{defender.name or 'defender'} immune via {def_ab.title()}",
            )

        if move.get("uses_defense_as_attack"):
            a_stat = _boosted(attacker.stat("def"), attacker.boosts.get("def", 0))
        elif move.get("uses_target_attack"):
            a_stat = _boosted(defender.stat("atk"), defender.boosts.get("atk", 0))
        elif category == "physical":
            a_stat = _boosted(attacker.stat("atk"), attacker.boosts.get("atk", 0))
        else:
            a_stat = _boosted(attacker.stat("spa"), attacker.boosts.get("spa", 0))

        if category == "physical":
            d_stat = _boosted(defender.stat("def"), defender.boosts.get("def", 0))
        else:
            d_stat = _boosted(defender.stat("spd"), defender.boosts.get("spd", 0))

        bp = int(bp * _weather_bp_modifier(move_type, field.weather))
        bp = int(bp * _terrain_bp_modifier(move_type, field.terrain, attacker))
        if bp <= 0:
            bp = 1

        damage_base = floor((((2 * attacker.level) / 5 + 2) * bp * a_stat / max(d_stat, 1)) / 50) + 2

        if field.spread and move.get("spread"):
            damage_base = floor(damage_base * 0.75)

        if field.crit:
            damage_base = floor(damage_base * 1.5)

        if attacker.is_burned and category == "physical" and not move.get("ignore_burn"):
            damage_base = floor(damage_base / 2)

        if (field.reflect and category == "physical") or (field.light_screen and category == "special") or field.aurora_veil:
            if not field.crit:
                damage_base = floor(damage_base * (2 / 3))

        attacker_types = [attacker.tera_type] if attacker.tera_type else attacker.types
        stab = 1.5 if move_type in attacker_types else 1.0
        if attacker.tera_type and move_type in attacker.types and move_type == attacker.tera_type:
            stab = 2.0
        # Adaptability bumps STAB to 2.0 (or 2.25 with same-type tera)
        if atk_ab == "adaptability" and move_type in attacker.types:
            stab = 2.25 if stab == 2.0 else 2.0

        defender_types = [defender.tera_type] if defender.tera_type else defender.types
        type_multiplier = 1.0
        chart = TYPE_CHART.get(move_type, {})
        for defending_type in defender_types:
            type_multiplier *= chart.get(defending_type, 1.0)

        damage_after_stab = floor(damage_base * stab)
        damage_after_type = floor(damage_after_stab * type_multiplier)

        # Defensive damage-reduction abilities
        if not mold_breaker:
            if type_multiplier > 1.0 and def_ab in ("filter", "solid rock", "prism armor"):
                damage_after_type = floor(damage_after_type * 0.75)
            if def_ab == "thick fat" and move_type in ("fire", "ice"):
                damage_after_type = floor(damage_after_type * 0.5)
            if def_ab == "heatproof" and move_type == "fire":
                damage_after_type = floor(damage_after_type * 0.5)
            if def_ab == "fluffy" and (move.get("flags") or {}).get("contact"):
                damage_after_type = floor(damage_after_type * 0.5)
            if def_ab in ("multiscale", "shadow shield"):
                # Assume full HP (we can't track HP between calcs)
                damage_after_type = floor(damage_after_type * 0.5)
        # Tinted Lens doubles NVE damage
        if atk_ab == "tinted lens" and 0 < type_multiplier < 1.0:
            damage_after_type = floor(damage_after_type * 2.0)
        # Tough Claws +30% on contact moves
        if atk_ab == "tough claws" and (move.get("flags") or {}).get("contact"):
            damage_after_type = floor(damage_after_type * 1.3)
        # Sand Force: rock/ground/steel +30% in sand
        if atk_ab == "sand force" and field.weather == "sand" and move_type in ("rock", "ground", "steel"):
            damage_after_type = floor(damage_after_type * 1.3)

        rolls = [floor(damage_after_type * roll / 100) for roll in range(85, 101)]
        hp = defender.stat("hp") or 1
        percentages = [r / hp * 100 for r in rolls]
        ko_chance = _ko_chance(rolls, hp)

        return CalcResult(
            move=move_name,
            type=move_type,
            category=category,
            rolls=rolls,
            percentages=percentages,
            ko_chance=ko_chance,
        )


def _boosted(stat: int, boost: int) -> int:
    boost = max(-6, min(6, boost))
    if boost >= 0:
        return floor(stat * (2 + boost) / 2)
    return floor(stat * 2 / (2 + abs(boost)))


def _weather_bp_modifier(move_type: str, weather: str) -> float:
    if weather == "sun":
        if move_type == "fire":
            return 1.5
        if move_type == "water":
            return 0.5
    if weather == "rain":
        if move_type == "water":
            return 1.5
        if move_type == "fire":
            return 0.5
    return 1.0


def _terrain_bp_modifier(move_type: str, terrain: str, attacker: Combatant) -> float:
    if not terrain:
        return 1.0
    grounded = "flying" not in attacker.types
    if terrain == "electric" and grounded and move_type == "electric":
        return 1.3
    if terrain == "grassy" and grounded and move_type == "grass":
        return 1.3
    if terrain == "psychic" and grounded and move_type == "psychic":
        return 1.3
    if terrain == "misty" and grounded and move_type == "dragon":
        return 0.5
    return 1.0


def _weather_ball_type(weather: str) -> str:
    return {"sun": "fire", "rain": "water", "sand": "rock", "snow": "ice"}.get(weather, "normal")


def _ko_chance(rolls: list[int], hp: int) -> str:
    if min(rolls) >= hp:
        return "OHKO guaranteed"
    if max(rolls) >= hp:
        chance = sum(1 for r in rolls if r >= hp) / len(rolls) * 100
        return f"OHKO {chance:.0f}%"
    if min(rolls) * 2 >= hp:
        return "2HKO guaranteed"
    if max(rolls) * 2 >= hp:
        chance = sum(1 for r in rolls if r * 2 >= hp) / len(rolls) * 100
        return f"2HKO {chance:.0f}%"
    return "3+HKO"
