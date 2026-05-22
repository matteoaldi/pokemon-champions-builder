from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Archetype:
    id: str
    name: str
    summary: str
    preferred_pokemon: tuple[str, ...] = ()
    required_roles: tuple[str, ...] = ()
    preferred_moves: tuple[str, ...] = ()
    preferred_items: tuple[str, ...] = ()
    counters_to_cover: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)


ARCHETYPES = {
    "balance": Archetype(
        id="balance",
        name="Balance",
        summary="Flexible Reg M-A structure with one Mega, Fake Out, speed control, and mixed damage.",
        preferred_pokemon=("Incineroar", "Whimsicott", "Primarina", "Garchomp", "Archaludon"),
        required_roles=("mega-cornerstone", "disruption", "speed-control", "physical-attacker", "special-attacker"),
        preferred_moves=("Fake Out", "Tailwind", "Protect", "Icy Wind"),
        counters_to_cover=("Gardevoir", "Garchomp", "Primarina", "Charizard"),
    ),
    "rain": Archetype(
        id="rain",
        name="Rain",
        summary="Rain pressure with Water spread damage, defensive Fire mitigation, and speed control.",
        preferred_pokemon=("Politoed", "Pelipper", "Primarina", "Basculegion", "Archaludon", "Incineroar"),
        required_roles=("speed-control", "special-attacker", "physical-attacker", "disruption"),
        preferred_moves=("Rain Dance", "Hurricane", "Sparkling Aria", "Waterfall", "Electro Shot", "Protect"),
        preferred_items=("Mystic Water", "Damp Rock", "Focus Sash"),
        counters_to_cover=("Rillaboom", "Whimsicott", "Archaludon", "Gardevoir"),
    ),
    "sand": Archetype(
        id="sand",
        name="Sand",
        summary="Tyranitar plus Ground/Steel pressure, usually with Excadrill and anti-Water support.",
        preferred_pokemon=("Tyranitar", "Excadrill", "Garchomp", "Primarina", "Whimsicott", "Incineroar"),
        required_roles=("mega-cornerstone", "physical-attacker", "speed-control", "special-attacker", "disruption"),
        preferred_moves=("Rock Slide", "Earthquake", "Iron Head", "Tailwind", "Protect"),
        preferred_items=("Tyranitarite", "Soft Sand", "Focus Sash", "Mystic Water"),
        counters_to_cover=("Primarina", "Gardevoir", "Garchomp", "Whimsicott"),
    ),
    "sun": Archetype(
        id="sun",
        name="Sun",
        summary="Mega Charizard Y or Torkoal centered Fire pressure with Grass/Electric answers to Water.",
        preferred_pokemon=("Charizard", "Torkoal", "Scovillain", "Whimsicott", "Incineroar", "Garchomp"),
        required_roles=("mega-cornerstone", "special-attacker", "speed-control", "disruption", "physical-attacker"),
        preferred_moves=("Heat Wave", "Solar Beam", "Tailwind", "Fake Out", "Protect"),
        preferred_items=("Charizardite Y", "Charcoal", "Focus Sash", "Sitrus Berry"),
        counters_to_cover=("Tyranitar", "Primarina", "Garchomp", "Archaludon"),
    ),
    "trick-room": Archetype(
        id="trick-room",
        name="Trick Room",
        summary="Slower board control using Trick Room, Fake Out denial, and bulky attackers.",
        preferred_pokemon=("Farigiraf", "Hatterene", "Torkoal", "Rhyperior", "Incineroar", "Primarina"),
        required_roles=("speed-control", "support", "special-attacker", "physical-attacker", "disruption"),
        preferred_moves=("Trick Room", "Helping Hand", "Protect", "Fake Out", "Rock Slide"),
        preferred_items=("Mental Herb", "Sitrus Berry", "Leftovers", "Charcoal"),
        counters_to_cover=("Whimsicott", "Tyranitar", "Gardevoir", "Garchomp"),
    ),
    "tailwind-offense": Archetype(
        id="tailwind-offense",
        name="Tailwind Offense",
        summary="Fast-paced damage with Whimsicott/Talonflame support and immediate spread pressure.",
        preferred_pokemon=("Whimsicott", "Talonflame", "Garchomp", "Gardevoir", "Charizard", "Incineroar"),
        required_roles=("speed-control", "mega-cornerstone", "physical-attacker", "special-attacker", "disruption"),
        preferred_moves=("Tailwind", "Encore", "Earthquake", "Hyper Voice", "Heat Wave", "Protect"),
        preferred_items=("Focus Sash", "Sharp Beak", "Garchompite", "Gardevoirite", "Charizardite Y"),
        counters_to_cover=("Primarina", "Archaludon", "Tyranitar", "Incineroar"),
    ),
}


def list_archetypes() -> list[Archetype]:
    return list(ARCHETYPES.values())


def get_archetype(archetype_id: str | None) -> Archetype:
    if not archetype_id:
        return ARCHETYPES["balance"]
    return ARCHETYPES.get(archetype_id, ARCHETYPES["balance"])
