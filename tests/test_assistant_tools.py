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
