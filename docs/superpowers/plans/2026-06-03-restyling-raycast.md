# Restyling Raycast + IA a 4 aree — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The visual-quality work should invoke the **frontend-design** skill; this plan provides the exact tokens, selectors, and IA structure to apply.

**Goal:** Restyle the web front-end to the Raycast design system and reorganize the information architecture from 6 overlapping tabs into 4 intent-based areas, without breaking the ~3115-line `app.js`.

**Architecture:** Three incremental phases. Phase 1 remaps the existing CSS custom properties in `:root` to Raycast tokens (every `var(--x)` across 1761 lines inherits the new look with zero structural change) plus Inter/ss03 and shadow removal. Phase 2 restructures the DOM (6 tabs → 4 areas) in `index.html` + `app.js`. Phase 3 polishes (type-color accents, assistant-first, responsive). No automated tests for CSS/markup — verification is `node --check`, an HTML parse check, the existing 59 Python tests staying green, and live visual checkpoints.

**Tech Stack:** Vanilla JS, CSS custom properties, `BaseHTTPRequestHandler` server. Front-end files: `src/pokemon_anti_meta_builder/web/static/{index.html,app.js,styles.css}`.

**Conventions:**
- Branch `main`, commit locally only. NO push / no PR without Matteo's explicit ok.
- After any `app.js` edit: `node --check src/pokemon_anti_meta_builder/web/static/app.js`.
- After any `index.html` edit: parse check (command below).
- Python suite must stay green: `PYTHONPATH=src python3 -m unittest discover -s tests` (59 OK).
- Reference: `/Users/matteoaldi/awesome-design-md/design-md/raycast/DESIGN.md`.

Parse-check command (reused throughout):
```bash
PYTHONPATH=src python3 -c "import pathlib,html.parser; html.parser.HTMLParser().feed(pathlib.Path('src/pokemon_anti_meta_builder/web/static/index.html').read_text()); print('html parse ok')"
```

---

## FASE 1 — Token Raycast (solo styles.css)

### Task 1: Rimappare il :root ai token Raycast

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/styles.css:1-45` (`:root` block)

- [ ] **Step 1: Sostituire i valori delle variabili surface/line/text**

Replace the existing `:root` color block (lines ~5-23, NOT the type-colors block) with the Raycast surface ladder, keeping the SAME variable names so the rest of the CSS inherits automatically:

```css
:root {
  color-scheme: dark;
  /* Raycast design system — near-black surface ladder, hairline borders,
     white CTA, no shadows. Variable names preserved so the whole stylesheet
     inherits the new look without per-rule edits. */
  --bg: #07080a;            /* canvas */
  --bg-soft: #0d0d0d;       /* surface */
  --panel: #0d0d0d;         /* surface (cards) */
  --panel-soft: #101111;    /* surface-elevated (inputs, buttons) */
  --surface-card: #121212;  /* command-palette row hover, icon tiles */
  --line: #242728;          /* hairline */
  --line-strong: rgba(255, 255, 255, 0.16);
  --text: #f4f4f6;          /* ink */
  --text-soft: #cdcdcd;     /* body */
  --muted: #9c9c9d;
  --muted-soft: #6a6b6c;
  /* Primary action is WHITE in Raycast (was lavender). --red is the legacy
     accent name used across the sheet; remap it to white so CTAs/active states
     become the Raycast white pill. Task 3 fixes spots where white-on-white
     breaks. */
  --red: #ffffff;
  --red-soft: rgba(255, 255, 255, 0.72);
  /* Raycast saturated semantic accents (warning/danger/ok/info) */
  --green: #59d499;
  --green-soft: rgba(89, 212, 153, 0.15);
  --gold: #ffc533;
  --gold-soft: rgba(255, 197, 51, 0.15);
  --blue: #57c1ff;
  --blue-soft: rgba(87, 193, 255, 0.15);
  --danger: #ff6161;
  --danger-soft: rgba(255, 97, 97, 0.15);
  --chip: #121212;
  --shadow: none;           /* Raycast builds depth from the surface ladder */
```

Keep the entire `/* Type colors (canonical) */` block and the closing `}` exactly as they are.

- [ ] **Step 2: Verifica caricamento**

Run the parse-check command (markup unchanged → still ok). Then start the server and eyeball:
```bash
PYTHONPATH=src python3 -m pokemon_anti_meta_builder serve --input data/raw/reg_ma_pokekipe.csv --dex data/raw/showdown_dex.json --learnsets data/raw/showdown_learnsets.json --pikalytics data/raw/pikalytics_sets.json &
sleep 3; curl -s -o /dev/null -w "/ -> %{code}\n" localhost:8765/; kill %1
```
Expected: `/ -> 200`. Visual: open localhost:8765 — surfaces should be near-black, borders hairline-grey.

- [ ] **Step 3: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "style(raycast): remap :root tokens to Raycast surface ladder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Inter + ss03, rimozione ombre, baseline tipografica

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/index.html` (add Inter font link in `<head>`)
- Modify: `src/pokemon_anti_meta_builder/web/static/styles.css` (body font-feature-settings; neutralize box-shadows)

