from __future__ import annotations

POKEMON_TYPES = {
    "bug",
    "dark",
    "dragon",
    "electric",
    "fairy",
    "fighting",
    "fire",
    "flying",
    "ghost",
    "grass",
    "ground",
    "ice",
    "normal",
    "poison",
    "psychic",
    "rock",
    "steel",
    "water",
}

TYPE_CHART: dict[str, dict[str, float]] = {
    "normal": {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire": {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0, "bug": 2.0, "rock": 0.5, "dragon": 0.5, "steel": 2.0},
    "water": {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0, "rock": 2.0, "dragon": 0.5},
    "electric": {"water": 2.0, "electric": 0.5, "grass": 0.5, "ground": 0.0, "flying": 2.0, "dragon": 0.5},
    "grass": {"fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5, "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0, "dragon": 0.5, "steel": 0.5},
    "ice": {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5, "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0, "dark": 2.0, "steel": 2.0, "fairy": 0.5},
    "poison": {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0, "fairy": 2.0},
    "ground": {"fire": 2.0, "electric": 2.0, "grass": 0.5, "poison": 2.0, "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0},
    "flying": {"electric": 0.5, "grass": 2.0, "fighting": 2.0, "bug": 2.0, "rock": 0.5, "steel": 0.5},
    "psychic": {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0, "steel": 0.5},
    "bug": {"fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0, "steel": 0.5, "fairy": 0.5},
    "rock": {"fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5, "flying": 2.0, "bug": 2.0, "steel": 0.5},
    "ghost": {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon": {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark": {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5, "fairy": 0.5},
    "steel": {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0, "rock": 2.0, "steel": 0.5, "fairy": 2.0},
    "fairy": {"fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0, "dark": 2.0, "steel": 0.5},
}

MOVE_TYPES: dict[str, str] = {
    "astral barrage": "ghost",
    "bleakwind storm": "flying",
    "body press": "fighting",
    "close combat": "fighting",
    "dazzling gleam": "fairy",
    "draco meteor": "dragon",
    "earth power": "ground",
    "earthquake": "ground",
    "electro drift": "electric",
    "eruption": "fire",
    "expanding force": "psychic",
    "fake out": "normal",
    "flare blitz": "fire",
    "flower trick": "grass",
    "glacial lance": "ice",
    "gold rush": "steel",
    "heat wave": "fire",
    "hurricane": "flying",
    "hyper voice": "normal",
    "ice beam": "ice",
    "icy wind": "ice",
    "jet punch": "water",
    "knock off": "dark",
    "moonblast": "fairy",
    "origin pulse": "water",
    "precipice blades": "ground",
    "protect": "normal",
    "psyblade": "psychic",
    "raging fury": "fire",
    "shadow ball": "ghost",
    "sludge bomb": "poison",
    "spirit break": "fairy",
    "spore": "grass",
    "surging strikes": "water",
    "tailwind": "flying",
    "thunderbolt": "electric",
    "trick room": "psychic",
    "u-turn": "bug",
    "water spout": "water",
    "wicked blow": "dark",
    "wild charge": "electric",
}

MOVE_CATEGORIES: dict[str, str] = {
    "astral barrage": "special",
    "bleakwind storm": "special",
    "body press": "physical",
    "close combat": "physical",
    "dazzling gleam": "special",
    "draco meteor": "special",
    "earth power": "special",
    "earthquake": "physical",
    "electro drift": "special",
    "eruption": "special",
    "expanding force": "special",
    "fake out": "physical",
    "flare blitz": "physical",
    "flower trick": "physical",
    "glacial lance": "physical",
    "gold rush": "special",
    "heat wave": "special",
    "hurricane": "special",
    "hyper voice": "special",
    "ice beam": "special",
    "icy wind": "special",
    "jet punch": "physical",
    "knock off": "physical",
    "moonblast": "special",
    "origin pulse": "special",
    "precipice blades": "physical",
    "psyblade": "physical",
    "raging fury": "physical",
    "shadow ball": "special",
    "sludge bomb": "special",
    "spirit break": "physical",
    "surging strikes": "physical",
    "thunderbolt": "special",
    "u-turn": "physical",
    "water spout": "special",
    "wicked blow": "physical",
    "wild charge": "physical",
}

MOVE_TYPE_BY_ID = {key.replace(" ", "").replace("-", "").replace("'", "").lower(): value for key, value in MOVE_TYPES.items()}
MOVE_CATEGORY_BY_ID = {key.replace(" ", "").replace("-", "").replace("'", "").lower(): value for key, value in MOVE_CATEGORIES.items()}


def move_type_for(move_name: str) -> str | None:
    key = move_name.replace(" ", "").replace("-", "").replace("'", "").lower()
    return MOVE_TYPES.get(move_name.lower()) or MOVE_TYPE_BY_ID.get(key)


def move_category_for(move_name: str) -> str | None:
    key = move_name.replace(" ", "").replace("-", "").replace("'", "").lower()
    return MOVE_CATEGORIES.get(move_name.lower()) or MOVE_CATEGORY_BY_ID.get(key)

SPEED_CONTROL_MOVES = {"tailwind", "trick room", "icy wind", "electroweb", "thunder wave"}
DISRUPTION_MOVES = {"fake out", "spore", "taunt", "encore", "will-o-wisp", "parting shot", "snarl"}
PROTECT_MOVES = {"protect", "detect", "spiky shield", "wide guard"}

DEFAULT_MOVES_BY_TYPE = {
    "fire": "Heat Wave",
    "water": "Muddy Water",
    "grass": "Energy Ball",
    "electric": "Thunderbolt",
    "ice": "Ice Beam",
    "fighting": "Close Combat",
    "poison": "Sludge Bomb",
    "ground": "Earth Power",
    "flying": "Air Slash",
    "psychic": "Psychic",
    "bug": "U-turn",
    "rock": "Rock Slide",
    "ghost": "Shadow Ball",
    "dragon": "Draco Meteor",
    "dark": "Knock Off",
    "steel": "Flash Cannon",
    "fairy": "Moonblast",
    "normal": "Hyper Voice",
}
