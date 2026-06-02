# Assistente conversazionale (B11 v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trasformare il Coach AI one-shot in un assistente conversazionale che orchestra l'engine deterministico via function-calling Gemini, risponde a domande operative sul dataset e propone set/spread applicabili con un click.

**Architecture:** Un `ToolRegistry` espone wrapper sottili sui metodi di `RecommendationService` ed `EVTunerService`. Un `GeminiAgent` invia gli schemi dei tool a Gemini, esegue le `functionCall` richieste contro l'engine in un loop limitato e ritorna `{reply, proposals[], toolTrace[]}`. La chat front-end manda lo storico e applica le proposte riusando il path degli overrides. I numeri vengono **sempre** dai tool, mai da Gemini.

**Tech Stack:** Python 3.10 (stdlib `urllib`, niente SDK), engine esistente, server `BaseHTTPRequestHandler`, vanilla JS front-end. Test con `unittest` (convenzione progetto: `PYTHONPATH=src python3 -m unittest discover -s tests`).

**Convenzioni progetto da rispettare:**
- Niente pytest installato → test come `unittest.TestCase`, lanciati con `PYTHONPATH=src python3 -m unittest discover -s tests`.
- Commit frequenti, in locale. **Niente push/PR senza ok esplicito di Matteo.**
- Nomi mossa/mon canonici inglesi nei tool; `to_key()` per match tollerante.

---

## FASE 1 — Engine + Tools

### Task 1: Estendere l'outspeed con i boost di Speed

**Files:**
- Modify: `src/pokemon_anti_meta_builder/ev_optimizer/outspeed.py`
- Test: `tests/test_ev_optimizer.py`

- [ ] **Step 1: Scrivere il test che fallisce**

In `tests/test_ev_optimizer.py` aggiungi al gruppo outspeed:

```python
class TestOutspeedBoost(unittest.TestCase):
    def _mon(self, spe_base, evs_spe=0, nature="Hardy"):
        from pokemon_anti_meta_builder.damage_calc.calculator import Combatant
        return Combatant(
            name="Test", level=50, types=["normal"],
            base_stats={"hp": 100, "atk": 100, "def": 100, "spa": 100, "spd": 100, "spe": spe_base},
            evs={"spe": evs_spe}, ivs={"spe": 31}, nature=nature,
        )

    def test_our_boost_plus_one_lowers_required_evs(self):
        from pokemon_anti_meta_builder.ev_optimizer.outspeed import find_min_evs_to_outspeed
        our = self._mon(80)
        target = self._mon(120, evs_spe=32, nature="Timid")
        base = find_min_evs_to_outspeed(our, target)
        boosted = find_min_evs_to_outspeed(our, target, our_boost=1)
        # +1 Speed (x1.5) deve rendere fattibile o ridurre gli EV richiesti
        self.assertTrue(boosted.feasible)
        self.assertLessEqual(boosted.spe_ev, base.spe_ev if base.feasible else 32)

    def test_target_boost_raises_required_speed(self):
        from pokemon_anti_meta_builder.ev_optimizer.outspeed import find_min_evs_to_outspeed
        our = self._mon(120)
        target = self._mon(100)
        no_boost = find_min_evs_to_outspeed(our, target)
        with_boost = find_min_evs_to_outspeed(our, target, target_boost=2)
        self.assertGreater(with_boost.target_speed, no_boost.target_speed)

    def test_default_boost_zero_unchanged(self):
        from pokemon_anti_meta_builder.ev_optimizer.outspeed import find_min_evs_to_outspeed
        our = self._mon(100)
        target = self._mon(95, evs_spe=32, nature="Timid")
        r = find_min_evs_to_outspeed(our, target)
        self.assertEqual(r.target_speed, find_min_evs_to_outspeed(our, target, our_boost=0, target_boost=0).target_speed)
```

- [ ] **Step 2: Lanciare il test, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_ev_optimizer.TestOutspeedBoost -v`
Expected: FAIL — `find_min_evs_to_outspeed() got an unexpected keyword argument 'our_boost'`

- [ ] **Step 3: Implementare i boost**

In `outspeed.py`, modifica la firma e applica i boost via il campo `boosts` del `Combatant` (già usato da `effective_speed`):

```python
def find_min_evs_to_outspeed(
    our_mon: Combatant,
    target_mon: Combatant,
    condition: str = "none",
    our_boost: int = 0,
    target_boost: int = 0,
) -> OutspeedResult:
    """Return the minimum (Spe EVs, nature) that makes us strictly faster.

    our_boost / target_boost are Speed stage changes (-6..+6) applied via the
    combatant boosts, so "+1 Speed" (Dragon Dance, etc.) is modelled correctly.
    """
    tw_me, tw_opp = _tailwind_flags(condition)
    scarf_me = condition == "scarf_me"
    scarf_opp = condition == "scarf_opp"
    paralysis_opp = condition == "paralysis_opp"

    target_mon = _with_spe_boost(target_mon, target_boost)
    our_mon = _with_spe_boost(our_mon, our_boost)

    target_speed = _live_speed(target_mon, tailwind=tw_opp, scarf=scarf_opp, paralyzed=paralysis_opp)
    # ...resto invariato...
```

Aggiungi l'helper subito sotto `_with_spe`:

```python
def _with_spe_boost(base: Combatant, stage: int) -> Combatant:
    if not stage:
        return base
    new_boosts = dict(base.boosts)
    new_boosts["spe"] = max(-6, min(6, new_boosts.get("spe", 0) + stage))
    return Combatant(
        name=base.name, level=base.level, types=list(base.types),
        base_stats=dict(base.base_stats), evs=dict(base.evs), ivs=dict(base.ivs),
        nature=base.nature, boosts=new_boosts, tera_type=base.tera_type,
        is_burned=base.is_burned,
    )
```

(`_with_spe` copia già `boosts=dict(base.boosts)`, quindi il boost di `our_mon` sopravvive all'iterazione EV.)

- [ ] **Step 4: Lanciare il test, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_ev_optimizer.TestOutspeedBoost -v`
Expected: PASS (3 test)