- [ ] **Step 1: Caricare Inter nel `<head>`**

In `index.html`, inside `<head>` (before the stylesheet link), add:
```html
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
```

- [ ] **Step 2: Body font + ss03**

In `styles.css`, the `body` rule's `font-family` block: set Inter first and enable ss03. Replace the existing `font-family:` line in `body` with:
```css
  font-family: "Inter", "Inter Fallback", system-ui, -apple-system, sans-serif;
  font-feature-settings: "calt", "kern", "liga", "ss03";
```

- [ ] **Step 3: Neutralizzare le ombre residue**

`--shadow` is now `none`, but some rules may hardcode `box-shadow`. Find and soften them:
```bash
grep -n "box-shadow" src/pokemon_anti_meta_builder/web/static/styles.css
```
For each hardcoded `box-shadow` on cards/panels/sidebar (NOT focus outlines), replace the value with `none` or a `1px solid var(--line)` border if the shadow was the only edge. Leave `:focus` outline rules alone for now.

- [ ] **Step 4: Verifica**

Parse-check ok; `node --check` not needed (no JS). Live: text renders in Inter, no drop shadows on cards.

- [ ] **Step 5: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/index.html src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "style(raycast): Inter+ss03 typography, remove drop shadows

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Sistemare i punti dove l'accento bianco rompe

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/styles.css`

Remapping `--red` → white turns hover/active text white, which can produce white-on-white or invisible states. Fix them.

- [ ] **Step 1: Trovare gli usi dell'accento**
```bash
grep -n "var(--red)\|var(--red-soft)" src/pokemon_anti_meta_builder/web/static/styles.css
```

- [ ] **Step 2: Correggere caso per caso**

Apply these rules:
- **Primary buttons** (`button.primary`, submit/apply/auto-build): white background `var(--red)` + black text `#000` — this is correct Raycast, keep.
- **Hover text that became `color: var(--red)`** (e.g. `button:hover { color: var(--red-soft) }`): change to a surface lift instead — `background: var(--panel-soft); color: var(--text);` and drop the white text color.
- **Active tab / accent borders**: replace `var(--red)` border with `var(--line-strong)` (a brightened hairline) so the active state reads without a colored chrome accent.
- **Focus outline** `outline: 2px solid var(--red)`: change to `outline: 1px solid var(--line-strong); outline-offset: -1px;` (Raycast brightens the hairline on focus, no colored ring).
- **Topbar bottom border** `border-bottom: 3px solid var(--red)`: change to `1px solid var(--line)`.

- [ ] **Step 3: Verifica visiva**

Live server: hover buttons (should lift, not turn white-on-white), focus an input (hairline brightens), active tab readable, primary CTAs are white pills with black text.

