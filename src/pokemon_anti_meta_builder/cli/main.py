from __future__ import annotations

import argparse
from pathlib import Path

from pokemon_anti_meta_builder.data_fetcher import (
    DEFAULT_REG_MA_FORMAT,
    download_url,
    smogon_chaos_url,
    sync_pokekipe_meta,
    sync_showdown_dex,
    sync_showdown_moves,
    sync_smogon_calc_bundle,
)
from pokemon_anti_meta_builder.web.server import run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pokemon-anti-meta-builder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="Download a public stats file by URL or Smogon chaos coordinates.")
    fetch.add_argument("--url", help="Direct public URL to download.")
    fetch.add_argument("--smogon-month", help="Smogon month, for example 2026-04.")
    fetch.add_argument("--smogon-format", help="Smogon format id, for example gen9vgc2026regma.")
    fetch.add_argument("--rating", type=int, default=0)
    fetch.add_argument("--output", required=True)

    sync = subparsers.add_parser("sync-meta", help="Build a local CSV from Pokekipe public Reg M-A data.")
    sync.add_argument("--source", choices=["pokekipe"], default="pokekipe")
    sync.add_argument("--source-format", default=DEFAULT_REG_MA_FORMAT)
    sync.add_argument("--month", help="Optional YYYY-MM snapshot.")
    sync.add_argument("--elo-cutoff", type=int, default=1760)
    sync.add_argument("--limit", type=int, default=60)
    sync.add_argument("--sleep", type=float, default=1.1, help="Delay between per-Pokemon API calls to respect anonymous rate limits.")
    sync.add_argument("--output", default="data/raw/reg_ma_pokekipe.csv")
    sync.add_argument("--api-key", help="Optional Pokekipe API key for higher rate limits.")
    sync.add_argument("--insecure", action="store_true", help="Disable TLS verification only if local Python certificates are broken.")

    sync_dex = subparsers.add_parser(
        "sync-dex",
        help="Download Pokemon Showdown's pokedex.json and slim it to Reg M-A entries.",
    )
    sync_dex.add_argument("--output", default="data/raw/showdown_dex.json")
    sync_dex.add_argument("--insecure", action="store_true")

    sync_moves = subparsers.add_parser(
        "sync-moves",
        help="Download Showdown moves.json and learnsets.json, slim to gen 9 Reg M-A.",
    )
    sync_moves.add_argument("--moves-output", default="data/raw/showdown_moves.json")
    sync_moves.add_argument("--learnsets-output", default="data/raw/showdown_learnsets.json")
    sync_moves.add_argument("--insecure", action="store_true")

    sync_pika = subparsers.add_parser(
        "sync-pikalytics",
        help="Fetch Pikalytics AI markdown for every species in the dex (off-meta included).",
    )
    sync_pika.add_argument("--dex", default="data/raw/showdown_dex.json", help="Showdown dex slim used as the species universe.")
    sync_pika.add_argument("--format-id", default="gen9championsvgc2026regma", help="Pikalytics format slug.")
    sync_pika.add_argument("--output", default="data/raw/pikalytics_sets.json")
    sync_pika.add_argument("--sleep", type=float, default=0.4, help="Polite delay between requests in seconds.")
    sync_pika.add_argument("--only-off-meta", action="store_true", help="Skip species that already have Pokekipe data in --meta-csv.")
    sync_pika.add_argument("--refresh", action="store_true", help="Re-fetch every species even if already cached (refresh stale data).")
    sync_pika.add_argument("--meta-csv", default="data/raw/reg_ma_pokekipe.csv", help="Pokekipe CSV used to detect on-meta species when --only-off-meta is set.")
    sync_pika.add_argument("--insecure", action="store_true")

    sync_calc = subparsers.add_parser(
        "sync-calc",
        help="Download the @smogon/calc browser bundle into the local UI assets.",
    )
    sync_calc.add_argument(
        "--output",
        default="src/pokemon_anti_meta_builder/web/static/vendor/calc.js",
    )
    sync_calc.add_argument("--insecure", action="store_true")

    serve = subparsers.add_parser("serve", help="Run the local interactive team builder UI.")
    serve.add_argument("--format", default="reg-ma")
    serve.add_argument("--input", default="data/raw/example_meta.csv")
    serve.add_argument("--dex", default="data/raw/showdown_dex.json", help="Optional Showdown dex slim JSON to enable off-meta picks.")
    serve.add_argument("--learnsets", default="data/raw/showdown_learnsets.json", help="Optional Showdown learnsets slim JSON to filter calc moves to legal ones.")
    serve.add_argument("--teams-dir", default="data/teams", help="Directory where saved teams are persisted as JSON files.")
    serve.add_argument("--pikalytics", default="data/raw/pikalytics_sets.json", help="Optional Pikalytics sets cache to enrich off-meta mons.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    if args.command == "fetch":
        return _fetch(args)
    if args.command == "sync-meta":
        return _sync_meta(args)
    if args.command == "sync-dex":
        return _sync_dex(args)
    if args.command == "sync-moves":
        return _sync_moves(args)
    if args.command == "sync-calc":
        return _sync_calc(args)
    if args.command == "sync-pikalytics":
        return _sync_pikalytics(args)
    if args.command == "serve":
        pikalytics_path = args.pikalytics if Path(args.pikalytics).exists() else None
        run_server(
            args.input,
            args.host,
            args.port,
            args.format,
            dex_path=args.dex,
            learnsets_path=args.learnsets,
            teams_dir=args.teams_dir,
            pikalytics_path=pikalytics_path,
        )
        return 0
    return 1


def _fetch(args: argparse.Namespace) -> int:
    url = args.url
    if not url:
        if not args.smogon_month or not args.smogon_format:
            raise SystemExit("Provide --url or both --smogon-month and --smogon-format.")
        url = smogon_chaos_url(args.smogon_month, args.smogon_format, args.rating)
    destination = download_url(url, args.output)
    print(f"Downloaded {url} to {destination}")
    return 0


def _sync_dex(args: argparse.Namespace) -> int:
    destination = sync_showdown_dex(output_path=args.output, insecure_ssl=args.insecure)
    print(f"Wrote Showdown Reg M-A dex slice to {destination}")
    print("Attribution: data from Pokemon Showdown (MIT license).")
    return 0


def _sync_moves(args: argparse.Namespace) -> int:
    moves_path, learnsets_path = sync_showdown_moves(
        moves_output=args.moves_output,
        learnsets_output=args.learnsets_output,
        insecure_ssl=args.insecure,
    )
    print(f"Wrote moves to {moves_path}")
    print(f"Wrote learnsets to {learnsets_path}")
    print("Attribution: data from Pokemon Showdown (MIT license).")
    return 0


def _sync_calc(args: argparse.Namespace) -> int:
    destination = sync_smogon_calc_bundle(output_path=args.output, insecure_ssl=args.insecure)
    print(f"Wrote @smogon/calc bundle to {destination}")
    print("Attribution: @smogon/calc (MIT license).")
    return 0


def _sync_meta(args: argparse.Namespace) -> int:
    if args.source != "pokekipe":
        raise SystemExit(f"Unsupported source: {args.source}")
    destination = sync_pokekipe_meta(
        output_path=args.output,
        format_id=args.source_format,
        limit=args.limit,
        month=args.month,
        elo_cutoff=args.elo_cutoff,
        sleep_seconds=args.sleep,
        api_key=args.api_key,
        insecure_ssl=args.insecure,
    )
    print(f"Wrote Pokekipe meta snapshot to {destination}")
    print("Attribution: data from Pokekipe Public API (CC BY 4.0), derived from Smogon public usage stats.")
    return 0


def _sync_pikalytics(args: argparse.Namespace) -> int:
    """Download Pikalytics AI markdown for every species in the dex.

    The endpoint is documented at /llms.txt (CC BY-NC 4.0). We respect a
    polite delay between requests and cache results to disk so subsequent
    runs only refresh missing entries.
    """
    import json
    from pokemon_anti_meta_builder.data_fetcher.pikalytics import (
        fetch_and_parse,
        save_cache,
        load_cache,
    )

    dex_path = Path(args.dex)
    if not dex_path.exists():
        raise SystemExit(f"Dex file not found: {dex_path}. Run sync-dex first.")
    payload = json.loads(dex_path.read_text(encoding="utf-8"))
    species_all = [p["name"] for p in payload.get("pokemon", [])]

    skip: set[str] = set()
    if args.only_off_meta and Path(args.meta_csv).exists():
        # Skip species that already have Pokekipe stats: read column 1 of CSV.
        import csv
        with Path(args.meta_csv).open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name = (row.get("pokemon") or "").strip()
                if name:
                    skip.add(name)

    species = [s for s in species_all if s not in skip]
    existing = load_cache(args.output)
    print(f"Pikalytics sync: {len(species)} species to fetch ({len(existing)} already cached).")

    import time
    count_new = 0
    count_404 = 0
    for i, name in enumerate(species, 1):
        if name in existing and not args.refresh:
            continue
        try:
            data = fetch_and_parse(name, format_id=args.format_id, insecure_ssl=args.insecure)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i:3}/{len(species)}] {name}: ERROR {exc}")
            time.sleep(args.sleep)
            continue
        if data is None:
            count_404 += 1
            print(f"  [{i:3}/{len(species)}] {name}: 404 (skipped)")
        else:
            existing[name] = data
            count_new += 1
            mv = ", ".join(m["name"] for m in data.get("moves", [])[:4])
            print(f"  [{i:3}/{len(species)}] {name}: ok ({mv})")
            # Persist incrementally so a crash doesn't lose progress
            save_cache(existing, args.output, format_id=args.format_id)
        time.sleep(args.sleep)

    save_cache(existing, args.output, format_id=args.format_id)
    print(f"Wrote {len(existing)} entries to {args.output} ({count_new} new, {count_404} 404).")
    print("Attribution: data from Pikalytics (CC BY-NC 4.0), https://www.pikalytics.com")
    return 0
