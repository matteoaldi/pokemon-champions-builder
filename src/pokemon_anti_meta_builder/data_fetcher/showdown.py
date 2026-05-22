from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from pokemon_anti_meta_builder.format_rules.reg_ma import REG_MA_LEGAL_POKEMON
from pokemon_anti_meta_builder.meta_parser.normalizer import normalize_name, to_key


SHOWDOWN_POKEDEX_URL = "https://play.pokemonshowdown.com/data/pokedex.json"
SHOWDOWN_MOVES_URL = "https://play.pokemonshowdown.com/data/moves.json"
SHOWDOWN_LEARNSETS_URL = "https://play.pokemonshowdown.com/data/learnsets.json"

GEN_9_PREFIXES = ("9",)  # Pokemon Champions / VGC 2026 Reg M-A is gen 9 data


def sync_showdown_dex(
    output_path: str | Path = "data/raw/showdown_dex.json",
    insecure_ssl: bool = False,
    url: str = SHOWDOWN_POKEDEX_URL,
) -> Path:
    """Download Pokemon Showdown's public pokedex.json and slim it to Reg M-A entries.

    Showdown data is MIT-licensed. We keep only the fields we need (types,
    abilities, base stats) and we resolve each entry to the canonical species
    name we already use across the project.
    """
    context = ssl._create_unverified_context() if insecure_ssl else None
    request = Request(url, headers={"User-Agent": "pokemon-anti-meta-builder/0.1"})
    with urlopen(request, timeout=60, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))

    pokemon, mega_forms = _extract_legal_entries(payload)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {"source": url, "pokemon": pokemon, "mega_forms": mega_forms},
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return destination