- [ ] **Step 5: Threadare i boost in EVTunerService.optimize**

In `src/pokemon_anti_meta_builder/ev_optimizer/service.py`, ramo `mode == "outspeed"`, passa i boost dal payload:

```python
            elif mode == "outspeed":
                result = find_min_evs_to_outspeed(
                    our_mon=our_combatant,
                    target_mon=target_combatant,
                    condition=(payload.get("condition") or "none"),
                    our_boost=int(payload.get("ourBoost") or 0),
                    target_boost=int(payload.get("targetBoost") or 0),
                )
```

- [ ] **Step 6: Full suite + commit**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests`
Expected: OK (14 test: 11 esistenti + 3 nuovi)

```bash
git add src/pokemon_anti_meta_builder/ev_optimizer/outspeed.py src/pokemon_anti_meta_builder/ev_optimizer/service.py tests/test_ev_optimizer.py
git commit -m "feat(ev): outspeed accepts our/target Speed boost stages"
```

---

### Task 2: ToolRegistry + tool `find_pokemon_by_moves`

**Files:**
- Create: `src/pokemon_anti_meta_builder/ai_coach/tools.py`
- Test: `tests/test_assistant_tools.py`

- [ ] **Step 1: Scrivere il test che fallisce**

```python
import unittest
from pokemon_anti_meta_builder.recommendations.service import RecommendationService
from pokemon_anti_meta_builder.ev_optimizer.service import EVTunerService
from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry


def _service():
    import os
    pk = "data/raw/pikalytics_sets.json"
    return RecommendationService(
        input_path="data/raw/reg_ma_pokekipe.csv", format_id="reg-ma",
        dex_path="data/raw/showdown_dex.json", learnsets_path="data/raw/showdown_learnsets.json",
        pikalytics_path=pk if os.path.exists(pk) else None,
    )


class TestFindByMoves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_intersection_requires_all_moves(self):
        out = cls = self.reg.call("find_pokemon_by_moves", {"moves": ["Protect"], "require_all": True})
        self.assertTrue(out["ok"])
        self.assertIsInstance(out["species"], list)

    def test_unknown_move_returns_empty_not_error(self):
        out = self.reg.call("find_pokemon_by_moves", {"moves": ["NotARealMove"], "require_all": True})
        self.assertTrue(out["ok"])
        self.assertEqual(out["species"], [])

    def test_unknown_tool_name_errors(self):
        out = self.reg.call("does_not_exist", {})
        self.assertFalse(out["ok"])
```

- [ ] **Step 2: Lanciare, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestFindByMoves -v`
Expected: FAIL — `No module named 'pokemon_anti_meta_builder.ai_coach.tools'`

- [ ] **Step 3: Implementare ToolRegistry + primo tool**

```python
"""Deterministic tools the conversational assistant can call.

Each tool is a thin wrapper over RecommendationService / EVTunerService that
returns compact JSON. Numbers come from the engine — the LLM only orchestrates.
Every tool returns a dict with at least {"ok": bool}; on failure {"ok": False,
"error": str}. `to_key` keeps name matching tolerant.
"""
from __future__ import annotations

from typing import Any, Callable

from pokemon_anti_meta_builder.meta_parser.normalizer import to_key


class ToolRegistry:
    def __init__(self, service, ev_tuner) -> None:
        self.service = service
        self.ev_tuner = ev_tuner
        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "find_pokemon_by_moves": self._find_pokemon_by_moves,
        }

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = self._tools.get(name)
        if fn is None:
            return {"ok": False, "error": f"unknown tool '{name}'"}
        try:
            return fn(args or {})
        except Exception as exc:  # tools must never crash the agent loop
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _find_pokemon_by_moves(self, args: dict[str, Any]) -> dict[str, Any]:
        moves = [m for m in (args.get("moves") or []) if m]
        if not moves:
            return {"ok": False, "error": "missing moves"}
        require_all = args.get("require_all", True)
        sets = [set(map(to_key, self.service.species_with_move(m))) for m in moves]
        keys = set.intersection(*sets) if require_all else set.union(*sets)
        # map keys back to display names, meta-first ordering from species_with_move
        ordered: list[str] = []
        seen: set[str] = set()
        for m in moves:
            for name in self.service.species_with_move(m):
                k = to_key(name)
                if k in keys and k not in seen:
                    seen.add(k)
                    ordered.append(name)
        return {"ok": True, "moves": moves, "require_all": bool(require_all), "species": ordered[:30]}
```

> `to_key` vive in `pokemon_anti_meta_builder.meta_parser.normalizer` (stesso import di `service.py`).

- [ ] **Step 4: Lanciare, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestFindByMoves -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add src/pokemon_anti_meta_builder/ai_coach/tools.py tests/test_assistant_tools.py
git commit -m "feat(assistant): ToolRegistry + find_pokemon_by_moves"
```

---

### Task 3: Tool `search_pokemon` + `get_learnset`

**Files:**
- Modify: `src/pokemon_anti_meta_builder/ai_coach/tools.py`
- Test: `tests/test_assistant_tools.py`

- [ ] **Step 1: Test che fallisce**

```python
class TestSearchAndLearnset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_search_by_type(self):
        out = self.reg.call("search_pokemon", {"type": "fairy"})
        self.assertTrue(out["ok"])
        self.assertTrue(all("fairy" in [t.lower() for t in p["types"]] for p in out["pokemon"]))

    def test_search_min_usage_filters(self):
        out = self.reg.call("search_pokemon", {"min_usage": 5.0})
        self.assertTrue(all(p["usage"] >= 5.0 for p in out["pokemon"]))

    def test_get_learnset(self):
        out = self.reg.call("get_learnset", {"species": "Garchomp"})
        self.assertTrue(out["ok"])
        self.assertIn("earthquake", [m.lower() for m in out["moves"]])
