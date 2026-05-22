from __future__ import annotations

import csv
import json
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pokemon_anti_meta_builder.meta_parser.normalizer import normalize_name, normalize_role, to_key


POKEKIPE_BASE_URL = "https://pokekipe.com/api/v1"
DEFAULT_REG_MA_FORMAT = "gen9championsvgc2026regma"


DISPLAY_BY_ID = {
    "aerialace": "Aerial Ace",
    "aquajet": "Aqua Jet",
    "bitterblade": "Bitter Blade",
    "bodypress": "Body Press",
    "bravebird": "Brave Bird",
    "calmmind": "Calm Mind",
    "closecombat": "Close Combat",
    "coaching": "Coaching",
    "darkestlariat": "Darkest Lariat",
    "dazzlinggleam": "Dazzling Gleam",
    "direclaw": "Dire Claw",
    "dracometeor": "Draco Meteor",
    "dragondance": "Dragon Dance",
    "dragonclaw": "Dragon Claw",
    "earthpower": "Earth Power",
    "earthquake": "Earthquake",
    "electroshot": "Electro Shot",
    "encore": "Encore",
    "fakeout": "Fake Out",
    "feint": "Feint",
    "flipturn": "Flip Turn",
    "flareblitz": "Flare Blitz",
    "flashcannon": "Flash Cannon",
    "foulplay": "Foul Play",
    "glaiverush": "Glaive Rush",
    "gunkshot": "Gunk Shot",
    "heatwave": "Heat Wave",
    "helpinghand": "Helping Hand",
    "hurricane": "Hurricane",
    "hypervoice": "Hyper Voice",
    "icywind": "Icy Wind",
    "ironhead": "Iron Head",
    "kowtowcleave": "Kowtow Cleave",
    "knockoff": "Knock Off",
    "lastrespects": "Last Respects",
    "lifedew": "Life Dew",
    "lightofruin": "Light of Ruin",
    "liquidation": "Liquidation",
    "lowkick": "Low Kick",
    "matchagotcha": "Matcha Gotcha",
    "moonblast": "Moonblast",
    "mortalspin": "Mortal Spin",
    "partingshot": "Parting Shot",
    "protect": "Protect",
    "ragepowder": "Rage Powder",
    "rockslide": "Rock Slide",
    "rocktomb": "Rock Tomb",
    "scaleshot": "Scale Shot",
    "scorchingsands": "Scorching Sands",
    "shadowball": "Shadow Ball",
    "sleeppowder": "Sleep Powder",
    "sludgebomb": "Sludge Bomb",
    "solarbeam": "Solar Beam",
    "spore": "Spore",
    "sparklingaria": "Sparkling Aria",
    "stompingtantrum": "Stomping Tantrum",
    "suckerpunch": "Sucker Punch",
    "swordsdance": "Swords Dance",
    "tailwind": "Tailwind",
    "taunt": "Taunt",
    "throatchop": "Throat Chop",
    "trickroom": "Trick Room",
    "uturn": "U-turn",
    "voltswitch": "Volt Switch",
    "waterfall": "Waterfall",
    "wavecrash": "Wave Crash",
    "weatherball": "Weather Ball",
    "willowisp": "Will-O-Wisp",
    "blackbelt": "Black Belt",
    "sitrusberry": "Sitrus Berry",
    "chopleberry": "Chople Berry",
    "choicescarf": "Choice Scarf",
    "cobaberry": "Coba Berry",
    "colburberry": "Colbur Berry",
    "shucaberry": "Shuca Berry",
    "leftovers": "Leftovers",
    "lumberry": "Lum Berry",
    "whiteherb": "White Herb",
    "passhoberry": "Passho Berry",
    "charcoal": "Charcoal",
    "brightpowder": "Bright Powder",
    "blackglasses": "Black Glasses",
    "mentalherb": "Mental Herb",
    "quickclaw": "Quick Claw",
    "chartiberry": "Charti Berry",
    "focussash": "Focus Sash",
    "habanberry": "Haban Berry",
    "kasibberry": "Kasib Berry",
    "kingsrock": "King's Rock",
    "metalcoat": "Metal Coat",
    "miracleseed": "Miracle Seed",
    "mysticwater": "Mystic Water",
    "occaberry": "Occa Berry",
    "roseliberry": "Roseli Berry",
    "softsand": "Soft Sand",
    "sharpbeak": "Sharp Beak",
    "tyranitarite": "Tyranitarite",
    "garchompite": "Garchompite",
    "gardevoirite": "Gardevoirite",
    "gengarite": "Gengarite",
    "glimmoranite": "Glimmoranite",
    "charizarditex": "Charizardite X",
    "charizarditey": "Charizardite Y",
    "yacheberry": "Yache Berry",
    "adaptability": "Adaptability",
    "defiant": "Defiant",
    "drought": "Drought",
    "fairyaura": "Fairy Aura",
    "hospitality": "Hospitality",
    "intimidate": "Intimidate",
    "moldbreaker": "Mold Breaker",
    "poisontouch": "Poison Touch",
    "pressure": "Pressure",
    "prankster": "Prankster",
    "roughskin": "Rough Skin",
    "sandstream": "Sand Stream",
    "sandrush": "Sand Rush",
    "supremeoverlord": "Supreme Overlord",
    "swiftswim": "Swift Swim",
    "stamina": "Stamina",
    "torrent": "Torrent",
    "galewings": "Gale Wings",
    "armortail": "Armor Tail",
}

