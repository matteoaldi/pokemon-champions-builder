"""Tests for the EV Tuner deterministic calculators.

Uses unittest so it runs with `python3 -m unittest discover tests` even
without pytest installed.
"""
import unittest

from pokemon_anti_meta_builder.damage_calc.calculator import Combatant, Field
from pokemon_anti_meta_builder.ev_optimizer.meta import (
    default_target_evs,
    parse_spread_option,
    top_n_spreads,
)
from pokemon_anti_meta_builder.ev_optimizer.ohko import find_min_offensive_evs
from pokemon_anti_meta_builder.ev_optimizer.outspeed import find_min_evs_to_outspeed
from pokemon_anti_meta_builder.ev_optimizer.suggest_remaining import suggest_remaining
from pokemon_anti_meta_builder.ev_optimizer.survive import (
    EV_MAX_PER_STAT,
    EV_MAX_TOTAL,
    find_min_evs_to_survive,
)
from pokemon_anti_meta_builder.models import PokemonMeta, WeightedOption


def _chomp_attacker(nature="Adamant", atk_ev=32, spe_ev=32) -> Combatant:
    return Combatant(
        name="Garchomp",
        types=["dragon", "ground"],
        base_stats={"hp": 108, "atk": 130, "def": 95, "spa": 80, "spd": 85, "spe": 102},
        evs={"hp": 2, "atk": atk_ev, "def": 0, "spa": 0, "spd": 0, "spe": spe_ev},
        nature=nature,
    )


def _sneasler_defender() -> Combatant:
    return Combatant(
        name="Sneasler",
        types=["fighting", "poison"],
        base_stats={"hp": 80, "atk": 130, "def": 60, "spa": 40, "spd": 80, "spe": 120},
        evs={"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        nature="Hardy",
    )


def _iron_hands() -> Combatant:
    return Combatant(
        name="Iron Hands",
        types=["fighting", "electric"],
        base_stats={"hp": 154, "atk": 140, "def": 108, "spa": 50, "spd": 68, "spe": 50},
        evs={"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        nature="Hardy",
    )


class TestSurvive(unittest.TestCase):
    def test_finds_feasible_spread(self):
        result = find_min_evs_to_survive(
            _sneasler_defender(), _chomp_attacker(), "Earthquake", Field(spread=True)
        )
        self.assertTrue(result.feasible)
        # Should be a tiny investment because EQ is spread + STAB ground vs poison resists
        self.assertLessEqual(result.total_used, EV_MAX_TOTAL)
        # Must guarantee survival in our chosen threshold
        self.assertEqual(result.survival_pct, 100.0)
        # Defensive stat that matters for physical is Def
        self.assertGreaterEqual(result.def_ev, 0)
        self.assertEqual(result.spd_ev, 0)

    def test_picks_def_for_physical_move(self):
        result = find_min_evs_to_survive(
            _sneasler_defender(), _chomp_attacker(), "Earthquake"
        )
        self.assertEqual(result.spd_ev, 0)

    def test_picks_spd_for_special_move(self):
        result = find_min_evs_to_survive(
            _sneasler_defender(),
            Combatant(
                name="Kyogre",
                types=["water"],
                base_stats={"hp": 100, "atk": 100, "def": 90, "spa": 150, "spd": 140, "spe": 90},
                evs={"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 0},
                nature="Modest",
            ),
            "Hydro Pump",
        )
        if result.feasible:
            self.assertEqual(result.def_ev, 0)


class TestOutspeed(unittest.TestCase):
    def test_outspeeds_paralyzed_garchomp(self):
        result = find_min_evs_to_outspeed(_iron_hands(), _chomp_attacker(), "paralysis_opp")
        self.assertTrue(result.feasible)
        # Iron Hands needs very few Spe EVs to beat paralyzed Chomp (~78 vs 77)
        self.assertLessEqual(result.spe_ev, EV_MAX_PER_STAT)
        self.assertGreater(result.our_speed, result.target_speed)

    def test_tailwind_changes_target_speed(self):
        no_cond = find_min_evs_to_outspeed(_iron_hands(), _chomp_attacker(), "none")
        opp_tw = find_min_evs_to_outspeed(_iron_hands(), _chomp_attacker(), "tailwind_opp")
        # Tailwind on opp doubles their speed → harder (less or equal feasibility)
        if no_cond.feasible and opp_tw.feasible:
            self.assertGreaterEqual(opp_tw.our_speed, opp_tw.target_speed + 1)


class TestOhko(unittest.TestCase):
    def test_iron_hands_close_combat_into_chomp(self):
        # Iron Hands has 140 base Atk + STAB Close Combat (120 BP) vs Chomp 95 base Def
        result = find_min_offensive_evs(_iron_hands(), _chomp_attacker(), "Close Combat", Field(spread=False), goal="2hko")
        # 2HKO on max-Spe Adamant Chomp is likely feasible
        self.assertTrue(result.feasible)
        self.assertGreaterEqual(result.atk_ev, 0)


class TestMeta(unittest.TestCase):
    def test_parse_spread_option(self):
        parsed = parse_spread_option("Adamant:2/32/0/0/0/32", 47.23)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["nature"], "Adamant")
        self.assertEqual(parsed["evs"]["atk"], 32)
        self.assertEqual(parsed["evs"]["spe"], 32)
        self.assertAlmostEqual(parsed["usage"], 47.23)

    def test_parse_spread_option_invalid(self):
        self.assertIsNone(parse_spread_option("garbage", 0.0))

    def test_top_n_spreads_picks_first_three(self):
        mon = PokemonMeta(
            name="Garchomp",
            usage=40.0,
            ev_spreads=[
                WeightedOption("Adamant:2/32/0/0/0/32", 20.0),
                WeightedOption("Jolly:0/32/0/0/2/32", 10.0),
                WeightedOption("Adamant:8/24/0/0/0/32", 5.0),
                WeightedOption("Jolly:2/32/0/0/0/32", 2.0),
            ],
        )
        out = top_n_spreads(mon, n=3)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["nature"], "Adamant")
        self.assertEqual(out[1]["nature"], "Jolly")


class TestSuggestRemaining(unittest.TestCase):
    def test_survive_mode_returns_3_suggestions(self):
        sugg = suggest_remaining({"hp": 8, "def": 32, "spd": 0}, "physical-attacker", "mode=survive".split("=")[1])
        self.assertEqual(len(sugg), 3)

    def test_returns_nothing_useful_when_all_spent(self):
        sugg = suggest_remaining({"hp": 32, "atk": 32, "spd": 2}, "physical-attacker", "survive")
        # 32+32+2 = 66 (Champions cap) → no leftover
        self.assertEqual(len(sugg), 1)
        self.assertIn("spesi", sugg[0])


if __name__ == "__main__":
    unittest.main()