- [ ] **Step 4: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "style(raycast): fix accent states (hover lift, hairline focus, white CTA)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Componenti chiave — pill-tab, command-palette-row, card, input

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/styles.css`

Invoke the **frontend-design** skill for this task — it produces the high-quality CSS for each component using the Raycast tokens. Apply to the existing class names so no markup changes are needed yet.

- [ ] **Step 1: Mappare i selettori reali**
```bash
grep -n "\.tab\b\|\.tab\.active\|\.mon-row\|\.counter-row\|\.slot\b\|\.calc-card\|\.search\b\|input\[type=\|\.assistant-msg\|\.proposal-card" src/pokemon_anti_meta_builder/web/static/styles.css | head -40
```

- [ ] **Step 2: Applicare i pattern Raycast (frontend-design skill)**

Restyle, keeping class names:
- `.tab` / `.tab.active` → Raycast `pill-tab`: `border-radius: 9999px; padding: 4px 10px; background: transparent; color: var(--text-soft);` active → `background: var(--panel-soft); color: var(--text);`
- `.mon-row`, `.counter-row` → `command-palette-row`: `border-radius: 6px; padding: 6px 10px;` hover → `background: var(--surface-card);` sprite tile 48px with `border-radius: 8px; background: var(--surface-card);`
- `.slot`, `.calc-card`, threat cards → `feature-card`: `background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px;` (no shadow).
- `.search`, `input[type=...]`, `textarea` → `text-input`: `background: var(--panel-soft); border: 1px solid var(--line); border-radius: 8px; height: 36px;` focus → `border-color: var(--line-strong);`
- `.assistant-msg.bot` / `.proposal-card` already exist — align radii to 8-10px and borders to `var(--line)`.

- [ ] **Step 3: Verifica visiva fase 1 completa**

Live server: tabs are pill chips, catalog/counter rows look like command-palette rows, cards are hairline-bordered surfaces, inputs are elevated surfaces. Run the Python suite (`59 OK`) to confirm nothing server-side broke.

- [ ] **Step 4: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "style(raycast): pill-tabs, command-palette rows, feature cards, inputs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 2 — Riorganizzazione IA (index.html + app.js)

> The tab system: buttons `<button class="tab" data-tab="X">` in `index.html` (lines ~87-92), panels `<section class="tab-panel" data-panel="X">`. `app.js` `selectTab(tabId)` (line ~468) toggles `.active` on `els.tabs` and `.hidden` on `els.panels` by matching `data-tab`/`data-panel`. Current tabs: build, matchup, lookup, calc, evtuner, extras(=Assistente).

### Task 5: Fondere Lookup dentro Analizza (matchup)

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/index.html`
- Modify: `src/pokemon_anti_meta_builder/web/static/app.js`

- [ ] **Step 1: Rinominare la tab matchup → "Analizza" e rimuovere il bottone Lookup**

In `index.html`: change the matchup tab button label to `Analizza`. Remove the `<button class="tab" data-tab="lookup">Lookup</button>` line.

- [ ] **Step 2: Spostare il markup di Lookup dentro il pannello matchup**

Move the contents of `<section data-panel="lookup">` (the `#lookupInput`, `#lookupOptions`, `#lookupResult` block) into the `data-panel="matchup"` section, under a sub-heading "Cerca counter di un Pokémon", below the existing team-counter + threats columns. Delete the now-empty `data-panel="lookup"` section.

- [ ] **Step 3: Verificare il JS del lookup**

`app.js` references `els.lookupInput/lookupOptions/lookupResult` and wires `runLookup` on input. These element IDs still exist (just moved), so the JS keeps working. Confirm no code calls `selectTab("lookup")`:
```bash
grep -n '"lookup"' src/pokemon_anti_meta_builder/web/static/app.js
```
If any `selectTab("lookup")` exists, change it to `selectTab("matchup")`.

- [ ] **Step 4: Verifica**

Parse-check ok; `node --check` ok. Live: Analizza tab shows team counters + threats + the single-mon counter search; Lookup tab is gone; searching a mon still works.

- [ ] **Step 5: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/index.html src/pokemon_anti_meta_builder/web/static/app.js
git commit -m "refactor(ia): fonde Lookup in Analizza (ex Matchup)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Unificare Damage Calc + EV Tuner in "Calcola"

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/index.html`
- Modify: `src/pokemon_anti_meta_builder/web/static/app.js`

- [ ] **Step 1: Una sola tab "Calcola" con due sotto-modi**

In `index.html`: replace the two tab buttons (`data-tab="calc"` and `data-tab="evtuner"`) with a single `<button class="tab" data-tab="calc">Calcola</button>`. Inside the `data-panel="calc"` section, add a sub-mode pill row at the top:
```html
<div class="subtabs" role="tablist">
  <button class="subtab active" data-subtab="damage" type="button">Damage Calc</button>
  <button class="subtab" data-subtab="evtuner" type="button">EV Tuner</button>
</div>
```
Then nest the existing damage-calc content under a `<div class="submode" data-submode="damage">` and move the entire `data-panel="evtuner"` content into a `<div class="submode hidden" data-submode="evtuner">` within the same `data-panel="calc"` section. Delete the old `data-panel="evtuner"` section.

- [ ] **Step 2: Wiring dei sotto-modi in app.js**

Add near `selectTab` in `app.js`:
```js
function selectCalcSubmode(name) {
  document.querySelectorAll('.subtab').forEach((b) => b.classList.toggle('active', b.dataset.subtab === name));
  document.querySelectorAll('.submode').forEach((m) => m.classList.toggle('hidden', m.dataset.submode !== name));
}
```
Wire it in the init/bind section (near `els.tabs.forEach`):
```js
  document.querySelectorAll('.subtab').forEach((b) =>
    b.addEventListener('click', () => selectCalcSubmode(b.dataset.subtab)));
