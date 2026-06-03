import unittest
from pokemon_anti_meta_builder.recommendations.service import RecommendationService
from pokemon_anti_meta_builder.ev_optimizer.service import EVTunerService
from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry
from pokemon_anti_meta_builder.ai_coach.agent import GeminiAgent


def _service():
    import os
    pk = "data/raw/pikalytics_sets.json"
    return RecommendationService(
        input_path="data/raw/reg_ma_pokekipe.csv", format_id="reg-ma",
        dex_path="data/raw/showdown_dex.json", learnsets_path="data/raw/showdown_learnsets.json",
        pikalytics_path=pk if os.path.exists(pk) else None,
    )


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        svc = _service()
        self.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_executes_function_call_then_returns_text(self):
        calls = []
        def fake_gemini(contents, tools):
            calls.append(contents)
            if len(calls) == 1:
                return {"functionCall": {"name": "find_pokemon_by_moves",
                                          "args": {"moves": ["Protect"], "require_all": True}}}
            return {"text": "Ecco i Pokémon che imparano Protect."}
        agent = GeminiAgent(self.reg, gemini_caller=fake_gemini)
        out = agent.run([{"role": "user", "text": "chi impara Protect?"}])
        self.assertEqual(out["reply"], "Ecco i Pokémon che imparano Protect.")
        self.assertEqual(out["toolTrace"][0]["name"], "find_pokemon_by_moves")
        self.assertEqual(len(calls), 2)

    def test_loop_cap_stops_runaway(self):
        def always_calls(contents, tools):
            return {"functionCall": {"name": "find_pokemon_by_moves", "args": {"moves": ["Protect"]}}}
        agent = GeminiAgent(self.reg, gemini_caller=always_calls, max_turns=3)
        out = agent.run([{"role": "user", "text": "loop"}])
        self.assertLessEqual(len(out["toolTrace"]), 3)
        self.assertTrue(out["reply"])
        self.assertIsInstance(out["reply"], str)

    def test_collects_proposals(self):
        def fake_gemini(contents, tools):
            if not any("functionResponse" in str(c) for c in contents):
                return {"functionCall": {"name": "min_evs_to_survive",
                                          "args": {"species": "Incineroar", "attacker": "Garchomp", "move": "Earthquake"}}}
            return {"text": "Ecco lo spread difensivo."}
        agent = GeminiAgent(self.reg, gemini_caller=fake_gemini)
        out = agent.run([{"role": "user", "text": "Incineroar regge Earthquake?"}])
        self.assertTrue(out["proposals"])
        self.assertEqual(out["proposals"][0]["species"], "Incineroar")
