from pathlib import Path

from pokemon_anti_meta_builder.recommendations import RecommendationService


def test_recommendation_service_autobuild_respects_core_rules() -> None:
    path = Path(__file__).parents[1] / "data" / "raw" / "example_meta.csv"
    state = RecommendationService(path).auto_build()
    items = [member.item for member in state.team]
    mega_items = [item for item in items if item.endswith("ite") or item in {"Charizardite X", "Charizardite Y"}]

    assert len(state.team) == 6
    assert len(items) == len(set(items))
    assert len(mega_items) <= 1
    assert state.recommendations
