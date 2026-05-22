from __future__ import annotations

from pokemon_anti_meta_builder.meta_parser.normalizer import to_key
from pokemon_anti_meta_builder.models import PokemonMeta


REG_MA_ALIASES = {"reg-ma", "regma", "m-a", "pokemon-champions-reg-ma", "champions-reg-ma", "vgc2026regma"}

REG_MA_LEGAL_POKEMON = {
    "Abomasnow", "Absol", "Aegislash", "Aerodactyl", "Aggron", "Alakazam", "Alcremie", "Altaria",
    "Ampharos", "Appletun", "Araquanid", "Arbok", "Arcanine", "Archaludon", "Ariados", "Armarouge",
    "Aromatisse", "Audino", "Aurorus", "Avalugg", "Azumarill", "Banette", "Basculegion", "Bastiodon",
    "Beartic", "Beedrill", "Bellibolt", "Blastoise", "Camerupt", "Castform", "Ceruledge", "Chandelure",
    "Charizard", "Chesnaught", "Chimecho", "Clawitzer", "Clefable", "Cofagrigus", "Conkeldurr", "Corviknight",
    "Crabominable", "Decidueye", "Dedenne", "Delphox", "Diggersby", "Ditto", "Dragapult", "Dragonite",
    "Drampa", "Emboar", "Emolga", "Empoleon", "Espathra", "Espeon", "Excadrill", "Farigiraf",
    "Feraligatr", "Flapple", "Flareon", "Floette", "Florges", "Forretress", "Froslass", "Furfrou",
    "Gallade", "Garbodor", "Garchomp", "Gardevoir", "Garganacl", "Gengar", "Glaceon", "Glalie",
    "Glimmora", "Gliscor", "Golurk", "Goodra", "Gourgeist", "Greninja", "Gyarados", "Hatterene",
    "Hawlucha", "Heliolisk", "Heracross", "Hippowdon", "Houndoom", "Hydrapple", "Hydreigon", "Incineroar",
    "Infernape", "Jolteon", "Kangaskhan", "Kingambit", "Kleavor", "Klefki", "Kommo-O", "Krookodile",
    "Leafeon", "Liepard", "Lopunny", "Lucario", "Luxray", "Lycanroc", "Machamp", "Mamoswine",
    "Manectric", "Maushold", "Medicham", "Meganium", "Meowscarada", "Meowstic", "Milotic", "Mimikyu",
    "Morpeko", "Mr. Rime", "Mudsdale", "Ninetales", "Noivern", "Oranguru", "Orthworm", "Palafin",
    "Pangoro", "Passimian", "Patrat", "Pelipper", "Pidgeot", "Pikachu", "Pinsir", "Politoed",
    "Polteageist", "Primarina", "Quaquaval", "Raichu", "Rampardos", "Reuniclus", "Rhyperior", "Roserade",
    "Rotom", "Runerigus", "Sableye", "Salazzle", "Samurott", "Sandaconda", "Scizor", "Scovillain",
    "Serperior", "Sharpedo", "Simipour", "Simisage", "Simisear", "Sinistcha", "Skarmory", "Skeledirge",
    "Slowbro", "Slowking", "Slurpuff", "Sneasler", "Snorlax", "Spiritomb", "Starmie", "Steelix",
    "Stunfisk", "Sylveon", "Talonflame", "Tauros", "Tinkaton", "Torkoal", "Torterra", "Toucannon",
    "Toxapex", "Toxicroak", "Trevenant", "Tsareena", "Typhlosion", "Tyranitar", "Tyrantrum", "Umbreon",
    "Vanilluxe", "Vaporeon", "Venusaur", "Victreebel", "Vivillon", "Volcarona", "Weavile", "Whimsicott",
    "Wyrdeer", "Zoroark",
}

REG_MA_LEGAL_ITEMS = {
    "Abomasite", "Absolite", "Aerodactylite", "Aggronite", "Alakazite", "Altarianite", "Ampharosite",
    "Aspear Berry", "Audinite", "Babiri Berry", "Banettite", "Beedrillite", "Black Belt", "Black Glasses",
    "Blastoisinite", "Bright Powder", "Cameruptite", "Chandelurite", "Charcoal", "Charizardite X",
    "Charizardite Y", "Charti Berry", "Cheri Berry", "Chesnaughtite", "Chesto Berry", "Chilan Berry",
    "Chimechite", "Choice Scarf", "Chople Berry", "Clefablite", "Coba Berry", "Colbur Berry",
    "Crabominite", "Delphoxite", "Dragon Fang", "Dragoninite", "Drampanite", "Emboarite", "Excadrite",
    "Fairy Feather", "Feraligite", "Floettite", "Focus Band", "Focus Sash", "Froslassite", "Galladite",
    "Garchompite", "Gardevoirite", "Gengarite", "Glalitite", "Glimmoranite", "Golurkite", "Greninjite",
    "Gyaradosite", "Haban Berry", "Hard Stone", "Hawluchanite", "Heracronite", "Houndoominite",
    "Kangaskhanite", "Kasib Berry", "Kebia Berry", "King's Rock", "Leftovers", "Leppa Berry", "Light Ball",
    "Lopunnite", "Lucarionite", "Lum Berry", "Magnet", "Manectite", "Medichamite", "Meganiumite",
    "Mental Herb", "Meowsticite", "Metal Coat", "Miracle Seed", "Mystic Water", "Never-Melt Ice",
    "Occa Berry", "Oran Berry", "Passho Berry", "Payapa Berry", "Pecha Berry", "Persim Berry",
    "Pidgeotite", "Pinsirite", "Poison Barb", "Quick Claw", "Rawst Berry", "Rindo Berry", "Roseli Berry",
    "Sablenite", "Scizorite", "Scope Lens", "Scovillainite", "Sharp Beak", "Sharpedonite", "Shell Bell",
    "Shuca Berry", "Silk Scarf", "Silver Powder", "Sitrus Berry", "Skarmorite", "Slowbronite",
    "Soft Sand", "Spell Tag", "Starminite", "Steelixite", "Tanga Berry", "Twisted Spoon", "Tyranitarite",
    "Venusaurite", "Victreebelite", "Wacan Berry", "White Herb", "Yache Berry",
}


def is_reg_ma(format_id: str) -> bool:
    return format_id.strip().lower() in REG_MA_ALIASES


def filter_legal_meta(meta: list[PokemonMeta], format_id: str) -> tuple[list[PokemonMeta], list[str]]:
    if not is_reg_ma(format_id):
        return meta, []

    legal_keys = {to_key(name) for name in REG_MA_LEGAL_POKEMON}
    item_keys = {to_key(name) for name in REG_MA_LEGAL_ITEMS}
    filtered: list[PokemonMeta] = []
    warnings: list[str] = []

    for mon in meta:
        if _species_key(mon.name) not in legal_keys:
            warnings.append(f"{mon.name}: excluded because it is not legal in Pokemon Champions Regulation M-A.")
            continue
        mon.items = [item for item in mon.items if to_key(item.name) in item_keys]
        filtered.append(mon)

    return filtered, warnings


def _species_key(name: str) -> str:
    clean = name
    if "-Mega-" in clean:
        clean = clean.split("-Mega-", 1)[0]
    elif clean.endswith("-Mega"):
        clean = clean[: -len("-Mega")]
    for suffix in ("-Alola", "-Galar", "-Hisui", "-Wash", "-Heat", "-Mow", "-Fan", "-Frost"):
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)]
            break
    return to_key(clean)