```

- [ ] **Step 2: Lanciare, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestSearchAndLearnset -v`
Expected: FAIL — `unknown tool 'search_pokemon'`

- [ ] **Step 3: Implementare i due tool**

Aggiungi al dict `_tools` in `__init__`:

```python
            "search_pokemon": self._search_pokemon,
            "get_learnset": self._get_learnset,
```

E i metodi:

```python
    def _search_pokemon(self, args: dict[str, Any]) -> dict[str, Any]:
        want_type = (args.get("type") or "").lower().strip()
        want_role = (args.get("role") or "").lower().strip()
        min_usage = float(args.get("min_usage") or 0.0)
        out = []
        for p in self.service.catalog()["pokemon"]:
            if want_type and want_type not in [t.lower() for t in p["types"]]:
                continue
            if want_role and want_role not in [r.lower() for r in (p.get("roles") or [])]:
                continue
            if (p.get("usage") or 0.0) < min_usage:
                continue
            out.append({"name": p["name"], "types": p["types"], "usage": p.get("usage"), "roles": p.get("roles")})
        out.sort(key=lambda x: -(x["usage"] or 0.0))
        return {"ok": True, "count": len(out), "pokemon": out[:40]}

    def _get_learnset(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        moves = self.service.learnset_for(species)
        return {"ok": True, "species": species, "moves": moves}
```

- [ ] **Step 4: Lanciare, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestSearchAndLearnset -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add src/pokemon_anti_meta_builder/ai_coach/tools.py tests/test_assistant_tools.py
git commit -m "feat(assistant): search_pokemon + get_learnset tools"
```

---

### Task 4: Tool `who_counters` + `countered_by` + `get_set`

**Files:**
- Modify: `src/pokemon_anti_meta_builder/ai_coach/tools.py`
- Test: `tests/test_assistant_tools.py`

- [ ] **Step 1: Test che fallisce**

```python
class TestCountersAndSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_who_counters_returns_reasons(self):
        out = self.reg.call("who_counters", {"species": "Garchomp"})
        self.assertTrue(out["ok"])
        self.assertTrue(out["counters"])
        self.assertIn("reasons", out["counters"][0])

    def test_countered_by(self):
        out = self.reg.call("countered_by", {"species": "Garchomp"})
        self.assertTrue(out["ok"])

    def test_get_set_has_moves_and_stats(self):
        out = self.reg.call("get_set", {"species": "Incineroar"})
        self.assertTrue(out["ok"])
        self.assertIn("moves", out["set"])
        self.assertIn("baseStats", out["set"])
```

- [ ] **Step 2: Lanciare, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestCountersAndSet -v`
Expected: FAIL — `unknown tool 'who_counters'`

- [ ] **Step 3: Implementare**

Aggiungi a `_tools`:

```python
            "who_counters": self._who_counters,
            "countered_by": self._countered_by,
            "get_set": self._get_set,
```

Metodi:

```python
    def _who_counters(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        data = self.service.counter_lookup(species)
        if data.get("notFound"):
            return {"ok": False, "error": f"unknown Pokemon: {species}"}
        return {"ok": True, "name": data["name"], "types": data["types"],
                "source": data["source"], "counters": data["counters"]}

    def _countered_by(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        return {"ok": True, **self.service.countered_by(species)}

    def _get_set(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        if not species:
            return {"ok": False, "error": "missing species"}
        payload = self.service.combatant_payload(species)
        if payload.get("error"):
            return {"ok": False, "error": payload["error"]}
        return {"ok": True, "set": payload}
```

- [ ] **Step 4: Lanciare, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestCountersAndSet -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add src/pokemon_anti_meta_builder/ai_coach/tools.py tests/test_assistant_tools.py
git commit -m "feat(assistant): who_counters, countered_by, get_set tools"
```

---

### Task 5: Tool EV — `min_speed_to_outspeed` (con proposal)

**Files:**
- Modify: `src/pokemon_anti_meta_builder/ai_coach/tools.py`
- Test: `tests/test_assistant_tools.py`

- [ ] **Step 1: Test che fallisce**

```python
class TestOutspeedTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_min_speed_to_outspeed_returns_result(self):
        out = self.reg.call("min_speed_to_outspeed", {
            "species": "Charizard", "target": "Aerodactyl",
            "target_max_speed": True, "our_boost": 1,
        })
        self.assertTrue(out["ok"])
        self.assertIn("evs", out["result"])
        self.assertIn("proposal", out)  # applicabile con 1 click

    def test_missing_species_errors(self):
        out = self.reg.call("min_speed_to_outspeed", {"target": "Aerodactyl"})
        self.assertFalse(out["ok"])
```

- [ ] **Step 2: Lanciare, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestOutspeedTool -v`
Expected: FAIL — `unknown tool 'min_speed_to_outspeed'`

- [ ] **Step 3: Implementare (mappa "max speed" → targetSpreadManual Champions)**

Aggiungi a `_tools`: `"min_speed_to_outspeed": self._min_speed_to_outspeed,`

```python
    def _min_speed_to_outspeed(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        target = (args.get("target") or "").strip()
        if not species or not target:
            return {"ok": False, "error": "need species and target"}
        payload = {
            "mode": "outspeed",
            "ourSpecies": species,
            "targetSpecies": target,
            "condition": args.get("condition") or "none",
            "ourBoost": int(args.get("our_boost") or 0),
            "targetBoost": int(args.get("target_boost") or 0),
        }
        if args.get("target_max_speed"):
            # Champions scale: 32 Spe EV + Jolly = max Speed.
            payload["targetSpreadManual"] = {"nature": "Jolly", "evs": {"spe": 32}}
        out = self.ev_tuner.optimize(payload)
        if not out.get("ok"):
            return out
        result = out["result"]
        proposal = None
        if result.get("feasible"):
            proposal = {
                "species": species,
                "nature": result.get("nature"),
                "evs": result.get("evs", {}),
                "note": f"{result['evs'].get('spe', 0)} Spe EV per superare {target}",
            }
        return {"ok": True, "result": result, "assumptions": out.get("assumptions"), "proposal": proposal}
```