MEGA_ITEM_BY_BASE = {
    "Abomasnow": "Abomasite",
    "Absol": "Absolite",
    "Aerodactyl": "Aerodactylite",
    "Aggron": "Aggronite",
    "Alakazam": "Alakazite",
    "Altaria": "Altarianite",
    "Ampharos": "Ampharosite",
    "Audino": "Audinite",
    "Banette": "Banettite",
    "Beedrill": "Beedrillite",
    "Blastoise": "Blastoisinite",
    "Camerupt": "Cameruptite",
    "Chandelure": "Chandelurite",
    "Charizard-Mega-X": "Charizardite X",
    "Charizard-Mega-Y": "Charizardite Y",
    "Charizard": "Charizardite Y",
    "Chesnaught": "Chesnaughtite",
    "Chimecho": "Chimechite",
    "Clefable": "Clefablite",
    "Crabominable": "Crabominite",
    "Delphox": "Delphoxite",
    "Dragonite": "Dragoninite",
    "Drampa": "Drampanite",
    "Emboar": "Emboarite",
    "Excadrill": "Excadrite",
    "Feraligatr": "Feraligite",
    "Floette": "Floettite",
    "Froslass": "Froslassite",
    "Gallade": "Galladite",
    "Garchomp": "Garchompite",
    "Gardevoir": "Gardevoirite",
    "Gengar": "Gengarite",
    "Glalie": "Glalitite",
    "Glimmora": "Glimmoranite",
    "Golurk": "Golurkite",
    "Greninja": "Greninjite",
    "Gyarados": "Gyaradosite",
    "Hawlucha": "Hawluchanite",
    "Heracross": "Heracronite",
    "Houndoom": "Houndoominite",
    "Kangaskhan": "Kangaskhanite",
    "Lopunny": "Lopunnite",
    "Lucario": "Lucarionite",
    "Manectric": "Manectite",
    "Medicham": "Medichamite",
    "Meganium": "Meganiumite",
    "Meowstic": "Meowsticite",
    "Pidgeot": "Pidgeotite",
    "Pinsir": "Pinsirite",
    "Sableye": "Sablenite",
    "Scizor": "Scizorite",
    "Scovillain": "Scovillainite",
    "Sharpedo": "Sharpedonite",
    "Skarmory": "Skarmorite",
    "Slowbro": "Slowbronite",
    "Starmie": "Starminite",
    "Steelix": "Steelixite",
    "Tyranitar": "Tyranitarite",
    "Venusaur": "Venusaurite",
    "Victreebel": "Victreebelite",
}

ROLE_MAP = {
    "fake_out_user": "disruption",
    "intimidate_user": "disruption",
    "bulky_pivot": "pivot",
    "physical_wallbreaker": "physical-attacker",
    "special_wallbreaker": "special-attacker",
    "spread_attacker": "spread-attacker",
    "priority_attacker": "physical-attacker",
    "trick_room_setter": "speed-control",
    "tailwind_setter": "speed-control",
    "redirector": "support",
}


