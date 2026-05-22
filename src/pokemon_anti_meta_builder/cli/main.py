from __future__ import annotations

import argparse
from pathlib import Path

from pokemon_anti_meta_builder.data_fetcher import (
    DEFAULT_REG_MA_FORMAT,
    download_url,
    load_meta_file,
    smogon_chaos_url,
    sync_pokekipe_meta,
    sync_showdown_dex,
    sync_showdown_moves,
    sync_smogon_calc_bundle,
)
from pokemon_anti_meta_builder.format_rules import filter_legal_meta
from pokemon_anti_meta_builder.models import BuiltTeam
from pokemon_anti_meta_builder.set_builder import SetBuilder
from pokemon_anti_meta_builder.showdown_exporter import ShowdownExporter
from pokemon_anti_meta_builder.team_builder import TeamBuilder
from pokemon_anti_meta_builder.threat_analyzer import ThreatAnalyzer
from pokemon_anti_meta_builder.web.server import run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pokemon-anti-meta-builder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a deterministic six-Pokemon team.")
    build.add_argument("--format", default="reg-ma", help="Target format label. MVP supports reg-ma semantics.")
    build.add_argument("--input", required=True, help="Local meta CSV/JSON file.")
    build.add_argument("--output", required=True, help="Showdown export destination.")
    build.add_argument("--threats", type=int, default=10, help="Top N meta threats to analyze.")

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
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args)
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
    if args.command == "serve":
        run_server(
            args.input,
            args.host,
            args.port,
            args.format,
            dex_path=args.dex,
            learnsets_path=args.learnsets,
            teams_dir=args.teams_dir,
        )
        return 0
    return 1


def _build(args: argparse.Namespace) -> int:
    meta = load_meta_file(args.input)
    meta, legality_warnings = filter_legal_meta(meta, args.format)
    selected = TeamBuilder().select_team(meta)
    set_builder = SetBuilder()
    used_items: set[str] = set()
    members = []
    for mon in selected:
        member = set_builder.build_set(mon, used_items=used_items)
        members.append(member)
        if member.item:
            used_items.add(member.item)
    warnings = [*legality_warnings, *[warning for member in members for warning in member.warnings]]
    team = BuiltTeam(format_id=args.format, members=members, warnings=warnings)
    export = ShowdownExporter().export_team(team)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(export + "\n", encoding="utf-8")

    print("Generated team")
    print(export)
    print()
    print("Roles")
    for member in members:
        print(f"- {member.species}: {', '.join(member.roles)}. {member.explanation}")
    print()
    print(ThreatAnalyzer().analyze(members, meta, top_n=args.threats).render())
    print()
    print("Warnings")
    if warnings:
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("- none")
    print(f"\nWrote Showdown team to {output}")
    return 0


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