- [ ] **Step 4: Lanciare, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestOutspeedTool -v`
Expected: PASS (2 test)

- [ ] **Step 5: Commit**

```bash
git add src/pokemon_anti_meta_builder/ai_coach/tools.py tests/test_assistant_tools.py
git commit -m "feat(assistant): min_speed_to_outspeed tool with apply proposal"
```

---

### Task 6: Tool EV — `min_evs_to_survive` + `min_evs_to_ohko`

**Files:**
- Modify: `src/pokemon_anti_meta_builder/ai_coach/tools.py`
- Test: `tests/test_assistant_tools.py`

- [ ] **Step 1: Test che fallisce**

```python
class TestSurviveOhkoTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_survive_returns_evs(self):
        out = self.reg.call("min_evs_to_survive", {
            "species": "Incineroar", "attacker": "Garchomp", "move": "Earthquake",
        })
        self.assertTrue(out["ok"])
        self.assertIn("result", out)

    def test_ohko_returns_evs(self):
        out = self.reg.call("min_evs_to_ohko", {
            "species": "Garchomp", "target": "Incineroar", "move": "Earthquake",
        })
        self.assertTrue(out["ok"])

    def test_survive_missing_move_errors(self):
        out = self.reg.call("min_evs_to_survive", {"species": "Incineroar", "attacker": "Garchomp"})
        self.assertFalse(out["ok"])
```

- [ ] **Step 2: Lanciare, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestSurviveOhkoTools -v`
Expected: FAIL — `unknown tool 'min_evs_to_survive'`

- [ ] **Step 3: Implementare**

Aggiungi a `_tools`:

```python
            "min_evs_to_survive": self._min_evs_to_survive,
            "min_evs_to_ohko": self._min_evs_to_ohko,
```

```python
    def _min_evs_to_survive(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        attacker = (args.get("attacker") or "").strip()
        move = (args.get("move") or "").strip()
        if not species or not attacker or not move:
            return {"ok": False, "error": "need species, attacker and move"}
        out = self.ev_tuner.optimize({
            "mode": "survive", "ourSpecies": species, "targetSpecies": attacker,
            "move": move, "threshold": args.get("threshold") or "guaranteed",
        })
        if not out.get("ok"):
            return out
        proposal = {"species": species, "evs": out["result"].get("evs", {}),
                    "note": f"regge {move} di {attacker}"} if out["result"].get("feasible") else None
        return {"ok": True, "result": out["result"], "assumptions": out.get("assumptions"), "proposal": proposal}

    def _min_evs_to_ohko(self, args: dict[str, Any]) -> dict[str, Any]:
        species = (args.get("species") or "").strip()
        target = (args.get("target") or "").strip()
        move = (args.get("move") or "").strip()
        if not species or not target or not move:
            return {"ok": False, "error": "need species, target and move"}
        out = self.ev_tuner.optimize({
            "mode": "ohko", "ourSpecies": species, "targetSpecies": target,
            "move": move, "goal": args.get("goal") or "ohko",
        })
        if not out.get("ok"):
            return out
        proposal = {"species": species, "evs": out["result"].get("evs", {}),
                    "note": f"{args.get('goal') or 'ohko'} {target} con {move}"} if out["result"].get("feasible") else None
        return {"ok": True, "result": out["result"], "assumptions": out.get("assumptions"), "proposal": proposal}
```

- [ ] **Step 4: Lanciare, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestSurviveOhkoTools -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add src/pokemon_anti_meta_builder/ai_coach/tools.py tests/test_assistant_tools.py
git commit -m "feat(assistant): min_evs_to_survive + min_evs_to_ohko tools"
```

---

### Task 7: Schemi `function_declarations` per Gemini

**Files:**
- Modify: `src/pokemon_anti_meta_builder/ai_coach/tools.py`
- Test: `tests/test_assistant_tools.py`

- [ ] **Step 1: Test che fallisce**

```python
class TestToolDeclarations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        svc = _service()
        cls.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_declarations_cover_every_tool(self):
        decls = self.reg.declarations()
        names = {d["name"] for d in decls}
        self.assertEqual(names, set(self.reg.tool_names()))

    def test_declaration_shape(self):
        for d in self.reg.declarations():
            self.assertIn("name", d)
            self.assertIn("description", d)
            self.assertIn("parameters", d)
            self.assertEqual(d["parameters"]["type"], "object")
```

- [ ] **Step 2: Lanciare, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestToolDeclarations -v`
Expected: FAIL — `'ToolRegistry' object has no attribute 'declarations'`

- [ ] **Step 3: Implementare declarations() + tool_names()**

Aggiungi a `ToolRegistry` (schema in formato Gemini `function_declarations`; tipi JSON-schema string/number/boolean/array):