```
Any existing `selectTab("evtuner")` (e.g. line ~3081 `openTuner`) must become:
```js
  selectTab("calc"); selectCalcSubmode("evtuner");
```
Find them:
```bash
grep -n '"evtuner"' src/pokemon_anti_meta_builder/web/static/app.js
```

- [ ] **Step 3: CSS per i subtab**

Add to `styles.css` (reuse pill-tab look):
```css
.subtabs { display: flex; gap: 6px; margin-bottom: 12px; }
.subtab { border-radius: 9999px; padding: 4px 10px; background: transparent; border: 1px solid var(--line); color: var(--text-soft); }
.subtab.active { background: var(--panel-soft); color: var(--text); }
.submode.hidden { display: none; }
```

- [ ] **Step 4: Verifica**

Parse-check ok; `node --check` ok. Live: one "Calcola" tab; the two pills switch between Damage Calc and EV Tuner; the "Tuna" icon on team slots still opens the EV Tuner pre-filled.

- [ ] **Step 5: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/index.html src/pokemon_anti_meta_builder/web/static/app.js src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "refactor(ia): unifica Damage Calc + EV Tuner in 'Calcola' (sotto-modi)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Rimuovere il dropdown counter/counterati dal Damage Calc

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/index.html`
- Modify: `src/pokemon_anti_meta_builder/web/static/app.js`

- [ ] **Step 1: Trovare il markup e il JS dei due dropdown**

The counter/counterati selects live on each calc-card. Locate:
```bash
grep -n "counter_lookup\|countered_by\|Counter (chi lo batte)\|Counterati" src/pokemon_anti_meta_builder/web/static/app.js
grep -n "counter\|counterati" src/pokemon_anti_meta_builder/web/static/index.html
```

- [ ] **Step 2: Rimuovere i due `<select>` dalle calc-card**

Remove the two dropdowns ("Counter (chi lo batte)" and "Counterati (chi batte)") from the calc-card template in `app.js` (the inline HTML that builds each calc card) and any static markup in `index.html`. Keep the rest of the calc-card (species, moves, EVs, result) intact.

- [ ] **Step 3: Rimuovere il JS morto**

Remove the event handlers that populated/handled those selects (the `fetchJson('/api/counter_lookup'...)` / `/api/countered_by` calls wired to the calc-card selects). The `/api/counter_lookup` and `/api/countered_by` endpoints STAY (used by Analizza); only the calc-card wiring is removed.

- [ ] **Step 4: Verifica**

`node --check` ok. Live: calc-cards no longer show the counter dropdowns; the Analizza tab still does counter search; damage calc still computes.

- [ ] **Step 5: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/index.html src/pokemon_anti_meta_builder/web/static/app.js
git commit -m "refactor(ia): togli dropdown counter dal Damage Calc (vive in Analizza)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Ordine aree + Assistente protagonista

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/index.html`

- [ ] **Step 1: Riordinare i 4 tab e rinominare Coach → Assistente**

The tab bar should read, in order: `Costruisci` (build) · `Analizza` (matchup) · `Calcola` (calc) · `Assistente` (extras). Rename the `data-tab="build"` label to `Costruisci`, and the `data-tab="extras"` label to `Assistente` (drop "Coach"). Keep `data-tab`/`data-panel` ids unchanged (build/matchup/calc/extras) so the JS keeps working.

- [ ] **Step 2: Rendere visibile l'assistente**

Add a small persistent entry point to the Assistente: in the topbar (`#coachButton` already exists and opens the chat) restyle it as a Raycast `button-tertiary` labelled "Assistente ⌘" so it's a visible launcher, not buried.

- [ ] **Step 3: Verifica**

Parse-check ok. Live: 4 tabs in order; Assistente reachable from the topbar and as the 4th tab.

- [ ] **Step 4: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/index.html
git commit -m "refactor(ia): 4 aree ordinate (Costruisci/Analizza/Calcola/Assistente)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## FASE 3 — Rifinitura

