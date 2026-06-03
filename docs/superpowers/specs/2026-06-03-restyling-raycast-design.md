# Restyling Raycast + riorganizzazione IA — Design

**Data:** 2026-06-03
**Stato:** approvato (design), in attesa di piano di implementazione

## Problema

Il front-end (`web/static/`) funziona ma ha due problemi:
1. **Estetica** da migliorare — Matteo vuole un look curato partendo dai design
   system della repo `awesome-design-md`.
2. **Information architecture confusa** — funzioni ripetute e mal distribuite:
   il "counter" appare in 3 tab (Matchup, Lookup, dropdown del Damage Calc), i
   calcoli sono spalmati su 2 tab (Damage Calc + EV Tuner), e l'assistente chat
   rifà a parole quasi tutto il resto.

## Decisioni prese (brainstorm)

- **Stile base:** **Raycast** (`design-md/raycast/DESIGN.md`). Scelto perché è
  un'estetica da *strumento*: near-black, command-palette (ideale per la chat e
  le liste), hairline 1px, accenti saturati per categoria che mappano sui 18
  type-colors Pokémon. Densità dati eccellente per un tool VGC.
- **IA: 4 aree per intento** (da 6 tab a 4):
  1. **Costruisci** (ex Build)
  2. **Analizza** (fonde Matchup + Lookup)
  3. **Calcola** (unifica Damage Calc + EV Tuner)
  4. **Assistente** (chat IA, protagonista)
- **Approccio:** incrementale in 3 fasi (token → IA → rifinitura), NON big-bang,
  per non rompere i ~3115 righe di `app.js`.

## Token Raycast (la base visiva)

Da applicare in `styles.css` `:root` (sostituendo il tema Linear attuale):

- **Surface ladder (dark-only, niente ombre):** canvas `#07080a` →
  surface `#0d0d0d` → surface-elevated `#101111` → surface-card `#121212`.
  L'elevazione si costruisce SOLO dal gradino di colore, mai da `box-shadow`.
- **Hairline:** bordo 1px `#242728` su ogni card/sezione; `hairline-strong`
  `rgba(255,255,255,0.16)` per i divisori più marcati; focus input = hairline
  più forte, NON un ring colorato.
- **CTA primaria:** pill **bianca** `#ffffff` testo nero `#000` — azione
  primaria (Auto-build, Applica al team, Invia). Al massimo una pill bianca
  piena per "fold".
- **Testo:** ink `#f4f4f6` (titoli), body `#cdcdcd`, mute `#9c9c9d`,
  ash `#6a6b6c`.
- **Font:** Inter con `font-feature-settings: "calt","kern","liga","ss03"` sul
  body (la `g` alternata ss03 è la firma Raycast). Fallback `system-ui`.
- **Radius:** scala stretta 4/6/8/10/16px; pill `9999px`. Niente flat (0) sulle
  card, niente oltre 16px tranne le pill.
- **Accenti semantici** (giallo/rosso/verde/blu Raycast) per warning/danger/ok/
  info: `#ffc533` / `#ff6161` / `#59d499` / `#57c1ff` + varianti soft 15%.
- **Type-colors Pokémon (18 tipi, già nel CSS):** restano come **accenti
  categoria** (come i colori-estensione di Raycast) — usati su chip-tipo,
  sprite, mai sul chrome (bottoni/testo/superfici).

## Componenti (Raycast → nostri elementi)

| Nostro elemento | Componente Raycast | Note |
|---|---|---|
| Tab area | `pill-tab` / `pill-tab-active` | chip tondi; attivo = surface-elevated |
| Catalogo mon, liste counter, proposte assistente | `command-palette-row` | sprite 48px (`app-icon-tile`) + nome + chip-tipo + azione/keycap a destra |
| Chat assistente | `command-palette-card` | header + righe + input in basso (pattern nativo) |
| Team slot, calc card, threat card | `feature-card-dark` | surface + hairline 1px, padding 16–24px, no shadow |
| Input / search | `text-input` / `store-search-bar` | surface-elevated, focus = hairline-strong |
| Severità minaccia (danger/risky/safe) | accenti rosso/giallo/verde soft | badge-soft |
| Scorciatoie/azioni | `keycap` | glifo con gradiente sottile |

## IA dettagliata (4 aree)

1. **Costruisci** — team 6 slot, prossimi pick consigliati (con breakdown
   synergy/counter/teammate/meta), synergy notes, warnings.
2. **Analizza** — due modi nella stessa area:
   - *Team*: counter per ogni membro + "Minacce dal meta" (rich threats top-N).
   - *Singolo*: ricerca counter di un Pokémon qualsiasi (ex tab Lookup, con i
     reasons B8). I due modi condividono il layout delle command-palette-row.
3. **Calcola** — due sotto-modi:
   - *Damage Calc*: il calcolatore (engine reale @smogon/calc). Il dropdown
     "counter/counterati" viene RIMOSSO da qui (vive in Analizza).
   - *EV Tuner*: Survive / Outspeed / OHKO / Spread Maker (sub-tab attuali).
4. **Assistente** — la chat IA come `command-palette-card`, accessibile sempre,
   con pannello trace e proposte applicabili 1-click.

La **sidebar** resta (Team + catalogo + saved teams + filtri + ricerca per
nome/mossa), ridisegnata coi token Raycast.

## Mobile / responsive

- Sidebar → drawer collassabile (hamburger) sotto i 768px.
- Aree in single-column; le card stack verticali.
- La chat assistente deve restare comoda da telefono (serve per il remote
  control da cell).
- Breakpoint coerenti con Raycast: desktop 1280 / tablet 768 / mobile 480.

## Fasi di implementazione

1. **Token + componenti** (solo `styles.css`): surface ladder, hairline, Inter
   ss03, pill-tab, command-palette-row, feature-card, input. L'app resta
   strutturalmente identica ma cambia faccia. Checkpoint visivo immediato.
2. **Ristruttura IA** (`index.html` + `app.js`): 6 tab → 4 aree. Fondere
   Matchup+Lookup in Analizza; unificare Damage Calc+EV Tuner in Calcola;
   rimuovere il dropdown counter dal calc. Aggiornare `els`, `selectTab`,
   `data-tab`/`data-panel`, render. Area per area, testando il JS.
3. **Rifinitura**: type-colors come accenti categoria, assistente protagonista,
   responsive/mobile, keycap, stati, micro-spacing.

## Verifica

- Niente test automatici per il CSS/markup; verifica con `node --check app.js`
  dopo ogni modifica al JS e `html.parser` sul markup.
- Verifica visiva con server live (`serve`) a fine di ogni fase.
- I 59 test Python esistenti devono restare verdi (il front-end non li tocca).

## Non in scope (v1)

- Nuove funzionalità (è un restyling + riorganizzazione, non feature nuove).
- Light mode (Raycast è dark-only by design).
- Cambiare la logica engine/tool (solo presentazione e IA).
