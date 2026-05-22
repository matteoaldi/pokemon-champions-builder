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
    # Mega stones (incl. Champions Z/X/Y variants)
    "Abomasite", "Absolite", "Absolite Z", "Aerodactylite", "Aggronite", "Alakazite", "Altarianite",
    "Ampharosite", "Audinite", "Banettite", "Beedrillite", "Blastoisinite", "Cameruptite",
    "Chandelurite", "Charizardite X", "Charizardite Y", "Chesnaughtite", "Chimechite", "Clefablite",
    "Crabominite", "Delphoxite", "Dragoninite", "Drampanite", "Emboarite", "Excadrite", "Feraligite",
    "Floettite", "Froslassite", "Galladite", "Garchompite", "Garchompite Z", "Gardevoirite",
    "Gengarite", "Glalitite", "Glimmoranite", "Golurkite", "Greninjite", "Gyaradosite",
    "Hawluchanite", "Heracronite", "Houndoominite", "Kangaskhanite", "Lopunnite", "Lucarionite",
    "Lucarionite Z", "Manectite", "Medichamite", "Meganiumite", "Meowsticite", "Pidgeotite",
    "Pinsirite", "Raichunite X", "Raichunite Y", "Sablenite", "Scizorite", "Scovillainite",
    "Sharpedonite", "Skarmorite", "Slowbronite", "Starminite", "Steelixite", "Tyranitarite",
    "Venusaurite", "Victreebelite",
    # Berries — pinch / type-resist / status cure
    "Aspear Berry", "Babiri Berry", "Charti Berry", "Cheri Berry", "Chesto Berry", "Chilan Berry",
    "Chople Berry", "Coba Berry", "Colbur Berry", "Custap Berry", "Enigma Berry", "Haban Berry",
    "Iapapa Berry", "Jaboca Berry", "Kasib Berry", "Kebia Berry", "Lansat Berry", "Leppa Berry",
    "Liechi Berry", "Lum Berry", "Maranga Berry", "Micle Berry", "Occa Berry", "Oran Berry",
    "Passho Berry", "Payapa Berry", "Pecha Berry", "Persim Berry", "Petaya Berry", "Rawst Berry",
    "Rindo Berry", "Roseli Berry", "Rowap Berry", "Salac Berry", "Shuca Berry", "Sitrus Berry",
    "Starf Berry", "Tanga Berry", "Wacan Berry", "Yache Berry",
    # Type-boosting held items
    "Black Belt", "Black Glasses", "Charcoal", "Dragon Fang", "Fairy Feather", "Hard Stone",
    "Magnet", "Metal Coat", "Miracle Seed", "Mystic Water", "Never-Melt Ice", "Poison Barb",
    "Sharp Beak", "Silk Scarf", "Silver Powder", "Soft Sand", "Spell Tag", "Twisted Spoon",
    # Competitive utility items
    "Air Balloon", "Assault Vest", "Big Root", "Binding Band", "Bright Powder", "Choice Band",
    "Choice Scarf", "Choice Specs", "Covert Cloak", "Eject Button", "Eject Pack", "Eviolite",
    "Expert Belt", "Float Stone", "Focus Band", "Focus Sash", "Heavy-Duty Boots", "King's Rock",
    "Leftovers", "Life Orb", "Light Ball", "Light Clay", "Loaded Dice", "Lucky Egg", "Lum Berry",
    "Mental Herb", "Metronome", "Mirror Herb", "Muscle Band", "Power Herb", "Punching Glove",
    "Quick Claw", "Razor Claw", "Red Card", "Rocky Helmet", "Safety Goggles", "Scope Lens",
    "Shed Shell", "Shell Bell", "Sticky Barb", "Throat Spray", "Toxic Orb", "Utility Umbrella",
    "Weakness Policy", "White Herb", "Wide Lens", "Wise Glasses", "Zoom Lens",
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
