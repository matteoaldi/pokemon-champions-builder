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