def _extract_legal_entries(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (base_species_list, mega_forms_list) for Reg M-A entries."""
    legal_keys = {to_key(name) for name in REG_MA_LEGAL_POKEMON}
    by_species: dict[str, dict[str, Any]] = {}
    mega_forms: dict[str, dict[str, Any]] = {}

    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        species = entry.get("name")
        if not species:
            continue
        base = entry.get("baseSpecies") or species
        if to_key(base) not in legal_keys:
            continue

        slim = _slim(entry)
        canonical_base = normalize_name(base)
        slim_name = entry.get("name") or canonical_base
        forme = entry.get("forme") or ""
        required_item = entry.get("requiredItem") or ""

        if "Mega" in forme or "-Mega" in slim_name:
            mega_slim = dict(slim)
            mega_slim["name"] = slim_name
            mega_slim["base_species"] = canonical_base
            mega_slim["required_item"] = required_item
            mega_forms[slim_name] = mega_slim

        existing = by_species.get(canonical_base)
        is_base = _is_base_form(entry, base)
        if existing is None or is_base:
            base_slim = dict(slim)
            base_slim["name"] = canonical_base
            base_slim["alt_forms"] = sorted(set((existing or {}).get("alt_forms", []) + [slim_name]))
            by_species[canonical_base] = base_slim
        else:
            existing.setdefault("alt_forms", []).append(slim_name)
            existing["alt_forms"] = sorted(set(existing["alt_forms"]))

    pokemon = sorted(by_species.values(), key=lambda item: item["name"])
    megas = sorted(mega_forms.values(), key=lambda m: m["name"])
    return pokemon, megas


def _slim(entry: dict[str, Any]) -> dict[str, Any]:
    abilities = entry.get("abilities") or {}
    return {
        "name": entry.get("name", ""),
        "types": [t.lower() for t in entry.get("types") or []],
        "abilities": [abilities[k] for k in sorted(abilities.keys()) if abilities.get(k)],
        "base_stats": entry.get("baseStats") or {},
        "num": entry.get("num"),
        "alt_forms": [],
    }


def _is_base_form(entry: dict[str, Any], base: str) -> bool:
    return entry.get("name") == base or not entry.get("forme")


def sync_showdown_moves(
    moves_output: str | Path = "data/raw/showdown_moves.json",
    learnsets_output: str | Path = "data/raw/showdown_learnsets.json",
    insecure_ssl: bool = False,
    moves_url: str = SHOWDOWN_MOVES_URL,
    learnsets_url: str = SHOWDOWN_LEARNSETS_URL,
) -> tuple[Path, Path]:
    """Download Showdown moves.json + learnsets.json and slim them to gen 9 / Reg M-A.

    Outputs two files:
      - moves_output: dict keyed by display name with full metadata (type,
        category, basePower, accuracy, priority, target, flags, secondary).
      - learnsets_output: dict keyed by display name with the gen-9 legal move
        list (level-up + TM + tutor + egg + event from gen 9 entries).
    """
    context = ssl._create_unverified_context() if insecure_ssl else None
    headers = {"User-Agent": "pokemon-anti-meta-builder/0.1"}

    moves_raw = _download_json(moves_url, headers, context)
    learnsets_raw = _download_json(learnsets_url, headers, context)

    legal_keys = {to_key(name) for name in REG_MA_LEGAL_POKEMON}

    learnsets_slim: dict[str, list[str]] = {}
    used_move_ids: set[str] = set()
    for showdown_id, entry in learnsets_raw.items():
        if not isinstance(entry, dict):
            continue
        species_key = to_key(showdown_id)
        if species_key not in legal_keys:
            continue
        learnset = entry.get("learnset") or {}
        gen9_moves = sorted({move_id for move_id, sources in learnset.items() if _is_gen9(sources)})
        if not gen9_moves:
            continue
        display = _species_display(showdown_id)
        learnsets_slim[display] = [_move_display(moves_raw.get(mid, {}), mid) for mid in gen9_moves]
        used_move_ids.update(gen9_moves)

    moves_slim: dict[str, dict[str, Any]] = {}
    for move_id, raw in moves_raw.items():
        if move_id not in used_move_ids or not isinstance(raw, dict):
            continue
        display = _move_display(raw, move_id)
        moves_slim[display] = _slim_move(raw)

    moves_path = Path(moves_output)
    learnsets_path = Path(learnsets_output)
    moves_path.parent.mkdir(parents=True, exist_ok=True)
    learnsets_path.parent.mkdir(parents=True, exist_ok=True)
    moves_path.write_text(
        json.dumps({"source": moves_url, "moves": moves_slim}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    learnsets_path.write_text(
        json.dumps({"source": learnsets_url, "learnsets": learnsets_slim}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return moves_path, learnsets_path


def _download_json(url: str, headers: dict[str, str], context: Any) -> dict[str, Any]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=120, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_gen9(sources: Any) -> bool:
    if not isinstance(sources, list):
        return False
    return any(isinstance(s, str) and s.startswith(GEN_9_PREFIXES) for s in sources)


def _species_display(showdown_id: str) -> str:
    return normalize_name(showdown_id)


def _move_display(raw: dict[str, Any], move_id: str) -> str:
    name = raw.get("name")
    if isinstance(name, str) and name:
        return name
    return normalize_name(move_id)


_TARGET_TO_SPREAD = {
    "allAdjacent": True,
    "allAdjacentFoes": True,
    "all": True,
    "foeSide": True,
    "allySide": True,
}


def _slim_move(raw: dict[str, Any]) -> dict[str, Any]:
    category = str(raw.get("category", "")).lower()
    target = str(raw.get("target", "normal"))
    move_type = str(raw.get("type", "")).lower()
    return {
        "type": move_type,
        "category": category,
        "bp": int(raw.get("basePower") or 0),
        "accuracy": _accuracy(raw.get("accuracy")),
        "priority": int(raw.get("priority") or 0),
        "target": target,
        "spread": bool(_TARGET_TO_SPREAD.get(target, False)),
        "flags": dict(raw.get("flags") or {}),
        "secondary": _secondary(raw.get("secondary")),
        "pp": int(raw.get("pp") or 0),
        "num": raw.get("num"),
    }


def _accuracy(value: Any) -> int | bool:
    if value is True or value == "true":
        return True
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _secondary(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, list):
        return [_secondary(item) for item in value]
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if not callable(v)}
    return None


SMOGON_CALC_URLS = (
    "https://cdn.jsdelivr.net/npm/@smogon/calc/dist/index.iife.js",
    "https://unpkg.com/@smogon/calc/dist/index.iife.js",
    "https://cdn.jsdelivr.net/npm/@smogon/calc/dist/index.global.js",
)


def sync_smogon_calc_bundle(
    output_path: str | Path = "src/pokemon_anti_meta_builder/web/static/vendor/calc.js",
    insecure_ssl: bool = False,
) -> Path:
    """Best-effort download of the @smogon/calc browser bundle.

    Smogon does not always publish a ready-to-use IIFE bundle; this function
    tries a few well-known CDN URLs in order and saves the first success.
    Falls back with a clear error otherwise. The fallback is fine: the UI
    keeps using the Python lite calc.
    """
    context = ssl._create_unverified_context() if insecure_ssl else None
    last_error: Exception | None = None
    for url in SMOGON_CALC_URLS:
        try:
            request = Request(url, headers={"User-Agent": "pokemon-anti-meta-builder/0.1"})
            with urlopen(request, timeout=60, context=context) as response:
                data = response.read()
            destination = Path(output_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            return destination
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(
        f"Could not download @smogon/calc bundle from known CDNs ({last_error}). "
        "Build one locally via `npx esbuild @smogon/calc/index.ts --bundle --format=iife "
        "--global-name=calc --outfile=src/pokemon_anti_meta_builder/web/static/vendor/calc.js`."
    )


def load_showdown_dex(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("pokemon", [])
    if isinstance(payload, list):
        return payload
    return []


def load_showdown_mega_forms(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("mega_forms", [])
    return []


def load_showdown_moves(path: str | Path) -> dict[str, dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("moves", {}) or {}
    return {}


def load_showdown_learnsets(path: str | Path) -> dict[str, list[str]]:
    source = Path(path)
    if not source.exists():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("learnsets", {}) or {}
    return {}