### Task 9: Type-colors come accenti categoria

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/styles.css`

- [ ] **Step 1: Trovare i chip-tipo**
```bash
grep -n "type-chip\|\.chip\b\|typeChip\|--t-" src/pokemon_anti_meta_builder/web/static/styles.css | head
```

- [ ] **Step 2: Applicare i type-colors come accenti soft**

Type chips should use the type color as a soft-background + colored text (Raycast category-accent pattern), e.g.:
```css
.type-chip { border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 500; border: 1px solid transparent; }
/* per-type: background uses the --t-<type> at ~18% via color-mix, text uses the solid type color */
.type-chip.fire { background: color-mix(in srgb, var(--t-fire) 18%, transparent); color: var(--t-fire); }
/* ...repeat for the 18 types using the existing --t-* vars... */
```
The chrome (buttons/tabs/surfaces) stays monochrome; type colors appear ONLY on type chips, sprites, and severity badges.

- [ ] **Step 3: Verifica + commit**

Live: type chips glow with their type color on the dark canvas; chrome stays monochrome.
```bash
git add src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "style(raycast): type-colors come accenti categoria sui chip-tipo

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Responsive / mobile (per il remote control da cell)

**Files:**
- Modify: `src/pokemon_anti_meta_builder/web/static/styles.css`

- [ ] **Step 1: Trovare il layout a colonne**
```bash
grep -n "grid-template-columns\|\.app\b\|\.sidebar\b\|\.workspace\b\|@media" src/pokemon_anti_meta_builder/web/static/styles.css | head
```

- [ ] **Step 2: Aggiungere i breakpoint Raycast**

Add at the end of `styles.css`:
```css
@media (max-width: 768px) {
  .app { grid-template-columns: 1fr; }           /* sidebar stacks above workspace */
  .sidebar { max-height: 40vh; overflow-y: auto; }
  .tabs { overflow-x: auto; }                     /* horizontal scroll for the pill tabs */
  .matchup-cols, .counter-2col, .calc-grid { grid-template-columns: 1fr; }
}
@media (max-width: 480px) {
  .assistant-log { max-height: 60vh; }
  .topbar h1 { font-size: 15px; }
}
```
Adjust the multi-column selector names to the real ones found in Step 1.

- [ ] **Step 3: Verifica**

Live: resize the browser narrow (or DevTools mobile) — sidebar stacks, tabs scroll, columns collapse, chat usable. This is what Matteo will see via remote-control on the phone.

- [ ] **Step 4: Commit**
```bash
git add src/pokemon_anti_meta_builder/web/static/styles.css
git commit -m "style(raycast): responsive — sidebar drawer, single-column, mobile chat

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Verifica finale end-to-end

**Files:** nessuno (solo verifica)

- [ ] **Step 1: Suite + syntax**
```bash
PYTHONPATH=src python3 -m unittest discover -s tests   # 59 OK
node --check src/pokemon_anti_meta_builder/web/static/app.js
```
Plus the parse-check command. All must pass.

- [ ] **Step 2: Smoke live di tutte le 4 aree**

Start the server (con o senza GEMINI_API_KEY). Click through: Costruisci (team+recommend), Analizza (counter team + threats + ricerca singola), Calcola (Damage Calc ↔ EV Tuner submodes), Assistente (chat). Confirm no console errors (`browser` devtools), no dead links, no leftover Lookup/EV-Tuner tabs.

- [ ] **Step 3: Aggiornare la memoria di progetto**

Update `project_pokemon_anti_meta_builder.md`: B13 frontend restyling fatto (Raycast + IA a 4 aree), elenco fasi, note su cosa è cambiato nei selettori/IA.

---

## Self-review (compilata in fase di scrittura)

- **Copertura spec:** token Raycast (Task 1-2), accenti/stati (Task 3), componenti (Task 4), IA 4 aree (Task 5 fonde Lookup, Task 6 unifica calc, Task 7 toglie dropdown, Task 8 ordina+assistente), type-colors (Task 9), mobile (Task 10), verifica (Task 11). Tutte le sezioni dello spec coperte.
- **Placeholder:** nessun TODO di logica. Gli step CSS dei Task 4/9/10 rimandano alla skill frontend-design per la qualità visiva ma forniscono token e selettori esatti — dichiarato, non è un placeholder.
- **Coerenza:** i `data-tab`/`data-panel` id (build/matchup/calc/extras) restano invariati tra i task; `selectTab`/`selectCalcSubmode` coerenti tra Task 6 e 8; le variabili CSS rimappate nel Task 1 sono usate coerentemente nei Task 3-4-9-10.
- **Note:** niente TDD sul CSS (non applicabile); verifica via node --check + parse-check + 59 test Python + checkpoint visivi live, come da spec.
