# Assistente conversazionale (B11 v2) — Design

**Data:** 2026-06-03
**Stato:** approvato (design), in attesa di piano di implementazione

## Problema

Il "Coach AI" attuale è one-shot: un bottone che produce 4 sezioni fisse
(Valutazione / Minaccia chiave / Game plan / Fix prioritari) commentando lo stato
del team. Matteo lo vuole trasformare in un **assistente conversazionale** con
accesso all'intero dataset, capace di rispondere a domande operative tipo:

- "Fammi un Charizard che a +1 di Speed supera Aerodactyl max Speed → quanta
  velocità minima deve avere?"
- "Quale Pokémon conosce sia Flare Blitz che Follow Me?"
- "Chi batte Garchomp e perché?"

I numeri devono sempre venire dall'engine deterministico; Gemini orchestra e
verbalizza, non inventa valori. Coerente con la filosofia del progetto
("engine decide, LLM commenta").

## Decisioni prese (brainstorm)

- **Surface:** chat globale, sempre accessibile, funziona anche senza team
  caricato (vero assistente del dataset). Il vecchio report one-shot non è più
  usato dalla UI.
- **Tool v1:** tutte e quattro le categorie — ricerca mosse/mon, counter/matchup,
  EV calc (speed/survive/ohko), dati set/stats.
- **Azioni:** "propone + applichi con 1 click". L'assistente calcola set/spread
  completi e li mostra come card con bottone "Applica al team"; la scrittura la
  conferma l'utente. Nessuna scrittura autonoma.
- **Approccio:** A — agente Gemini function-calling. I numeri vengono solo dai
  tool deterministici.

## Architettura

Nuovo modulo `ai_coach/agent.py`. L'`advise` one-shot in `coach.py` resta per
retro-compatibilità ma non è più chiamato dalla UI.

Loop function-calling:

```
client → POST /api/assistant {messages:[...], teamState}
  → GeminiAgent.run():
      loop (max 6 giri):
        Gemini(messages + toolDeclarations)
        ├─ se functionCall → dispatch su ToolRegistry → risultato JSON → append → ricicla
        └─ se testo finale → ritorna {reply, proposals[], toolTrace[]}
```

- `messages`: storico conversazione (ruolo user/model), inviato dal client a ogni
  turno (stato lato client, niente sessione server).
- `teamState`: lo stato corrente del team (se presente), iniettato nel system
  prompt come contesto.
- Cap **6 giri** di tool per evitare loop infiniti e consumo quota.

## ToolRegistry (`ai_coach/tools.py`)

Wrapper sottili su `RecommendationService` + `EVTunerService`. Ogni tool ha:
schema JSON (per Gemini `function_declarations`) + funzione Python che chiama
l'engine e ritorna JSON compatto. Errori → `{ok: false, error}` (Gemini sa
spiegarli all'utente).

| Tool | Engine dietro | Esempio |
|---|---|---|
| `find_pokemon_by_moves(moves[], require_all=true)` | `move_users` intersezione | "chi conosce Flare Blitz E Follow Me" |
| `search_pokemon(type?, role?, min_usage?)` | catalog filter | "fairy veloci nel meta" |
| `get_learnset(species)` | `learnset_for` | "che mosse impara X" |
| `who_counters(species)` | `counter_lookup` (B8, con reasons) | "chi batte Garchomp e perché" |
| `countered_by(species)` | `countered_by` | "chi batte X" |
| `get_set(species)` | `combatant_payload` | item/ability/mosse/EV/base stats/forma mega |
| `min_speed_to_outspeed(species, target, condition?, our_boost?, target_spread?)` | EV outspeed **(esteso boost)** | "Charizard +1 vs Aerodactyl max" |
| `min_evs_to_survive(species, attacker, move, threshold?)` | EV survive | "regge Glacial Lance?" |
| `min_evs_to_ohko(species, target, move, goal?)` | EV ohko | "EV per OHKO Incineroar" |

### Estensione engine: boost nell'outspeed

`find_min_evs_to_outspeed` oggi accetta solo `condition`
(none/tailwind/scarf/paralysis). Per l'esempio "+1 Speed" va aggiunto un
parametro stage di boost (es. `our_boost: int = 0`, `target_boost: int = 0`) che
applica il moltiplicatore di stage (+1 → ×1.5, +2 → ×2.0, ecc.) alla Speed prima
del confronto. Cambio minimo, retro-compatibile (default 0 = comportamento
attuale). "max Speed" del target si risolve con un `target_spread` override
(252/max Spe, natura +Spe).

### Mappatura nomi (IT → canonico)

I nomi dataset sono in inglese. Gemini traduce i nomi italiani delle mosse/mon
("Bruciapelo" → "Flare Blitz") prima di chiamare i tool. I tool accettano nomi
canonici inglesi e usano `to_key` per il matching tollerante.

## Proposte applicabili (1 click)

Quando un tool produce un set/spread costruito, include un blocco `proposal`:
`{species, item, ability, nature, moves[], evs{}}`. L'agente raccoglie le
proposal in `proposals[]` nel response. La chat le renderizza come **card** con
bottone "Applica al team" → scrive su `state.overrides[species]` riusando il path
esistente degli overrides. Nessuna scrittura senza click dell'utente.

## UI Chat

Tab "Coach" diventa una finestra chat:

- Bolle user/assistant, input testuale + invio, storico in
  `state.assistantHistory`.
- Card-proposta inline con bottone "Applica al team".
- Pannello collassabile "🔧 ha usato: `min_speed_to_outspeed`, …" per trasparenza
  (quali tool ha chiamato e con quali argomenti/risultati).
- Funziona senza team; se un team è caricato, viene incluso nel contesto.
- Stile coerente con `.calc-card` esistente.

## Fallback / dipendenze

- Niente `GEMINI_API_KEY` → la chat mostra un hint di setup e disabilita l'input;
  i tool restano usabili dal resto della UI (Lookup, EV Tuner, ecc.). Niente
  parser NL deterministico (YAGNI: la key c'è).
- Modello primario `gemini-2.5-flash` (tool-use più affidabile del lite),
  fallback chain `flash-lite → flash-latest → 2.0-flash` su 429/503.
- Cap 6 giri tool per turno.

## Test

- `tests/test_assistant_tools.py`: ogni tool sull'engine reale (intersezione
  mosse, outspeed con boost, survive, who_counters) — `unittest.TestCase`, niente
  rete.
- Estensione outspeed boost: test dedicati (+1/+2 stage, default 0 invariato).
- Loop agente: mock della risposta Gemini (niente rete) → verifica dispatch tool,
  parse della functionCall, raccolta `proposals`.

## Scope / consegna

È il pezzo più grosso della rassegna funzione-per-funzione. Si può spezzare in 2
tappe:

1. **Engine + tool**: ToolRegistry, estensione outspeed boost, test tool.
2. **Agente + chat UI**: `agent.py`, endpoint `/api/assistant`, chat front-end,
   card-proposta.

## Non in scope (v1)

- Scrittura autonoma nel team (solo proposte con click).
- Parser NL deterministico offline.
- Memoria conversazione lato server (lo storico vive nel client).
- Tool spread-maker/bulk completo (resta nella tab dedicata; l'assistente v1 si
  ferma a outspeed/survive/ohko).