```python
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def declarations(self) -> list[dict[str, Any]]:
        S = {"type": "string"}
        return [
            {"name": "find_pokemon_by_moves",
             "description": "Pokémon che imparano le mosse date. require_all=true -> intersezione (tutte), false -> unione.",
             "parameters": {"type": "object", "properties": {
                 "moves": {"type": "array", "items": S}, "require_all": {"type": "boolean"}}, "required": ["moves"]}},
            {"name": "search_pokemon",
             "description": "Cerca Pokémon del meta per tipo, ruolo e usage minimo.",
             "parameters": {"type": "object", "properties": {
                 "type": S, "role": S, "min_usage": {"type": "number"}}}},
            {"name": "get_learnset",
             "description": "Tutte le mosse legali che un Pokémon impara.",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "who_counters",
             "description": "Chi counter-a (batte) il Pokémon dato, con motivi (mosse/tipi/speed).",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "countered_by",
             "description": "Quali Pokémon il soggetto batte (inverso di who_counters).",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "get_set",
             "description": "Set reale (item/ability/mosse/EV/nature) e base stats di un Pokémon.",
             "parameters": {"type": "object", "properties": {"species": S}, "required": ["species"]}},
            {"name": "min_speed_to_outspeed",
             "description": "EV Speed minimi per superare un bersaglio. target_max_speed=true assume il bersaglio a max Speed. our_boost/target_boost = stage di Speed (+1, +2...). condition: none/tailwind_me/tailwind_opp/scarf_me/scarf_opp/paralysis_opp.",
             "parameters": {"type": "object", "properties": {
                 "species": S, "target": S, "target_max_speed": {"type": "boolean"},
                 "our_boost": {"type": "number"}, "target_boost": {"type": "number"}, "condition": S},
                 "required": ["species", "target"]}},
            {"name": "min_evs_to_survive",
             "description": "EV difensivi minimi per sopravvivere a una mossa di un attaccante. threshold: guaranteed/high/median.",
             "parameters": {"type": "object", "properties": {
                 "species": S, "attacker": S, "move": S, "threshold": S}, "required": ["species", "attacker", "move"]}},
            {"name": "min_evs_to_ohko",
             "description": "EV offensivi minimi per OHKO/2HKO un bersaglio con una mossa. goal: ohko/2hko.",
             "parameters": {"type": "object", "properties": {
                 "species": S, "target": S, "move": S, "goal": S}, "required": ["species", "target", "move"]}},
        ]
```

- [ ] **Step 4: Lanciare, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_tools.TestToolDeclarations -v`
Expected: PASS (2 test)

- [ ] **Step 5: Full suite + commit**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests`
Expected: OK

```bash
git add src/pokemon_anti_meta_builder/ai_coach/tools.py tests/test_assistant_tools.py
git commit -m "feat(assistant): Gemini function_declarations for all tools"
```

---

## FASE 2 — Agente + Chat

### Task 8: GeminiAgent loop (Gemini mockato, niente rete)

**Files:**
- Create: `src/pokemon_anti_meta_builder/ai_coach/agent.py`
- Test: `tests/test_assistant_agent.py`

- [ ] **Step 1: Test che fallisce**

Il test inietta un fake "Gemini caller" per evitare la rete: primo turno chiede una `functionCall`, secondo turno risponde testo.

```python
import unittest
from pokemon_anti_meta_builder.recommendations.service import RecommendationService
from pokemon_anti_meta_builder.ev_optimizer.service import EVTunerService
from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry
from pokemon_anti_meta_builder.ai_coach.agent import GeminiAgent


def _service():
    import os
    pk = "data/raw/pikalytics_sets.json"
    return RecommendationService(
        input_path="data/raw/reg_ma_pokekipe.csv", format_id="reg-ma",
        dex_path="data/raw/showdown_dex.json", learnsets_path="data/raw/showdown_learnsets.json",
        pikalytics_path=pk if os.path.exists(pk) else None,
    )


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        svc = _service()
        self.reg = ToolRegistry(svc, EVTunerService(svc))

    def test_executes_function_call_then_returns_text(self):
        calls = []
        def fake_gemini(contents, tools):
            calls.append(contents)
            if len(calls) == 1:
                return {"functionCall": {"name": "find_pokemon_by_moves",
                                          "args": {"moves": ["Protect"], "require_all": True}}}
            return {"text": "Ecco i Pokémon che imparano Protect."}
        agent = GeminiAgent(self.reg, gemini_caller=fake_gemini)
        out = agent.run([{"role": "user", "text": "chi impara Protect?"}])
        self.assertEqual(out["reply"], "Ecco i Pokémon che imparano Protect.")
        self.assertEqual(out["toolTrace"][0]["name"], "find_pokemon_by_moves")
        self.assertEqual(len(calls), 2)

    def test_loop_cap_stops_runaway(self):
        def always_calls(contents, tools):
            return {"functionCall": {"name": "find_pokemon_by_moves", "args": {"moves": ["Protect"]}}}
        agent = GeminiAgent(self.reg, gemini_caller=always_calls, max_turns=3)
        out = agent.run([{"role": "user", "text": "loop"}])
        self.assertLessEqual(len(out["toolTrace"]), 3)
        self.assertIn("reply", out)

    def test_collects_proposals(self):
        def fake_gemini(contents, tools):
            if not any("functionResponse" in str(c) for c in contents):
                return {"functionCall": {"name": "min_speed_to_outspeed",
                                          "args": {"species": "Charizard", "target": "Aerodactyl", "target_max_speed": True}}}
            return {"text": "Servono X EV."}
        agent = GeminiAgent(self.reg, gemini_caller=fake_gemini)
        out = agent.run([{"role": "user", "text": "charizard vs aerodactyl"}])
        self.assertTrue(any(p for p in out["proposals"]))
```

- [ ] **Step 2: Lanciare, deve fallire**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_agent -v`
Expected: FAIL — `No module named 'pokemon_anti_meta_builder.ai_coach.agent'`

- [ ] **Step 3: Implementare l'agente**

`gemini_caller(contents, tools) -> {"functionCall": {...}} | {"text": str}` è iniettabile (test) o il vero client REST (Task 9).

```python
"""Conversational agent: loops Gemini function-calls against the ToolRegistry.

The LLM only orchestrates; every number comes from a tool. `gemini_caller` is
injectable so tests run without network.
"""
from __future__ import annotations

from typing import Any, Callable

from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry

GeminiCaller = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]

SYSTEM_PROMPT = (
    "Sei un assistente per Pokémon Champions, Regulation M-A. Rispondi in italiano, "
    "conciso. Champions NON ha Tera; supporta Mega Evoluzioni (una per team). "
    "Usa SEMPRE i tool per numeri, counter, mosse, EV: non inventare valori. "
    "Traduci i nomi italiani di mosse/Pokémon in inglese canonico prima di chiamare i tool. "
    "Se un tool torna ok=false, spiega l'errore e chiedi chiarimenti."
)


