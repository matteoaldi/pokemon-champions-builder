"""Pikalytics AI markdown endpoint fetcher + parser.

Pikalytics exposes a markdown endpoint per Pokemon at
    https://www.pikalytics.com/ai/pokedex/<format_id>/<species>
documented in /llms.txt and /llms-full.txt as the official AI-readable
view of their data. License: CC BY-NC 4.0.

This module fetches that markdown and parses out the structured fields
we need: top moves, abilities, items, plus the most common EV spread and
nature, and base stats. We keep parsing tolerant: each section is
optional and any missing field is returned as None / [].
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PIKALYTICS_ENDPOINT = "https://www.pikalytics.com/ai/pokedex/{format_id}/{species}"
DEFAULT_FORMAT_ID = "gen9championsvgc2026regma"
USER_AGENT = "pokemon-anti-meta-builder/0.1 (matteo aldi; personal hobby; respects CC BY-NC 4.0)"


def fetch_markdown(species: str, format_id: str = DEFAULT_FORMAT_ID, insecure_ssl: bool = False) -> str | None:
    """Fetch the raw markdown for `species`. Returns None on 404."""
    url = PIKALYTICS_ENDPOINT.format(format_id=format_id, species=species)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/markdown"})
    context = ssl._create_unverified_context() if insecure_ssl else None
    try:
        with urllib.request.urlopen(req, timeout=20, context=context) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


_PCT_LINE_RE = re.compile(r"^- \*\*(?P<name>[^*]+)\*\*: (?P<pct>[\d.]+)%")
_SPREAD_RE = re.compile(
    r"\*\*(?P<nature>[A-Z][a-z]+)\*\* nature with an EV spread of `(?P<spread>[\d/]+)`"
)
_PCT_IN_TEXT_RE = re.compile(r"accounts for (?P<pct>[\d.]+)%")
_BASE_STAT_RE = re.compile(r"^\| (?P<key>HP|Attack|Defense|Sp\. Atk|Sp\. Def|Speed) \| (?P<value>\d+) \|")
_USAGE_RE = re.compile(r"^\| \*\*Usage\*\* \| (?P<pct>[\d.]+)% \|")
_WIN_RE = re.compile(r"^\| \*\*Win Rate\*\* \| (?P<pct>[\d.]+)% \|")


def parse_markdown(markdown: str) -> dict[str, Any]:
    """Parse the Pikalytics AI markdown into a structured dict.

    Returned shape (all fields optional):
        {
          "usage": float, "winrate": float,
          "moves":     [{"name": str, "pct": float}, ...],
          "abilities": [{"name": str, "pct": float}, ...],
          "items":     [{"name": str, "pct": float}, ...],
          "topNature": "Adamant",
          "topSpread": "2/32/0/0/0/32",
          "topSpreadPct": 36.577,
          "baseStats": {"hp": ..., "atk": ..., "def": ..., "spa": ..., "spd": ..., "spe": ...},
        }
    """
    out: dict[str, Any] = {
        "moves": [], "abilities": [], "items": [],
        "topNature": None, "topSpread": None, "topSpreadPct": None,
        "usage": None, "winrate": None,
        "baseStats": {},
    }
    section: str | None = None
    base_stat_keys = {"HP": "hp", "Attack": "atk", "Defense": "def", "Sp. Atk": "spa", "Sp. Def": "spd", "Speed": "spe"}
    for line in markdown.splitlines():
        stripped = line.strip()
        # Section headers
        if stripped.startswith("## Common Moves"):
            section = "moves"; continue
        if stripped.startswith("## Common Abilities"):
            section = "abilities"; continue
        if stripped.startswith("## Common Items"):
            section = "items"; continue
        if stripped.startswith("## "):
            section = None
        # Quick info table
        if out["usage"] is None:
            m = _USAGE_RE.match(line)
            if m: out["usage"] = float(m.group("pct"))
        if out["winrate"] is None:
            m = _WIN_RE.match(line)
            if m: out["winrate"] = float(m.group("pct"))
        # Base stats
        m = _BASE_STAT_RE.match(line)
        if m:
            out["baseStats"][base_stat_keys[m.group("key")]] = int(m.group("value"))
        # Section list lines
        if section in ("moves", "abilities", "items"):
            m = _PCT_LINE_RE.match(stripped)
            if m and m.group("name") != "Other":
                out[section].append({"name": m.group("name").strip(), "pct": float(m.group("pct"))})
        # Top spread (in the FAQ section)
        m = _SPREAD_RE.search(line)
        if m and out["topSpread"] is None:
            out["topNature"] = m.group("nature")
            out["topSpread"] = m.group("spread")
            pct_match = _PCT_IN_TEXT_RE.search(line)
            if pct_match:
                out["topSpreadPct"] = float(pct_match.group("pct"))
    return out


def fetch_and_parse(species: str, format_id: str = DEFAULT_FORMAT_ID, insecure_ssl: bool = False) -> dict[str, Any] | None:
    md = fetch_markdown(species, format_id=format_id, insecure_ssl=insecure_ssl)
    if md is None:
        return None
    return parse_markdown(md)


def fetch_many(
    species_list: list[str],
    format_id: str = DEFAULT_FORMAT_ID,
    insecure_ssl: bool = False,
    delay_sec: float = 0.3,
    on_progress=None,
) -> dict[str, dict[str, Any]]:
    """Fetch + parse a batch of species. Returns {species: parsed_dict}.

    `delay_sec` is a polite throttle between requests (no API key, public
    endpoint). 404s are skipped silently.
    """
    out: dict[str, dict[str, Any]] = {}
    for i, species in enumerate(species_list, 1):
        try:
            parsed = fetch_and_parse(species, format_id=format_id, insecure_ssl=insecure_ssl)
        except Exception as exc:  # noqa: BLE001 - log and continue, partial cache better than none
            if on_progress: on_progress(i, len(species_list), species, error=str(exc))
            continue
        if parsed is not None:
            out[species] = parsed
        if on_progress: on_progress(i, len(species_list), species)
        time.sleep(delay_sec)
    return out


def save_cache(data: dict[str, dict[str, Any]], path: str | Path, format_id: str = DEFAULT_FORMAT_ID) -> None:
    payload = {
        "source": "pikalytics",
        "license": "CC BY-NC 4.0",
        "source_url": f"https://www.pikalytics.com/pokedex/{format_id}",
        "format_id": format_id,
        "pokemon": data,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cache(path: str | Path) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return {}
    payload = json.loads(p.read_text(encoding="utf-8"))
    return payload.get("pokemon", {}) if isinstance(payload, dict) else {}
