from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen


def smogon_chaos_url(month: str, format_id: str, rating: int = 0) -> str:
    """Build a public Smogon chaos stats URL, e.g. 2026-04/gen9vgc2026regma-0.json."""
    normalized_month = month.strip("/")
    return f"https://www.smogon.com/stats/{normalized_month}/chaos/{format_id}-{rating}.json"


def download_url(url: str, output_path: str | Path, timeout: int = 30) -> Path:
    """Download a public stats file to disk.

    This intentionally accepts an explicit URL. Sites such as Pikalytics or
    MunchStats can change HTML/API surfaces; callers should isolate any scraper
    that produces the URL before passing it here.
    """
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=timeout) as response:
        destination.write_bytes(response.read())
    return destination
