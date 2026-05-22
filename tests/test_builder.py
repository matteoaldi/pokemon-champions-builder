from pathlib import Path

from pokemon_anti_meta_builder.meta_parser import MetaParser
from pokemon_anti_meta_builder.set_builder import SetBuilder
from pokemon_anti_meta_builder.team_builder import TeamBuilder


def test_builder_selects_six_and_includes_core_roles() -> None:
    path = Path(__file__).parents[1] / "data" / "raw" / "example_meta.csv"
    meta = MetaParser().parse_file(path)
    selected = TeamBuilder().select_team(meta)
    sets = [SetBuilder().build_set(mon) for mon in selected]
    roles = {role for pokemon_set in sets for role in pokemon_set.roles}

    assert len(selected) == 6
    assert "speed-control" in roles
    assert "disruption" in roles
    assert any("Protect" in pokemon_set.moves for pokemon_set in sets)
