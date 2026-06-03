import unittest
from pokemon_anti_meta_builder.recommendations.service import RecommendationService
from pokemon_anti_meta_builder.ev_optimizer.service import EVTunerService
from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry


def _service():
    import os
    pk = "data/raw/pikalytics_sets.json"
    return RecommendationService(
        input_path="data/raw/reg_ma_pokekipe.csv", format_id="reg-ma",
        dex_path="data/raw/showdown_dex.json", learnsets_path="data/raw/showdown_learnsets.json",
        pikalytics_path=pk if os.path.exists(pk) else None,
    )


class TestFindByMoves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_intersection_requires_all_moves(self):
        out = self.reg.call("find_pokemon_by_moves", {"moves": ["Protect"], "require_all": True})
        self.assertTrue(out["ok"])
        self.assertIsInstance(out["species"], list)

    def test_unknown_move_returns_empty_not_error(self):
        out = self.reg.call("find_pokemon_by_moves", {"moves": ["NotARealMove"], "require_all": True})
        self.assertTrue(out["ok"])
        self.assertEqual(out["species"], [])

    def test_unknown_tool_name_errors(self):
        out = self.reg.call("does_not_exist", {})
        self.assertFalse(out["ok"])


class TestSearchAndLearnset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_search_by_type(self):
        out = self.reg.call("search_pokemon", {"type": "fairy"})
        self.assertTrue(out["ok"])
        self.assertTrue(all("fairy" in [t.lower() for t in p["types"]] for p in out["pokemon"]))

    def test_search_min_usage_filters(self):
        out = self.reg.call("search_pokemon", {"min_usage": 5.0})
        self.assertTrue(all(p["usage"] >= 5.0 for p in out["pokemon"]))

    def test_get_learnset(self):
        out = self.reg.call("get_learnset", {"species": "Garchomp"})
        self.assertTrue(out["ok"])
        self.assertIn("earthquake", [m.lower() for m in out["moves"]])


class TestCountersAndSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_who_counters_returns_reasons(self):
        out = self.reg.call("who_counters", {"species": "Garchomp"})
        self.assertTrue(out["ok"])
        self.assertTrue(out["counters"])
        self.assertIn("reasons", out["counters"][0])

    def test_countered_by(self):
        out = self.reg.call("countered_by", {"species": "Garchomp"})
        self.assertTrue(out["ok"])

    def test_get_set_has_moves_and_stats(self):
        out = self.reg.call("get_set", {"species": "Incineroar"})
        self.assertTrue(out["ok"])
        self.assertIn("moves", out["set"])
        self.assertIn("baseStats", out["set"])


class TestOutspeedTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_min_speed_to_outspeed_returns_result(self):
        out = self.reg.call("min_speed_to_outspeed", {
            "species": "Charizard", "target": "Aerodactyl",
            "target_max_speed": True, "our_boost": 1,
        })
        self.assertTrue(out["ok"])
        self.assertIn("evs", out["result"])
        self.assertIn("proposal", out)

    def test_missing_species_errors(self):
        out = self.reg.call("min_speed_to_outspeed", {"target": "Aerodactyl"})
        self.assertFalse(out["ok"])


class TestSurviveOhkoTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_survive_returns_evs(self):
        out = self.reg.call("min_evs_to_survive", {
            "species": "Incineroar", "attacker": "Garchomp", "move": "Earthquake",
        })
        self.assertTrue(out["ok"])
        self.assertIn("result", out)

    def test_ohko_returns_evs(self):
        out = self.reg.call("min_evs_to_ohko", {
            "species": "Garchomp", "target": "Incineroar", "move": "Earthquake",
        })
        self.assertTrue(out["ok"])

    def test_survive_missing_move_errors(self):
        out = self.reg.call("min_evs_to_survive", {"species": "Incineroar", "attacker": "Garchomp"})
        self.assertFalse(out["ok"])


class TestOutspeedNatureLockTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_tool_passes_nature_lock(self):
        out = self.reg.call("min_speed_to_outspeed", {
            "species": "Charizard", "target": "Aerodactyl",
            "target_max_speed": True, "our_boost": 1, "nature": "Adamant",
        })
        self.assertTrue(out["ok"])
        # the engine result must keep the locked nature, never silently swap it
        self.assertEqual(out["result"]["nature"], "Adamant")


class TestToolDeclarations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_declarations_cover_every_tool(self):
        decls = self.reg.declarations()
        names = {d["name"] for d in decls}
        self.assertEqual(names, set(self.reg.tool_names()))

    def test_declaration_shape(self):
        for d in self.reg.declarations():
            self.assertIn("name", d)
            self.assertIn("description", d)
            self.assertIn("parameters", d)
            self.assertEqual(d["parameters"]["type"], "object")


class TestSurviveToolExtras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_survive_tool_accepts_nature_boost_field(self):
        out = self.reg.call("min_evs_to_survive", {
            "species": "Incineroar", "attacker": "Garchomp", "move": "Earthquake",
            "nature": "Impish", "defense_boost": 1, "reflect": True,
        })
        self.assertTrue(out["ok"])
        self.assertIn("result", out)

    def test_survive_tool_field_changes_outcome_path(self):
        # just assert the call succeeds with weather/screen flags (no crash)
        out = self.reg.call("min_evs_to_survive", {
            "species": "Incineroar", "attacker": "Garchomp", "move": "Earthquake",
            "light_screen": True, "weather": "sun",
        })
        self.assertTrue(out["ok"])


class TestMegaAliasResolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_colloquial_mega_names_resolve(self):
        for raw in ["Charizard X", "Mega Charizard X", "Charizard Mega X", "Charizard-X"]:
            self.assertEqual(self.reg.resolve_species(raw), "Charizard-Mega-X", raw)

    def test_suffixless_mega_resolves_but_not_base(self):
        # "Mega Garchomp" / "Garchomp Mega" -> the mega form
        self.assertEqual(self.reg.resolve_species("Mega Garchomp"), "Garchomp-Mega")
        self.assertEqual(self.reg.resolve_species("Garchomp Mega"), "Garchomp-Mega")
        # plain base name must NOT be redirected to the mega
        self.assertEqual(self.reg.resolve_species("Garchomp"), "Garchomp")

    def test_unknown_or_normal_names_pass_through(self):
        self.assertEqual(self.reg.resolve_species("Incineroar"), "Incineroar")
        self.assertEqual(self.reg.resolve_species("Totally Fake Mon"), "Totally Fake Mon")
        self.assertEqual(self.reg.resolve_species(""), "")

    def test_outspeed_tool_accepts_colloquial_mega(self):
        out = self.reg.call("min_speed_to_outspeed", {
            "species": "Charizard X", "target": "Aerodactyl",
            "target_max_speed": True, "our_boost": 1, "nature": "Adamant",
        })
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["nature"], "Adamant")


class TestOhkoBoostTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_ohko_tool_accepts_attack_boost(self):
        out = self.reg.call("min_evs_to_ohko", {
            "species": "Garchomp", "target": "Incineroar", "move": "Earthquake",
            "attack_boost": 2,
        })
        self.assertTrue(out["ok"])
        self.assertIn("result", out)
