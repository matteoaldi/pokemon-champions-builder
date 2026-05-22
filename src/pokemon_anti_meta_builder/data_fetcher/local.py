from __future__ import annotations

from pathlib import Path

from pokemon_anti_meta_builder.meta_parser import MetaParser
from pokemon_anti_meta_builder.models import PokemonMeta


def load_meta_file(path: str | Path) -> list[PokemonMeta]:
    return MetaParser().parse_file(path)