class PokekipeClient:
    def __init__(self, api_key: str | None = None, base_url: str = POKEKIPE_BASE_URL, insecure_ssl: bool = False):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.context = ssl._create_unverified_context() if insecure_ssl else None

    def get_json(self, path: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(f"{self.base_url}{path}{query}", headers=self._headers())
        for attempt in range(retries + 1):
            try:
                with urlopen(request, timeout=30, context=self.context) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code != 429 or attempt >= retries:
                    raise
                retry_after = int(exc.headers.get("Retry-After", "60"))
                time.sleep(max(retry_after, 5))
        raise RuntimeError("unreachable")

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "pokemon-anti-meta-builder/0.1"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers


def sync_pokekipe_meta(
    output_path: str | Path,
    format_id: str = DEFAULT_REG_MA_FORMAT,
    limit: int = 60,
    month: str | None = None,
    elo_cutoff: int | None = 1760,
    sleep_seconds: float = 1.1,
    api_key: str | None = None,
    insecure_ssl: bool = False,
) -> Path:
    client = PokekipeClient(api_key=api_key, insecure_ssl=insecure_ssl)
    params: dict[str, Any] = {"limit": limit}
    if month:
        params["month"] = month
    if elo_cutoff is not None:
        params["elo_cutoff"] = elo_cutoff
    overview = client.get_json(f"/meta/{quote(format_id)}", params)

    rows = []
    for entry in overview.get("pokemon", [])[:limit]:
        name = entry.get("pokemon_name") or entry.get("name")
        if not name:
            continue
        details = client.get_json(
            f"/pokemon/{quote(name)}/{quote(format_id)}",
            {k: v for k, v in {"month": month, "elo_cutoff": elo_cutoff, "tolerate_missing": "true"}.items() if v is not None},
        )
        if not details:
            continue
        rows.append(_details_to_row(details, entry))
        time.sleep(sleep_seconds)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "pokemon",
                "usage",
                "winrate",
                "types",
                "items",
                "abilities",
                "moves",
                "ev_spreads",
                "natures",
                "teammates",
                "checks_counters",
                "roles",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return destination


def _details_to_row(details: dict[str, Any], overview: dict[str, Any]) -> dict[str, str]:
    reference = details.get("reference") or {}
    type1 = reference.get("type1") or overview.get("type1")
    type2 = reference.get("type2") or overview.get("type2")
    spreads = details.get("spreads") or []
    raw_name = details.get("pokemon_name") or overview.get("pokemon_name") or overview.get("name")
    pokemon_name = _base_species(_display(raw_name))
    item_field = _weighted(details.get("items", []), "name", "usage")
    mega_item = _mega_item_for(_display(raw_name), pokemon_name)
    if mega_item and mega_item not in item_field:
        item_field = f"{mega_item}:100.00" + (f";{item_field}" if item_field else "")
    roles = [ROLE_MAP.get(role, normalize_role(role)) for role in details.get("roles") or overview.get("roles") or []]
    return {
        "pokemon": pokemon_name,
        "usage": f"{_percent(details.get('usage_rate') or overview.get('usage_rate') or overview.get('usage') or 0):.2f}",
        "winrate": "",
        "types": ";".join(t.lower() for t in (type1, type2) if t),
        "items": item_field,
        "abilities": _weighted(details.get("abilities", []), "name", "usage"),
        "moves": _weighted(details.get("moves", []), "name", "usage"),
        "ev_spreads": _weighted(spreads, "spread", "usage", display=False),
        "natures": _natures(spreads),
        "teammates": _weighted(details.get("teammates", []), "name", "usage"),
        "checks_counters": _weighted(_checks_counters_source(details), "name", "usage"),
        "roles": ";".join(sorted(set(roles))),
    }


def _weighted(items: list[dict[str, Any]], name_key: str, usage_key: str, display: bool = True, limit: int = 12) -> str:
    parts = []
    for item in items[:limit]:
        name = item.get(name_key) or item.get("pokemon_name")
        if not name:
            continue
        value = _display(name) if display else str(name)
        parts.append(f"{value}:{_percent(item.get(usage_key, 0)):.2f}")
    return ";".join(parts)


def _natures(spreads: list[dict[str, Any]]) -> str:
    totals: dict[str, float] = {}
    for spread in spreads:
        raw = spread.get("spread") or ""
        if ":" not in raw:
            continue
        nature = raw.split(":", 1)[0]
        totals[nature] = totals.get(nature, 0) + _percent(spread.get("usage", 0))
    return ";".join(f"{normalize_name(k)}:{v:.2f}" for k, v in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:8])


def _percent(value: Any) -> float:
    number = float(value or 0)
    return number * 100 if 0 <= number <= 1 else number


def _display(value: Any) -> str:
    raw = str(value or "")
    key = to_key(raw)
    return DISPLAY_BY_ID.get(key) or normalize_name(raw)


def _base_species(name: str) -> str:
    if "-Mega-" in name:
        return name.split("-Mega-", 1)[0]
    if name.endswith("-Mega"):
        return name[: -len("-Mega")]
    return name


def _mega_item_for(display_name: str, base_name: str) -> str:
    if "-Mega" not in display_name:
        return ""
    return MEGA_ITEM_BY_BASE.get(display_name) or MEGA_ITEM_BY_BASE.get(base_name, "")


def _checks_counters_source(details: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("checks_counters", "checks_and_counters", "counters"):
        value = details.get(key)
        if value:
            return list(value)
    checks = list(details.get("checks") or [])
    counters = list(details.get("counters") or [])
    if not checks and not counters:
        return []
    merged: dict[str, float] = {}
    for entry in checks + counters:
        name = entry.get("name") or entry.get("pokemon_name")
        if not name:
            continue
        usage = float(entry.get("usage") or entry.get("score") or 0)
        merged[name] = max(merged.get(name, 0.0), usage)
    return [{"name": name, "usage": usage} for name, usage in merged.items()]
