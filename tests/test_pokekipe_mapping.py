from pokemon_anti_meta_builder.data_fetcher.pokekipe import _details_to_row


def test_pokekipe_mapping_converts_mega_form_to_base_with_stone() -> None:
    row = _details_to_row(
        {
            "pokemon_name": "Charizard-Mega-Y",
            "usage_rate": 0.16,
            "reference": {"type1": "Fire", "type2": "Flying"},
            "items": [],
            "abilities": [{"name": "drought", "usage": 1}],
            "moves": [{"name": "heatwave", "usage": 0.9}, {"name": "protect", "usage": 0.7}],
            "spreads": [{"spread": "Timid:2/0/0/32/0/32", "usage": 0.4}],
            "teammates": [{"name": "Whimsicott", "usage": 0.3}],
            "roles": ["special_wallbreaker"],
        },
        {},
    )

    assert row["pokemon"] == "Charizard"
    assert row["items"].startswith("Charizardite Y:100.00")
    assert "Heat Wave" in row["moves"]
    assert "special-attacker" in row["roles"]