class GeminiAgent:
    def __init__(self, registry: ToolRegistry, gemini_caller: GeminiCaller, max_turns: int = 6) -> None:
        self.registry = registry
        self.gemini = gemini_caller
        self.max_turns = max_turns

    def run(self, messages: list[dict[str, Any]], team_state: dict[str, Any] | None = None) -> dict[str, Any]:
        contents: list[dict[str, Any]] = [{"role": "system", "text": SYSTEM_PROMPT}]
        if team_state:
            contents.append({"role": "system", "text": f"Team corrente: {team_state}"})
        contents.extend(messages)

        tool_trace: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []

        for _ in range(self.max_turns):
            resp = self.gemini(contents, self.registry.declarations())
            call = resp.get("functionCall")
            if not call:
                return {"reply": resp.get("text", ""), "proposals": proposals, "toolTrace": tool_trace}
            name, args = call.get("name", ""), call.get("args", {})
            result = self.registry.call(name, args)
            tool_trace.append({"name": name, "args": args, "ok": result.get("ok")})
            if isinstance(result, dict) and result.get("proposal"):
                proposals.append(result["proposal"])
            contents.append({"role": "model", "functionCall": call})
            contents.append({"role": "tool", "functionResponse": {"name": name, "response": result}})

        # loop cap reached: ask the model for a final wrap-up without tools
        final = self.gemini(contents + [{"role": "system", "text": "Concludi senza altri tool."}], [])
        return {"reply": final.get("text", "Troppi passaggi, riprova più specifico."),
                "proposals": proposals, "toolTrace": tool_trace}
```

- [ ] **Step 4: Lanciare, deve passare**

Run: `PYTHONPATH=src python3 -m unittest tests.test_assistant_agent -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add src/pokemon_anti_meta_builder/ai_coach/agent.py tests/test_assistant_agent.py
git commit -m "feat(assistant): GeminiAgent function-call loop (mockable, capped)"
```

---

### Task 9: Client Gemini reale (function-calling REST)

**Files:**
- Modify: `src/pokemon_anti_meta_builder/ai_coach/agent.py`
- Test: manuale (richiede rete + key) — niente test automatico (convenzione: no rete nei test)

- [ ] **Step 1: Implementare il caller REST**

Riusa il pattern di `coach.py` (`urllib`, fallback model chain). Aggiungi in `agent.py` una factory che produce un `gemini_caller` reale. Mappa i `contents` interni (role/text/functionCall/functionResponse) nel formato Gemini `contents[].parts[]` e passa `tools=[{"function_declarations": decls}]`. Estrai dalla risposta o `functionCall` o `text`.

```python
import json, os, urllib.request, urllib.error

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash")


def make_real_gemini_caller(api_key: str | None = None, model: str | None = None) -> GeminiCaller:
    key = api_key or os.getenv("GEMINI_API_KEY")
    primary = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    def _to_gemini_contents(contents):
        out = []
        sys_txt = []
        for c in contents:
            if c["role"] == "system":
                sys_txt.append(c["text"]); continue
            if "functionCall" in c:
                out.append({"role": "model", "parts": [{"functionCall": {"name": c["functionCall"]["name"], "args": c["functionCall"].get("args", {})}}]})
            elif "functionResponse" in c:
                out.append({"role": "user", "parts": [{"functionResponse": {"name": c["functionResponse"]["name"], "response": c["functionResponse"]["response"]}}]})
            else:
                role = "user" if c["role"] == "user" else "model"
                out.append({"role": role, "parts": [{"text": c.get("text", "")}]})
        return out, "\n".join(sys_txt)

    def caller(contents, tools):
        gem_contents, sys_txt = _to_gemini_contents(contents)
        body = {"contents": gem_contents}
        if sys_txt:
            body["systemInstruction"] = {"parts": [{"text": sys_txt}]}
        if tools:
            body["tools"] = [{"function_declarations": tools}]
        data = json.dumps(body).encode("utf-8")
        last_error = ""
        for model_name in (primary, *FALLBACK_MODELS):
            url = GEMINI_ENDPOINT.format(model=model_name, key=key)
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    payload = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_error = f"{e.code}"
                if e.code in (429, 503):
                    continue
                return {"text": f"Errore Gemini {e.code}."}
            except Exception as e:
                return {"text": f"Errore rete: {e}"}
            parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            for p in parts:
                if "functionCall" in p:
                    return {"functionCall": {"name": p["functionCall"]["name"], "args": dict(p["functionCall"].get("args", {}))}}
            text = "\n".join(p.get("text", "") for p in parts if "text" in p).strip()
            return {"text": text}
        return {"text": f"Gemini non disponibile ({last_error})."}

    return caller
```

- [ ] **Step 2: Smoke manuale (con key)**

```bash
GEMINI_API_KEY=... PYTHONPATH=src python3 -c "
from pokemon_anti_meta_builder.recommendations.service import RecommendationService
from pokemon_anti_meta_builder.ev_optimizer.service import EVTunerService
from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry
from pokemon_anti_meta_builder.ai_coach.agent import GeminiAgent, make_real_gemini_caller
svc = RecommendationService(input_path='data/raw/reg_ma_pokekipe.csv', format_id='reg-ma', dex_path='data/raw/showdown_dex.json', learnsets_path='data/raw/showdown_learnsets.json', pikalytics_path='data/raw/pikalytics_sets.json')
reg = ToolRegistry(svc, EVTunerService(svc))
agent = GeminiAgent(reg, make_real_gemini_caller())
print(agent.run([{'role':'user','text':'quale pokemon conosce sia Flare Blitz che Follow Me?'}])['reply'])
"
```
Expected: risposta italiana con i Pokémon corretti, `toolTrace` con `find_pokemon_by_moves`.

- [ ] **Step 3: Commit**

```bash
git add src/pokemon_anti_meta_builder/ai_coach/agent.py
git commit -m "feat(assistant): real Gemini function-calling REST caller"
```

---

### Task 10: Endpoint `/api/assistant`

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/server.py`

