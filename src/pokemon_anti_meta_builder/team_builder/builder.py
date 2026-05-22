from __future__ import annotations

from collections import Counter

from pokemon_anti_meta_builder.constants import DISRUPTION_MOVES, PROTECT_MOVES, SPEED_CONTROL_MOVES, TYPE_CHART, move_type_for
from pokemon_anti_meta_builder.meta_parser.normalizer import to_key
from pokemon_anti_meta_builder.models import PokemonMeta


TARGET_ROLES = {
    "physical-attacker",
    "special-attacker",
    "speed-control",
    "disruption",
    "protect-user",
}


class TeamBuilder:
    def __init__(self, threat_count: int = 12):
        self.threat_count = threat_count

    def select_team(self, meta: list[PokemonMeta], size: int = 6) -> list[PokemonMeta]:
        if len(meta) < size:
            raise ValueError(f"Need at least {size} Pokemon in meta data; got {len(meta)}")

        selected: list[PokemonMeta] = []
        available = list(meta)
        threats = sorted(meta, key=lambda mon: mon.usage, reverse=True)[: self.threat_count]

        while len(selected) < size:
            scored = [(self.score_candidate(candidate, selected, threats), candidate) for candidate in available]
            scored.sort(key=lambda pair: (pair[0], pair[1].usage, pair[1].name), reverse=True)
            best = scored[0][1]
            selected.append(best)
            available = [candidate for candidate in available if candidate.name != best.name]
        return selected

    def score_candidate(self, candidate: PokemonMeta, selected: list[PokemonMeta], threats: list[PokemonMeta]) -> float:
        score = candidate.usage
        if candidate.winrate is not None:
            score += (candidate.winrate - 50.0) * 0.9

        existing_roles = {role for mon in selected for role in _roles(mon)}
        missing_roles = TARGET_ROLES - existing_roles
        candidate_roles = _roles(candidate)
        score += 8.0 * len(candidate_roles & missing_roles)

        if "speed-control" not in existing_roles and _has_any_move(candidate, SPEED_CONTROL_MOVES):
            score += 10.0
        if "disruption" not in existing_roles and _has_any_move(candidate, DISRUPTION_MOVES):
            score += 7.0
        if "protect-user" not in existing_roles and _has_any_move(candidate, PROTECT_MOVES):
            score += 4.0

        score += self._offensive_coverage_score(candidate, threats)
        score += self._defensive_coverage_score(candidate, threats)
        score -= self._weakness_redundancy_penalty(candidate, selected)
        score -= self._item_clause_penalty(candidate, selected)
        score += self._attack_balance_bonus(candidate, selected)

        teammate_names = {mon.name for mon in selected}
        for option in candidate.teammates:
            if option.name in teammate_names:
                score += min(option.weight / 10.0, 4.0)
        return score

    def _offensive_coverage_score(self, candidate: PokemonMeta, threats: list[PokemonMeta]) -> float:
        move_types = _offensive_types(candidate)
        score = 0.0
        for threat in threats:
            if any(_type_multiplier(move_type, threat.types) > 1.0 for move_type in move_types):
                score += min(threat.usage / 10.0, 3.0)
        return score

    def _defensive_coverage_score(self, candidate: PokemonMeta, threats: list[PokemonMeta]) -> float:
        score = 0.0
        for threat in threats:
            threat_stabs = [type_ for type_ in threat.types if type_]
            if any(_type_multiplier(stab, candidate.types) < 1.0 for stab in threat_stabs):
                score += min(threat.usage / 18.0, 2.0)
        return score

    def _weakness_redundancy_penalty(self, candidate: PokemonMeta, selected: list[PokemonMeta]) -> float:
        weaknesses = Counter()
        for mon in [*selected, candidate]:
            for attacking_type in TYPE_CHART:
                if _type_multiplier(attacking_type, mon.types) > 1.0:
                    weaknesses[attacking_type] += 1
        return sum((count - 2) * 4.0 for count in weaknesses.values() if count > 2)

    def _item_clause_penalty(self, candidate: PokemonMeta, selected: list[PokemonMeta]) -> float:
        candidate_item = _top_item(candidate)
        selected_items = {_top_item(mon) for mon in selected}
        penalty = 0.0
        if candidate_item and candidate_item in selected_items:
            penalty += 15.0
        if _is_mega_stone(candidate_item) and any(_is_mega_stone(item) for item in selected_items):
            penalty += 35.0
        return penalty

    def _attack_balance_bonus(self, candidate: PokemonMeta, selected: list[PokemonMeta]) -> float:
        roles = Counter(role for mon in selected for role in _roles(mon))
        candidate_roles = _roles(candidate)
        bonus = 0.0
        if roles["physical-attacker"] < roles["special-attacker"] and "physical-attacker" in candidate_roles:
            bonus += 5.0
        if roles["special-attacker"] < roles["physical-attacker"] and "special-attacker" in candidate_roles:
            bonus += 5.0
        return bonus


def _roles(mon: PokemonMeta) -> set[str]:
    return set(mon.roles)


def _has_any_move(mon: PokemonMeta, moves: set[str]) -> bool:
    wanted = {to_key(move) for move in moves}
    return bool({to_key(move.name) for move in mon.moves} & wanted)


def _offensive_types(mon: PokemonMeta) -> set[str]:
    types = set()
    for move in mon.moves[:8]:
        move_type = move_type_for(move.name)
        if move_type:
            types.add(move_type)
    return types or set(mon.types)


def _top_item(mon: PokemonMeta) -> str:
    return mon.items[0].name if mon.items else ""


def _is_mega_stone(item: str) -> bool:
    return item.endswith("ite") or item in {"Charizardite X", "Charizardite Y"}


def _type_multiplier(attacking_type: str, defending_types: list[str]) -> float:
    multiplier = 1.0
    chart = TYPE_CHART.get(attacking_type, {})
    for defending_type in defending_types:
        multiplier *= chart.get(defending_type, 1.0)
    return multiplier
