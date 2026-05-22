from __future__ import annotations

from pokemon_anti_meta_builder.data_fetcher.pokekipe import _details_to_row
from pokemon_anti_meta_builder.meta_parser import MetaParser
from pokemon_anti_meta_builder.models import EVSpread, PokemonMeta, PokemonSet, WeightedOption
from pokemon_anti_meta_builder.threat_analyzer import ThreatAnalyzer


def _set(species: str, moves: list[str] | None = None) -> PokemonSet:
    return PokemonSet(
        species=species,
        item="",
        ability="",
        moves=moves or [],
        evs=EVSpread(),
        nature="Hardy",
        roles=[],
        explanation="",
    )


def test_pokekipe_mapping_extracts_checks_counters() -> None:
    row = _details_to_row(
        {
            "pokemon_name": "Sneasler",
            "usage_rate": 0.43,
            "reference": {"type1": "Fighting", "type2": "Poison"},
            "items": [],
            "abilities": [],
            "moves": [],
            "spreads": [],
            "teammates": [],
            "checks_counters": [
                {"name": "Incineroar", "usage": 0.42},
                {"name": "Whimsicott", "usage": 0.28},
            ],
            "roles": [],
        },
        {},
    )

    assert "Incineroar:42.00" in row["checks_counters"]
    assert "Whimsicott:28.00" in row["checks_counters"]


def test_meta_parser_reads_checks_counters_csv(tmp_path) -> None:
    path = tmp_path / "meta.csv"
    path.write_text(
        "pokemon,usage,types,checks_counters\n"
        "Sneasler,43.8,fighting;poison,Incineroar:42.0;Whimsicott:28.0\n",
        encoding="utf-8",
    )

    meta = MetaParser().parse_file(path)

    assert meta[0].name == "Sneasler"
    names = [option.name for option in meta[0].checks_counters]
    assert names[:2] == ["Incineroar", "Whimsicott"]
    assert meta[0].checks_counters[0].weight == 42.0


def test_threat_analyzer_uses_real_checks_when_present() -> None:
    threat = PokemonMeta(
        name="Sneasler",
        usage=43.8,
        types=["fighting", "poison"],
        checks_counters=[
            WeightedOption("Incineroar", 42.0),
            WeightedOption("Whimsicott", 28.0),
        ],
    )
    incineroar = PokemonMeta(name="Incineroar", usage=30.0, types=["fire", "dark"])
    team = [_set("Incineroar"), _set("Garchomp")]

    report = ThreatAnalyzer().analyze(team, [threat, incineroar])

    assert report.used_pokekipe_data is True
    assert report.threats_with_real_data >= 1
    safe_entries = [e for e in report.entries if e.severity == "safe"]
    assert any("Incineroar" in e.summary and "Pokékipe" in e.summary for e in safe_entries)


def test_threat_analyzer_flags_missing_real_check() -> None:
    threat = PokemonMeta(
        name="Sneasler",
        usage=43.8,
        types=["fighting", "poison"],
        checks_counters=[WeightedOption("Incineroar", 42.0)],
    )
    team = [_set("Garchomp", moves=["Dragon Claw"])]

    report = ThreatAnalyzer().analyze(team, [threat])

    assert report.used_pokekipe_data is True
    danger_entries = [e for e in report.entries if e.severity == "danger"]
    assert any("Incineroar" in e.summary for e in danger_entries)


def test_threat_analyzer_falls_back_to_type_based_when_no_real_data() -> None:
    threat = PokemonMeta(name="Garchomp", usage=40.0, types=["dragon", "ground"])
    team = [_set("Glaceon", moves=["Ice Beam"]), _set("Tangrowth", moves=["Giga Drain"])]

    report = ThreatAnalyzer().analyze(team, [threat])

    assert report.used_pokekipe_data is False
    assert report.threats_with_fallback >= 1
    rendered = report.render()
    assert "type-based" in rendered.lower()