- [ ] **Step 1: Costruire l'agente una volta in run_server**

Dopo `ev_tuner = EVTunerService(service)` (riga ~39):

```python
    from pokemon_anti_meta_builder.ai_coach.tools import ToolRegistry
    from pokemon_anti_meta_builder.ai_coach.agent import GeminiAgent, make_real_gemini_caller
    tool_registry = ToolRegistry(service, ev_tuner)
    assistant_key = os.getenv("GEMINI_API_KEY")
    assistant = GeminiAgent(tool_registry, make_real_gemini_caller()) if assistant_key else None
```

(Assicurati `import os` in cima a `server.py`.)

- [ ] **Step 2: Aggiungere il ramo POST**

Nel blocco `do_POST`, accanto a `/api/coach`:

```python
            if parsed.path == "/api/assistant":
                if assistant is None:
                    self._json({"enabled": False,
                                "reply": "Imposta GEMINI_API_KEY per usare l'assistente.",
                                "proposals": [], "toolTrace": []})
                    return
                messages = payload.get("messages") or []
                team_state = None
                if payload.get("selected"):
                    team_state = service.build_state(payload.get("selected", []),
                                                     payload.get("overrides") or {}).as_dict()
                result = assistant.run(messages, team_state=team_state)
                result["enabled"] = True
                self._json(result)
                return
```

- [ ] **Step 3: Verifica manuale (no key → disabled)**

```bash
PYTHONPATH=src python3 -m pokemon_anti_meta_builder serve --input data/raw/reg_ma_pokekipe.csv --dex data/raw/showdown_dex.json --learnsets data/raw/showdown_learnsets.json &
sleep 2
curl -s -X POST localhost:8765/api/assistant -d '{"messages":[{"role":"user","text":"ciao"}]}' | head -c 300
kill %1
```
Expected (senza key): `{"enabled": false, "reply": "Imposta GEMINI_API_KEY...`

- [ ] **Step 4: Commit**

```bash
git add src/pokemon_anti_meta_builder/web/server.py
git commit -m "feat(assistant): /api/assistant endpoint with no-key fallback"
```

---

### Task 11: Chat UI (HTML + CSS)

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/index.html`
- Modify: `src/pokemon_anti_meta_builder/web/static/styles.css`

- [ ] **Step 1: Sostituire il corpo della tab Coach**

Trova la `<section ... data-panel="coach">` in `index.html`. Sostituisci il contenuto one-shot con la chat:

```html
        <section class="tab-panel hidden" data-panel="coach">
          <div class="section-head"><h2>Assistente</h2></div>
          <p class="muted">Chiedi liberamente: counter, mosse, EV, set. I numeri vengono dall'engine.</p>
          <div id="assistantLog" class="assistant-log"></div>
          <div id="assistantProposals" class="assistant-proposals"></div>
          <form id="assistantForm" class="assistant-form">
            <input id="assistantInput" class="search" type="text" autocomplete="off"
                   placeholder="Es. quale Pokémon conosce Flare Blitz e Follow Me?" />
            <button class="btn" type="submit">Invia</button>
          </form>
        </section>
