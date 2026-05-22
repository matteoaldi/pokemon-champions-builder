from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pokemon_anti_meta_builder.ai_coach import AICoach
from pokemon_anti_meta_builder.damage_calc import DamageCalculator, MOVE_LIBRARY
from pokemon_anti_meta_builder.damage_calc.calculator import Combatant, Field
from pokemon_anti_meta_builder.recommendations import RecommendationService


WEB_DIR = Path(__file__).resolve().parent / "static"


def run_server(
    input_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    format_id: str = "reg-ma",
    dex_path: str | Path | None = None,
    learnsets_path: str | Path | None = None,
) -> None:
    service = RecommendationService(
        input_path=input_path,
        format_id=format_id,
        dex_path=dex_path,
        learnsets_path=learnsets_path,
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/catalog":
                self._json(service.catalog())
                return
            if parsed.path == "/api/state":
                query = parse_qs(parsed.query)
                archetype = query.get("archetype", ["balance"])[0]
                selected = _split_team(query.get("team", [""])[0])
                self._json(service.build_state(archetype, selected).as_dict())
                return
            if parsed.path == "/api/autobuild":
                # GET fallback: empty team
                self._json(service.auto_build().as_dict())
                return
            if parsed.path == "/api/counters":
                query = parse_qs(parsed.query)
                selected = _split_team(query.get("team", [""])[0])
                self._json(service.team_counters(selected))
                return
            if parsed.path == "/api/combatant":
                query = parse_qs(parsed.query)
                name = query.get("name", [""])[0]
                if not name:
                    self.send_error(400, "missing name")
                    return
                self._json(service.combatant_payload(name))
                return
            if parsed.path == "/api/calc/moves":
                self._json({"moves": sorted(MOVE_LIBRARY.keys())})
                return
            if parsed.path == "/api/options":
                query = parse_qs(parsed.query)
                name = query.get("name", [""])[0]
                if not name:
                    self.send_error(400, "missing name")
                    return
                self._json(service.edit_options(name))
                return
            if parsed.path == "/api/counter_lookup":
                query = parse_qs(parsed.query)
                name = query.get("name", [""])[0]
                if not name:
                    self.send_error(400, "missing name")
                    return
                self._json(service.counter_lookup(name))
                return
            if parsed.path == "/api/learnset":
                query = parse_qs(parsed.query)
                name = query.get("name", [""])[0]
                if not name:
                    self.send_error(400, "missing name")
                    return
                learnset = service.learnset_for(name)
                available = set(MOVE_LIBRARY.keys())
                self._json({
                    "name": name,
                    "moves": learnset,
                    "calcable": [move for move in learnset if move in available],
                    "hasLearnset": bool(learnset),
                })
                return
            self._static(parsed.path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body or "{}")
            if parsed.path == "/api/state":
                self._json(service.build_state(
                    payload.get("archetype", "balance"),
                    payload.get("selected", []),
                    payload.get("overrides") or {},
                ).as_dict())
                return
            if parsed.path == "/api/coach":
                state = service.build_state(
                    payload.get("archetype", "balance"),
                    payload.get("selected", []),
                    payload.get("overrides") or {},
                ).as_dict()
                self._json(AICoach().advise(state))
                return
            if parsed.path == "/api/counters":
                self._json(service.team_counters(
                    payload.get("selected", []),
                    overrides=payload.get("overrides") or {},
                ))
                return
            if parsed.path == "/api/autobuild":
                self._json(service.auto_build(
                    seed=payload.get("selected") or [],
                    overrides=payload.get("overrides") or {},
                ).as_dict())
                return
            if parsed.path == "/api/damage":
                self._json(_damage_response(payload))
                return
            self.send_error(404)

        def _static(self, path: str) -> None:
            relative = "index.html" if path in {"", "/"} else path.lstrip("/")
            target = (WEB_DIR / relative).resolve()
            if WEB_DIR.resolve() not in target.parents and target != WEB_DIR.resolve():
                self.send_error(403)
                return
            if not target.exists() or not target.is_file():
                self.send_error(404)
                return
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
            }.get(target.suffix, "application/octet-stream")
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, payload: object) -> None:
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Pokemon Anti Meta Builder UI: http://{host}:{port}")
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/example_meta.csv")
    parser.add_argument("--format", default="reg-ma")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    run_server(args.input, args.host, args.port, args.format)
    return 0


