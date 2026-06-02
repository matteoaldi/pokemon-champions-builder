from __future__ import annotations

from pathlib import Path

from pokemon_anti_meta_builder.constants import TYPE_CHART
from pokemon_anti_meta_builder.data_fetcher.pokekipe import _details_to_row
from pokemon_anti_meta_builder.meta_parser import MetaParser
from pokemon_anti_meta_builder.recommendations import RecommendationService
from pokemon_anti_meta_builder.recommendations.service import _is_switch_in, _threat_summary


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


def test_is_switch_in_resists_one_weak_to_none() -> None:
    # Water resists Fire STAB, weak to none of (fire) -> switch-in.
    assert _is_switch_in(["water"], ["fire"], TYPE_CHART) is True
    # Grass is weak to Fire -> not a switch-in even though it could resist water.
    assert _is_switch_in(["grass"], ["fire"], TYPE_CHART) is False
    # Neutral to everything -> not a switch-in (resists nothing).
    assert _is_switch_in(["normal"], ["fighting"], TYPE_CHART) is False


def test_threat_summary_status_text() -> None:
    covered = _threat_summary(["A"], ["B"], [], ["B"], "covered")
    assert "Risposta pulita" in covered and "colpita da B" in covered
    exposed = _threat_summary(["A", "B"], [], [], [], "exposed")
    assert "Preme 2 membri" in exposed and "Nessuna risposta" in exposed


def test_team_threat_coverage_unified_payload() -> None:
    path = Path(__file__).parents[1] / "data" / "raw" / "example_meta.csv"
    state = RecommendationService(path).auto_build()
    threats = state.threat_entries

    assert threats, "expected unified threat entries"
    sample = threats[0]
    for key in ("name", "severity", "summary", "pressures", "answers", "isMega", "usage"):
        assert key in sample
    assert sample["severity"] in {"danger", "risky", "safe"}
    # Sorted by number of pressured members (desc).
    pressures = [len(t["pressures"]) for t in threats]
    assert pressures == sorted(pressures, reverse=True)
