from pathlib import Path
import json

from pokemon_anti_meta_builder.meta_parser import MetaParser


def test_parser_reads_example_csv() -> None:
    path = Path(__file__).parents[1] / "data" / "raw" / "example_meta.csv"
    meta = MetaParser().parse_file(path)

    incineroar = next(mon for mon in meta if mon.name == "Incineroar")
    assert incineroar.usage == 31.8
    assert incineroar.items[0].name == "Sitrus Berry"
    assert "disruption" in incineroar.roles
    assert incineroar.types == ["fire", "dark"]


def test_parser_reads_smogon_chaos_shape(tmp_path: Path) -> None:
    path = tmp_path / "chaos.json"
    path.write_text(
        json.dumps(
            {
                "data": {
                    "Flutter Mane": {
                        "usage": 0.258,
                        "Items": {"Booster Energy": 60},
                        "Abilities": {"Protosynthesis": 100},
                        "Moves": {"Moonblast": 90, "Protect": 70},
                        "Spreads": {"Timid:4/0/0/252/0/252": 42},
                        "Teammates": {"Chi-Yu": 25},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    meta = MetaParser().parse_file(path)

    assert meta[0].name == "Flutter Mane"
    assert meta[0].usage == 25.8
    assert meta[0].moves[0].name == "Moonblast"