def _split_team(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _damage_response(payload: dict) -> dict:
    try:
        attacker_payload = payload.get("attacker", {})
        defender_payload = payload.get("defender", {})
        attacker = _combatant_from(attacker_payload)
        defender = _combatant_from(defender_payload)
        field = _field_from(payload.get("field", {}))
        move_name = payload.get("move", "")
        result = DamageCalculator().calculate(attacker, defender, move_name, field)
        return {
            "ok": True,
            "result": result.as_dict(),
            "stats": {
                "attacker": attacker.stats_breakdown(),
                "defender": defender.stats_breakdown(),
            },
            "speed": _speed_comparison(attacker, defender, attacker_payload, defender_payload, payload.get("field", {})),
        }
    except Exception as exc:  # noqa: BLE001 - surface the message to the UI
        return {"ok": False, "error": str(exc)}


def _speed_comparison(attacker: Combatant, defender: Combatant, ap: dict, dp: dict, field: dict) -> dict:
    tailwind = bool(field.get("tailwind"))
    trick_room = bool(field.get("trickRoom"))
    a_speed = attacker.effective_speed(tailwind=tailwind, paralyzed=bool(ap.get("isParalyzed")))
    d_speed = defender.effective_speed(tailwind=tailwind, paralyzed=bool(dp.get("isParalyzed")))
    if trick_room:
        if a_speed < d_speed:
            verdict = f"{attacker.name or 'attacker'} prima (Trick Room: {a_speed} < {d_speed})"
        elif a_speed > d_speed:
            verdict = f"{defender.name or 'defender'} prima (Trick Room: {d_speed} < {a_speed})"
        else:
            verdict = f"Pari velocità in Trick Room ({a_speed})"
    else:
        if a_speed > d_speed:
            verdict = f"{attacker.name or 'attacker'} prima ({a_speed} vs {d_speed})"
        elif a_speed < d_speed:
            verdict = f"{defender.name or 'defender'} prima ({d_speed} vs {a_speed})"
        else:
            verdict = f"Pari velocità ({a_speed})"
    return {"attacker": a_speed, "defender": d_speed, "verdict": verdict, "tailwind": tailwind, "trickRoom": trick_room}


def _combatant_from(payload: dict) -> Combatant:
    return Combatant(
        name=payload.get("name", ""),
        level=int(payload.get("level", 50) or 50),
        types=[str(t).lower() for t in payload.get("types") or []],
        base_stats={k: int(v or 0) for k, v in (payload.get("baseStats") or {}).items()},
        evs={k: int(v or 0) for k, v in (payload.get("evs") or {}).items()},
        ivs={k: int(v if v is not None else 31) for k, v in (payload.get("ivs") or {}).items()} or {k: 31 for k in ("hp", "atk", "def", "spa", "spd", "spe")},
        nature=payload.get("nature", "Hardy") or "Hardy",
        boosts={k: int(v or 0) for k, v in (payload.get("boosts") or {}).items()},
        tera_type=(payload.get("teraType") or None),
        is_burned=bool(payload.get("isBurned")),
    )


def _field_from(payload: dict) -> Field:
    return Field(
        weather=str(payload.get("weather", "") or ""),
        terrain=str(payload.get("terrain", "") or ""),
        light_screen=bool(payload.get("lightScreen")),
        reflect=bool(payload.get("reflect")),
        aurora_veil=bool(payload.get("auroraVeil")),
        spread=bool(payload.get("spread", True)),
        crit=bool(payload.get("crit")),
    )


if __name__ == "__main__":
    raise SystemExit(main())
