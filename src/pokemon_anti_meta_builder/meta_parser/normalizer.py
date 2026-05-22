from __future__ import annotations

import re


_KNOWN_WORDS = {
    "hp": "HP",
    "ohko": "OHKO",
    "vgc": "VGC",
}

_SPECIAL_DISPLAY = {
    "aegislash": "Aegislash",
    "basculegion": "Basculegion",
    "calyrex-shadow": "Calyrex-Shadow",
    "calyrex-ice": "Calyrex-Ice",
    "charizard-mega-x": "Charizard-Mega-X",
    "charizard-mega-y": "Charizard-Mega-Y",
    "dragonite-mega": "Dragonite-Mega",
    "floette-mega": "Floette-Mega",
    "froslass-mega": "Froslass-Mega",
    "gardevoir-mega": "Gardevoir-Mega",
    "gengar-mega": "Gengar-Mega",
    "glimmora-mega": "Glimmora-Mega",
    "ho-oh": "Ho-Oh",
    "incineroar": "Incineroar",
    "kingambit": "Kingambit",
    "kommo-o": "Kommo-O",
    "ninetales-alola": "Ninetales-Alola",
    "porygon-z": "Porygon-Z",
    "rotom-wash": "Rotom-Wash",
    "rotom-heat": "Rotom-Heat",
    "rotom-mow": "Rotom-Mow",
    "scizor-mega": "Scizor-Mega",
    "scovillain-mega": "Scovillain-Mega",
    "sneasler": "Sneasler",
    "tyranitar-mega": "Tyranitar-Mega",
    "u-turn": "U-turn",
    "whimsicott": "Whimsicott",
    "zoroark-hisui": "Zoroark-Hisui",
}


def to_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def normalize_name(value: str) -> str:
    value = " ".join(str(value).replace("_", " ").split())
    if not value:
        return value
    special = _SPECIAL_DISPLAY.get(value.lower())
    if special:
        return special
    words = []
    for word in value.split(" "):
        parts = []
        for part in word.split("-"):
            low = part.lower()
            parts.append(_KNOWN_WORDS.get(low, part[:1].upper() + part[1:]))
        words.append("-".join(parts))
    return " ".join(words)


def normalize_type(value: str) -> str:
    return str(value).strip().lower()


def normalize_role(value: str) -> str:
    return str(value).strip().lower().replace(" ", "-").replace("_", "-")
