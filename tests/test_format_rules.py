from pokemon_anti_meta_builder.format_rules import filter_legal_meta
from pokemon_anti_meta_builder.models import PokemonMeta


def test_reg_ma_filters_illegal_pokemon() -> None:
    meta = [
        PokemonMeta(name="Calyrex-Shadow", usage=50),
        PokemonMeta(name="Incineroar", usage=30),
    ]

    filtered, warnings = filter_legal_meta(meta, "reg-ma")

    assert [mon.name for mon in filtered] == ["Incineroar"]
    assert "Calyrex-Shadow" in warnings[0]


def test_reg_ma_allows_legal_forms_by_base_species() -> None:
    meta = [
        PokemonMeta(name="Rotom-Wash", usage=20),
        PokemonMeta(name="Ninetales-Alola", usage=10),
    ]

    filtered, warnings = filter_legal_meta(meta, "reg-ma")

    assert [mon.name for mon in filtered] == ["Rotom-Wash", "Ninetales-Alola"]
    assert warnings == []
