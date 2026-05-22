# Pokémon Champions Builder

Tool Python deterministico + UI locale per costruire team competitivi **Pokémon Champions / VGC 2026 Regulation M-A**, basato su dati reali del meta (Pokékipe) e sul dex completo (Pokémon Showdown).

L'engine deterministico fa lo heavy lifting (legalità, scoring, threat analysis, counter detection). L'AI coach opzionale (Gemini gratuito) commenta lo stato in linguaggio naturale.

## Highlight

- **Builder counter-aware**: l'auto-build minimizza il numero di counter del meta che il team subisce, mantenendo i Pokémon già scelti dall'utente.
- **Threat analyzer** che usa dati reali Pokékipe (`checks_counters`) quando disponibili, con fallback type-based. Riconosce le forme Mega via item.
- **Roster esteso**: tutti i Pokémon legali Reg M-A (~188), incluse 65 forme Mega come voci separate per il lookup.
- **Damage calculator** lite con formula gen 9 in scala Pokémon Champions (0–32 per stat). Stats live, confronto velocità con Tailwind / Trick Room / Paralysis.
- **Lookup standalone**: digita qualunque Pokémon (anche off-meta o forma Mega) per vedere chi lo counta. Suggerisce sia opzioni meta sia off-meta.
- **AI Coach con Gemini** (gratis via [AI Studio](https://aistudio.google.com)) come consulente sopra l'engine.

## Setup

```bash
git clone <questo-repo>
cd pokemon-champions-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Niente dipendenze di runtime obbligatorie oltre alla standard library Python 3.10+. `pip install -e .` serve solo per esporre il modulo come pacchetto.

## Sync dei dati

I dati live non sono committati. Scaricali col CLI (richiede internet; usa `--insecure` se i certificati locali sono rotti):

```bash
# Meta Pokékipe (top usage + spreads + teammates + checks/counters)
PYTHONPATH=src python3 -m pokemon_anti_meta_builder sync-meta \
  --source pokekipe --source-format gen9championsvgc2026regma \
  --elo-cutoff 1760 --limit 30 --sleep 1.1 --insecure

# Pokédex Showdown filtrato a Reg M-A (188 mon + 65 Mega forms)
PYTHONPATH=src python3 -m pokemon_anti_meta_builder sync-dex --insecure

# Mosse + learnsets gen 9 per i mon Reg M-A
PYTHONPATH=src python3 -m pokemon_anti_meta_builder sync-moves --insecure
```

I file finiscono in `data/raw/`. Si rigenerano in qualunque momento.

## Avvio UI

```bash
PYTHONPATH=src python3 -m pokemon_anti_meta_builder serve \
  --format reg-ma \
  --input data/raw/reg_ma_pokekipe.csv \
  --dex data/raw/showdown_dex.json \
  --learnsets data/raw/showdown_learnsets.json \
  --port 8765
```

Apri http://127.0.0.1:8765.

### Attivare l'AI Coach (Gemini, gratis)

1. Vai su https://aistudio.google.com → login con Google.
2. Clicca "**Get API key**" → copia la chiave (formato `AIzaSy...`).
3. Rilancia il server con la chiave:

```bash
GEMINI_API_KEY=AIzaSy... PYTHONPATH=src python3 -m pokemon_anti_meta_builder serve [...stessi args]
```

Free tier: 15 req/min, 1500 req/giorno. Senza la chiave, l'AI Coach mostra un fallback deterministico ricco (digest dei threats + suggerimenti).

## CLI commands

| Comando | Scopo |
|---|---|
| `build` | Genera un team deterministico e lo esporta in formato Showdown |
| `fetch` | Scarica un file di stats Smogon-chaos pubblico |
| `sync-meta` | Aggiorna il CSV meta da Pokékipe |
| `sync-dex` | Scarica/slim il pokedex Showdown a Reg M-A |
| `sync-moves` | Scarica/slim moves + learnsets gen 9 |
| `sync-calc` | Best-effort download del bundle `@smogon/calc` browser |
| `serve` | Avvia la UI locale |

## Architettura

```
src/pokemon_anti_meta_builder/
├── data_fetcher/        # Pokékipe + Showdown + Smogon fetch & slim
├── meta_parser/         # CSV/JSON → model interno
├── format_rules/        # Whitelist Reg M-A (Pokémon + items)
├── team_builder/        # Selezione 6 Pokémon (scoring)
├── set_builder/         # Item/ability/moves/EVs/nature per ogni mon
├── threat_analyzer/     # Severity-based threat report (Pokékipe / type fallback)
├── damage_calc/         # Formula gen 9 Champions scale + speed compare
├── recommendations/     # RecommendationService (engine orchestratore)
├── ai_coach/            # Wrapper Gemini opzionale
├── showdown_exporter/   # Export Showdown (convert 0-32 → 0-252)
├── web/                 # Server HTTP + UI statica
└── cli/                 # CLI argparse
```

## Tab della UI

- **Build** — Recommendations + Synergy notes
- **Matchup** — Threats (top 20 meta) + Counters per ogni mon del team
- **Lookup** — Cerca un Pokémon → vedi i suoi counter (meta + off-meta)
- **Damage Calc** — Calc gen 9 con stats live, Tailwind/Trick Room, boost steppers
- **Coach & Export** — AI coach (Gemini) + export Showdown

## Note

- Engine deterministico: niente generative AI nel cuore (legalità, scoring, validation).
- Pokékipe espone `checks_counters` come campo nell'API ma per Reg M-A restituisce lista vuota. Il codice è pronto: appena Pokékipe popolerà il campo, lo userà automaticamente.
- Mega Evolution: l'engine considera tipi/stats/ability della forma Mega quando il mon ha la Mega Stone (item-driven).
- EV scale: scala Pokémon Champions (0-32 per stat, ~66 totali). L'export Showdown converte automaticamente in 0-252 per compatibilità.

## Attribuzioni

- **Pokémon Showdown** (MIT) — pokedex, moves, learnsets, abilities.
- **Pokékipe Public API** (CC BY 4.0) — meta usage, spreads, teammates.
- **Smogon damage-calc** (MIT) — `@smogon/calc` bundle opzionale browser-side.
- **PokeAPI sprites** (CC BY 4.0) — sprite ufficiali per la UI.

## Test

Niente pytest installato di default. Si gira via unittest:

```bash
PYTHONPATH=src python3 -m unittest discover tests
```

oppure con `pytest` se l'hai installato.

## License

Code in this repo is released for personal/educational use. Refer to each dataset's license for attribution requirements.