```

- [ ] **Step 2: CSS (riusa i token esistenti)**

In `styles.css` (sotto la sezione damage calc):

```css
/* ASSISTANT --------------------------------------- */
.assistant-log { display: flex; flex-direction: column; gap: 8px; max-height: 52vh; overflow-y: auto; padding: 4px; }
.assistant-msg { padding: 8px 10px; border-radius: 8px; font-size: 13px; line-height: 1.5; max-width: 92%; white-space: pre-wrap; }
.assistant-msg.user { align-self: flex-end; background: var(--accent, #5e6ad2); color: #fff; }
.assistant-msg.bot { align-self: flex-start; background: var(--panel-soft); border: 1px solid var(--line); }
.assistant-trace { font-size: 10px; color: var(--text-soft, #9aa0a6); margin-top: 4px; }
.assistant-form { display: flex; gap: 6px; margin-top: 8px; }
.assistant-form .search { flex: 1; }
.assistant-proposals { display: flex; flex-direction: column; gap: 6px; margin: 6px 0; }
.proposal-card { border: 1px solid var(--accent, #5e6ad2); border-radius: 8px; padding: 8px 10px; font-size: 12px; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
```

- [ ] **Step 3: Verifica markup**

Run: `PYTHONPATH=src python3 -c "import pathlib,html.parser
class P(html.parser.HTMLParser):
    pass
P().feed(pathlib.Path('src/pokemon_anti_meta_builder/web/static/index.html').read_text())
print('html parse ok')"`
Expected: `html parse ok`

- [ ] **Step 4: Commit**

```bash
git add src/pokemon_anti_meta_builder/web/static/index.html src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "feat(assistant): chat UI markup + styles"
```

---

### Task 12: Chat front-end logic + apply proposta

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/app.js`

- [ ] **Step 1: Stato + cache elementi**

Aggiungi a `state`: `assistantHistory: []`. Aggiungi in `els`:

```js
  assistantLog: document.querySelector("#assistantLog"),
  assistantInput: document.querySelector("#assistantInput"),
  assistantForm: document.querySelector("#assistantForm"),
  assistantProposals: document.querySelector("#assistantProposals"),
```

- [ ] **Step 2: Wiring submit + render**

```js
function initAssistant() {
  if (!els.assistantForm) return;
  els.assistantForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = (els.assistantInput.value || "").trim();
    if (!text) return;
    els.assistantInput.value = "";
    appendAssistantMsg("user", text);
    state.assistantHistory.push({ role: "user", text });
    appendAssistantMsg("bot", "…", true);
    let data;
    try {
      data = await fetchJson("/api/assistant", {
        method: "POST",
        body: JSON.stringify({
          messages: state.assistantHistory,
          selected: state.selected || [],
          overrides: state.overrides || {},
        }),
      });
    } catch (err) {
      replaceLastBot(`Errore: ${escapeHtml(err.message)}`);
      return;
    }
    replaceLastBot(escapeHtml(data.reply || ""), data.toolTrace);
    state.assistantHistory.push({ role: "model", text: data.reply || "" });
    renderProposals(data.proposals || []);
  });
}

function appendAssistantMsg(kind, text, pending) {
  const div = document.createElement("div");
  div.className = `assistant-msg ${kind}${pending ? " pending" : ""}`;
  div.innerHTML = text;
  els.assistantLog.appendChild(div);
  els.assistantLog.scrollTop = els.assistantLog.scrollHeight;
}

function replaceLastBot(html, trace) {
  const pend = els.assistantLog.querySelector(".assistant-msg.bot.pending");
  const target = pend || els.assistantLog.lastElementChild;
  if (!target) return;
  target.classList.remove("pending");
  const traceHtml = (trace && trace.length)
    ? `<div class="assistant-trace">🔧 ${trace.map((t) => escapeHtml(t.name)).join(", ")}</div>` : "";
  target.innerHTML = html + traceHtml;
  els.assistantLog.scrollTop = els.assistantLog.scrollHeight;
}

function renderProposals(proposals) {
  if (!els.assistantProposals) return;
  els.assistantProposals.innerHTML = "";
  proposals.forEach((p) => {
    const card = document.createElement("div");
    card.className = "proposal-card";
    const evs = Object.entries(p.evs || {}).filter(([, v]) => v).map(([k, v]) => `${k.toUpperCase()} ${v}`).join(" / ");
    card.innerHTML = `<span>${escapeHtml(p.species)}${p.nature ? " · " + escapeHtml(p.nature) : ""}${evs ? " · " + escapeHtml(evs) : ""}<br><span class="muted">${escapeHtml(p.note || "")}</span></span>`;
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.textContent = "Applica al team";
    btn.addEventListener("click", () => applyProposal(p));
    card.appendChild(btn);
    els.assistantProposals.appendChild(card);
  });
}

async function applyProposal(p) {
  const key = p.species;
  state.overrides = state.overrides || {};
  const prev = state.overrides[key] || {};
  state.overrides[key] = {
    ...prev,
    ...(p.nature ? { nature: p.nature } : {}),
    evs: { ...(prev.evs || {}), ...(p.evs || {}) },
  };
  await refresh();
  showToast(`Applicato a ${escapeHtml(key)}`, "success");
}
```

> Helper reali confermati in `app.js`: `fetchJson(url, options)`, `escapeHtml`, `refresh()` (async, ricostruisce stato+render), `showToast(msg, kind)`. Nota: `applyProposal` applica l'override solo se `state.selected` contiene già `p.species`; se il mon non è in team, `refresh()` lo ignora — in tal caso mostra un toast "aggiungi prima {species} al team" (controlla `state.selected.includes(key)` prima di applicare).

- [ ] **Step 3: Chiamare initAssistant() al boot**

In `async function init()` (riga ~64), accanto agli altri wiring di listener (es. dopo `populateLookupDatalist()`), aggiungi `initAssistant();`.

- [ ] **Step 4: Verifica sintassi**

Run: `node --check src/pokemon_anti_meta_builder/web/static/app.js`
Expected: nessun errore

- [ ] **Step 5: Commit**

```bash
git add src/pokemon_anti_meta_builder/web/static/app.js
git commit -m "feat(assistant): chat front-end logic + apply-proposal to overrides"
```

---

### Task 13: Verifica end-to-end manuale (con key)

**Files:** nessuno (solo verifica)

- [ ] **Step 1: Avvio con key**

```bash
GEMINI_API_KEY=... PYTHONPATH=src python3 -m pokemon_anti_meta_builder serve \
  --input data/raw/reg_ma_pokekipe.csv --dex data/raw/showdown_dex.json \
  --learnsets data/raw/showdown_learnsets.json --pikalytics data/raw/pikalytics_sets.json
```

- [ ] **Step 2: Prove dai tuoi esempi** (apri `localhost:8765`, tab Assistente)
  - "Quale Pokémon conosce sia Flare Blitz che Follow Me?" → lista corretta, trace `find_pokemon_by_moves`.
  - "Charizard a +1 di Speed quanta velocità minima per superare Aerodactyl max Speed?" → numero dall'engine, card proposta con bottone Applica.
  - "Chi batte Garchomp e perché?" → counter con reasons.
  - Clic "Applica al team" su una proposta → l'override compare nel team.

- [ ] **Step 3: Full suite finale**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests`
Expected: OK (tutti i test verdi)
Run: `node --check src/pokemon_anti_meta_builder/web/static/app.js`
Expected: ok

- [ ] **Step 4: Aggiornare la memoria di progetto**

Aggiorna `project_pokemon_anti_meta_builder.md` con: B11 v2 fatto (assistente conversazionale, tool list, agent loop, endpoint, chat UI), e marca B11 come completato nella rassegna.

---

## Self-review (compilata in fase di scrittura)

- **Copertura spec:** architettura (Task 8-10), ToolRegistry+8 tool (Task 2-7), estensione boost outspeed (Task 1), proposte 1-click (Task 5/6/12), UI chat (Task 11-12), fallback no-key (Task 10), test (Task 1-8). Tutte le sezioni dello spec hanno un task.
- **Placeholder:** nessun TBD; ogni step ha codice/comando reale. Eccezioni dichiarate: nomi helper front-end (`fetchJson`/`refreshState`/`showToast`) e import di `to_key` vanno verificati contro i nomi reali in fase di esecuzione — segnalato esplicitamente nei task, non è un placeholder di logica.
- **Coerenza tipi:** `gemini_caller(contents, tools) -> {"functionCall"|"text"}` usato identico in Task 8 e Task 9; `ToolRegistry.call/declarations/tool_names` coerenti; proposal `{species, nature?, evs, note}` coerente tra tool (Task 5/6) e UI (Task 12).
