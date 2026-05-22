const state = {
  catalog: null,
  archetype: "balance",
  selected: [],
  query: "",
  activeTab: "threats",
  counters: null,
  overrides: {},
};

const els = {
  autoBuildButton: document.querySelector("#autoBuildButton"),
  coachButton: document.querySelector("#coachButton"),
  clearButton: document.querySelector("#clearButton"),
  teamSlots: document.querySelector("#teamSlots"),
  teamDigest: document.querySelector("#teamDigest"),
  catalogList: document.querySelector("#catalogList"),
  searchInput: document.querySelector("#searchInput"),
  recommendations: document.querySelector("#recommendations"),
  synergyPanel: document.querySelector("#synergyPanel"),
  threatReport: document.querySelector("#threatReport"),
  threatCards: document.querySelector("#threatCards"),
  warningsPanel: document.querySelector("#warningsPanel"),
  coachPanel: document.querySelector("#coachPanel"),
  showdownExport: document.querySelector("#showdownExport"),
  countersPanel: document.querySelector("#countersPanel"),
  refreshCountersButton: document.querySelector("#refreshCountersButton"),
  calcPanel: document.querySelector("#calcPanel"),
  lookupInput: document.querySelector("#lookupInput"),
  lookupOptions: document.querySelector("#lookupOptions"),
  lookupResult: document.querySelector("#lookupResult"),
  tabs: document.querySelectorAll(".tab"),
  panels: document.querySelectorAll(".tab-panel"),
};

async function init() {
  state.catalog = await fetchJson("/api/catalog");
  bindEvents();
  await refresh();
}

function bindEvents() {
  els.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.toLowerCase();
    renderCatalog();
  });
  els.clearButton.addEventListener("click", async () => {
    state.selected = [];
    els.coachPanel.textContent = "";
    await refresh();
  });
  els.autoBuildButton.addEventListener("click", autoBuild);
  els.coachButton.addEventListener("click", askCoach);
  els.tabs.forEach((tab) => {
    tab.addEventListener("click", () => selectTab(tab.dataset.tab));
  });
  if (els.lookupInput) {
    let debounce;
    els.lookupInput.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(runLookup, 250);
    });
  }
  initCalc();
  populateLookupDatalist();
}

function populateLookupDatalist() {
  if (!els.lookupOptions || !state.catalog) return;
  const baseOpts = state.catalog.pokemon.map((mon) => `<option value="${escapeHtml(mon.name)}"></option>`);
  const megaOpts = (state.catalog.megaForms || []).map((form) =>
    `<option value="${escapeHtml(form.name)}">Mega form of ${escapeHtml(form.baseSpecies)}</option>`
  );
  els.lookupOptions.innerHTML = [...baseOpts, ...megaOpts].join("");
}

async function runLookup() {
  const name = (els.lookupInput.value || "").trim();
  if (!name) {
    els.lookupResult.innerHTML = "";
    return;
  }
  let data;
  try {
    data = await fetchJson(`/api/counter_lookup?name=${encodeURIComponent(name)}`);
  } catch (error) {
    els.lookupResult.innerHTML = `<div class="note">Errore: ${escapeHtml(error.message)}</div>`;
    return;
  }
  if (data.notFound) {
    els.lookupResult.innerHTML = `<div class="note">Nessun Pokémon trovato per "${escapeHtml(name)}".</div>`;
    return;
  }
  const sourceChip = data.source === "pokekipe"
    ? chip("Pokékipe", "green")
    : chip("type-based", "gray");
  const typesChips = (data.types || []).map((t) => typeChip(t)).join(" ");
  const metaCounters = (data.counters || []).filter((c) => !c.offMeta);
  const offMetaCounters = (data.counters || []).filter((c) => c.offMeta);
  const renderRow = (c) => {
    const num = numForName(c.name);
    return `
      <div class="counter-row${c.offMeta ? " off-meta" : ""}">
        ${spriteImg(num, c.name, "counter-row-sprite")}
        <span>${escapeHtml(c.name)} ${(c.types || []).map((t) => typeChip(t)).join(" ")}${c.offMeta ? " " + chip("off-meta", "gray") : ""}</span>
        <span class="muted">${c.usage_vs ? c.usage_vs.toFixed(1) + "% vs · " : ""}${c.meta_usage ? "meta " + c.meta_usage.toFixed(1) + "%" : "fuori meta"}</span>
      </div>
    `;
  };
  const sections = [];
  if (metaCounters.length) {
    sections.push(`<div class="counter-section-title muted">Top meta picks</div>`);
    sections.push(metaCounters.map(renderRow).join(""));
  }
  if (offMetaCounters.length) {
    sections.push(`<div class="counter-section-title muted">Opzioni off-meta</div>`);
    sections.push(offMetaCounters.map(renderRow).join(""));
  }
  const subjectNum = numForName(data.name);
  els.lookupResult.innerHTML = `
    <div class="counter-group">
      <h3>${spriteImg(subjectNum, data.name, "counter-row-sprite")} <span>${escapeHtml(data.name)}</span> ${typesChips} ${sourceChip} ${data.offMeta ? chip("off-meta", "gray") : ""}</h3>
      <div class="counter-list">${sections.join("") || '<div class="muted">Nessun counter individuato.</div>'}</div>
    </div>
  `;
}

function selectTab(tabId) {
  state.activeTab = tabId;
  els.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabId));
  els.panels.forEach((panel) => panel.classList.toggle("hidden", panel.dataset.panel !== tabId));
}

function renderCounters(data) {
  if (!data || !data.members || !data.members.length) {
    els.countersPanel.innerHTML = '<div class="note">No data.</div>';
    return;
  }
  els.countersPanel.innerHTML = data.members
    .map((member) => {
      const tag = member.source === "pokekipe"
        ? chip("Pokékipe data", "green")
        : chip("type-based fallback", "gray");
      const megaChip = member.isMega ? chip("Mega", "gold") : "";
      const rows = member.counters.length
        ? member.counters
            .map((entry) => {
              const num = numForName(entry.name);
              return `
                <div class="counter-row">
                  ${spriteImg(num, entry.name, "counter-row-sprite")}
                  <span>${escapeHtml(entry.name)}</span>
                  <span class="muted">${entry.usage ? entry.usage.toFixed(1) + "% vs · " : ""}meta ${entry.meta_usage ? entry.meta_usage.toFixed(1) : "?"}%</span>
                </div>
              `;
            })
            .join("")
        : '<div class="muted">Nessuna minaccia individuata.</div>';
      const memberNum = numForName(member.baseSpecies || member.species);
      return `
        <div class="counter-group">
          <h3>${spriteImg(memberNum, member.species, "counter-row-sprite")} <span>${escapeHtml(member.species)}</span> ${megaChip} ${member.offMeta ? chip("off-meta", "gray") : ""} ${tag}</h3>
          <div class="counter-list">${rows}</div>
        </div>
      `;
    })
    .join("");
}

async function autoBuild() {
  const data = await fetchJson("/api/autobuild", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected: state.selected, overrides: state.overrides }),
  });
  state.selected = data.selected;
  renderState(data);
}

async function askCoach() {
  selectTab("extras");
  els.coachPanel.textContent = "Thinking...";
  const data = await fetchJson("/api/coach", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected: state.selected, overrides: state.overrides }),
  });
  const lines = [];
  if (data.needsSetup && data.setupHint) {
    lines.push(data.setupHint);
    lines.push("\n---\n");
  }
  if (data.error) lines.push(`(errore: ${data.error})\n`);
  lines.push(data.advice || "No advice returned.");
  els.coachPanel.textContent = lines.join("\n");
}

async function refresh() {
  const data = await fetchJson("/api/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      archetype: state.archetype,
      selected: state.selected,
      overrides: state.overrides,
    }),
  });
  renderState(data);
}

const calcState = {
  attacker: null,
  defender: null,
  moves: [],
  attackerLearnset: null,
  showAllMoves: false,
  field: {
    weather: "",
    terrain: "",
    spread: true,
    crit: false,
    lightScreen: false,
    reflect: false,
    auroraVeil: false,
    tailwind: false,
    trickRoom: false,
  },
};

function initCalc() {
  if (!els.calcPanel) return;
  els.calcPanel.innerHTML = `
    <div class="calc-grid">
      ${calcCardTemplate("attacker", "Attacker")}
      ${calcCardTemplate("defender", "Defender")}
    </div>
    <div class="calc-card">
      <label>Move
        <select id="calcMove"></select>
      </label>
      <label class="chip"><input type="checkbox" id="calcShowAllMoves" /> show all moves (ignore attacker learnset)</label>
      <div id="calcMoveHint" class="muted" style="font-size:12px"></div>
      <div class="calc-grid">
        <label>Weather
          <select id="calcWeather">
            <option value="">none</option>
            <option value="sun">sun</option>
            <option value="rain">rain</option>
            <option value="sand">sand</option>
            <option value="snow">snow</option>
          </select>
        </label>
        <label>Terrain
          <select id="calcTerrain">
            <option value="">none</option>
            <option value="electric">electric</option>
            <option value="grassy">grassy</option>
            <option value="psychic">psychic</option>
            <option value="misty">misty</option>
          </select>
        </label>
      </div>
      <div class="mon-meta">
        <label class="chip"><input type="checkbox" id="calcSpread" checked /> spread (doubles)</label>
        <label class="chip"><input type="checkbox" id="calcCrit" /> crit</label>
        <label class="chip"><input type="checkbox" id="calcReflect" /> reflect</label>
        <label class="chip"><input type="checkbox" id="calcLight" /> light screen</label>
        <label class="chip"><input type="checkbox" id="calcVeil" /> aurora veil</label>
        <label class="chip"><input type="checkbox" id="calcTailwind" /> tailwind (spe × 2)</label>
        <label class="chip"><input type="checkbox" id="calcTrickRoom" /> trick room (slow first)</label>
      </div>
      <div id="calcSpeedLive" class="calc-speed-live"></div>
      <button id="calcButton" class="primary" type="button">Calculate</button>
    </div>
    <div id="calcResultCard" class="calc-result-card hidden">
      <div id="calcVerdict" class="calc-verdict"></div>
      <div id="calcSpeed" class="calc-speed"></div>
      <div id="calcStatsGrid" class="calc-stats-grid"></div>
      <div id="calcRolls" class="muted calc-rolls"></div>
    </div>
    <div id="calcOutput" class="muted">Pick attacker, defender, and a move, then Calculate.</div>
  `;
  populateCalcDropdowns();
  document.querySelector("#calcButton").addEventListener("click", runCalc);
  ["calcSpread", "calcCrit", "calcReflect", "calcLight", "calcVeil", "calcTailwind", "calcTrickRoom"].forEach((id) => {
    document.querySelector("#" + id).addEventListener("change", () => {
      syncCalcField();
      updateLivePreview();
    });
  });
  ["calcWeather", "calcTerrain"].forEach((id) => {
    document.querySelector("#" + id).addEventListener("change", () => {
      syncCalcField();
      updateLivePreview();
    });
  });
  // Live preview on combatant card input changes
  document.querySelectorAll(".calc-card[data-role] input, .calc-card[data-role] select").forEach((el) => {
    el.addEventListener("input", updateLivePreview);
    el.addEventListener("change", updateLivePreview);
  });
  // Boost steppers
  document.querySelectorAll(".calc-card[data-role] .boost-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const stat = btn.dataset.boostStat;
      const delta = parseInt(btn.dataset.boostDelta, 10) || 0;
      const valueEl = btn.closest(".calc-card").querySelector(`[data-boost-value='${stat}']`);
      if (!valueEl) return;
      const current = parseInt(valueEl.textContent, 10) || 0;
      const next = Math.max(-6, Math.min(6, current + delta));
      valueEl.textContent = next > 0 ? `+${next}` : `${next}`;
      valueEl.classList.toggle("boost-positive", next > 0);
      valueEl.classList.toggle("boost-negative", next < 0);
      updateLivePreview();
    });
  });
}

const NATURE_MODIFIERS_JS = {
  Adamant: { atk: 1.1, spa: 0.9 },
  Modest: { spa: 1.1, atk: 0.9 },
  Jolly: { spe: 1.1, spa: 0.9 },
  Timid: { spe: 1.1, atk: 0.9 },
  Bold: { def: 1.1, atk: 0.9 },
  Impish: { def: 1.1, spa: 0.9 },
  Calm: { spd: 1.1, atk: 0.9 },
  Careful: { spd: 1.1, spa: 0.9 },
  Naive: { spe: 1.1, spd: 0.9 },
  Hasty: { spe: 1.1, def: 0.9 },
  Brave: { atk: 1.1, spe: 0.9 },
  Quiet: { spa: 1.1, spe: 0.9 },
  Relaxed: { def: 1.1, spe: 0.9 },
  Sassy: { spd: 1.1, spe: 0.9 },
  Mild: { spa: 1.1, def: 0.9 },
  Lonely: { atk: 1.1, def: 0.9 },
  Naughty: { atk: 1.1, spd: 0.9 },
  Rash: { spa: 1.1, spd: 0.9 },
  Gentle: { spd: 1.1, def: 0.9 },
};

function computeStat(base, ev, iv, level, nature, key) {
  // Pokemon Champions EV scale (0-32 per stat). Compared to gen 9 standard
  // floor(ev/4) on 0-252, Champions uses 2 * ev on 0-32 which yields the
  // same +32-ish stat points at the cap.
  if (!base) return 0;
  const evTerm = ev * 2;
  if (key === "hp") {
    return Math.floor(((2 * base + iv + evTerm) * level) / 100) + level + 10;
  }
  const raw = Math.floor(((2 * base + iv + evTerm) * level) / 100) + 5;
  const mod = (NATURE_MODIFIERS_JS[nature] || {})[key] || 1.0;
  return Math.floor(raw * mod);
}

function computeAllStats(combatant) {
  const order = ["hp", "atk", "def", "spa", "spd", "spe"];
  const out = {};
  for (const k of order) {
    out[k] = computeStat(combatant.baseStats?.[k] || 0, combatant.evs?.[k] || 0, 31, combatant.level || 50, combatant.nature, k);
  }
  return out;
}

function boostedStatJS(stat, boost) {
  const b = Math.max(-6, Math.min(6, boost || 0));
  if (b >= 0) return Math.floor(stat * (2 + b) / 2);
  return Math.floor(stat * 2 / (2 + Math.abs(b)));
}

function effectiveSpeedJS(combatant, field) {
  const stats = computeAllStats(combatant);
  let speed = boostedStatJS(stats.spe, combatant.boosts?.spe || 0);
  if (field.tailwind) speed *= 2;
  if (combatant.isParalyzed) speed = Math.floor(speed * 0.5);
  return speed;
}

function updateLivePreview() {
  syncCalcField();
  ["attacker", "defender"].forEach((role) => {
    const card = document.querySelector(`.calc-card[data-role='${role}']`);
    const target = card?.querySelector("[data-live-stats]");
    if (!target) return;
    const combatant = collectCombatant(role);
    const placeholder = !combatant;
    const stats = placeholder ? { hp: 0, atk: 0, def: 0, spa: 0, spd: 0, spe: 0 } : computeAllStats(combatant);
    const boosts = combatant?.boosts || {};
    const rows = ["hp", "atk", "def", "spa", "spd", "spe"].map((k) => {
      const boost = boosts[k] || 0;
      const badge = boost ? `<span class="chip ${boost > 0 ? 'gold' : 'red'}">${boost > 0 ? '+' : ''}${boost}</span>` : "";
      const valueText = placeholder ? '<span class="muted">—</span>' : stats[k];
      return `<div class="stat-row"><span>${k.toUpperCase()}</span><span>${valueText} ${badge}</span></div>`;
    }).join("");
    target.innerHTML = `<div class="stats-block-title">Stats live</div>${rows}`;
  });
  updateSpeedLive();
}

function updateSpeedLive() {
  const el = document.querySelector("#calcSpeedLive");
  if (!el) return;
  const attacker = collectCombatant("attacker");
  const defender = collectCombatant("defender");
  if (!attacker || !defender) {
    el.innerHTML = `<span class="chip gray">Speed</span> <span class="muted">scegli attacker e defender per il confronto</span>`;
    return;
  }
  const field = calcState.field;
  const aSpeed = effectiveSpeedJS(attacker, field);
  const dSpeed = effectiveSpeedJS(defender, field);
  let verdict;
  if (field.trickRoom) {
    if (aSpeed < dSpeed) verdict = `<strong>${escapeHtml(attacker.name)}</strong> prima (Trick Room: ${aSpeed} &lt; ${dSpeed})`;
    else if (aSpeed > dSpeed) verdict = `<strong>${escapeHtml(defender.name)}</strong> prima (Trick Room: ${dSpeed} &lt; ${aSpeed})`;
    else verdict = `pari (Trick Room, ${aSpeed} a testa)`;
  } else {
    if (aSpeed > dSpeed) verdict = `<strong>${escapeHtml(attacker.name)}</strong> prima (${aSpeed} vs ${dSpeed})`;
    else if (aSpeed < dSpeed) verdict = `<strong>${escapeHtml(defender.name)}</strong> prima (${dSpeed} vs ${aSpeed})`;
    else verdict = `parità velocità (${aSpeed} a testa)`;
  }
  el.innerHTML = `<span class="chip green">Speed</span> ${verdict}`;
}

function calcCardTemplate(role, label) {
  return `
    <div class="calc-card" data-role="${role}">
      <strong>${label}</strong>
      <label>Pokemon
        <select data-field="name"></select>
      </label>
      <label>Nature
        <select data-field="nature"></select>
      </label>
      <div class="calc-evs">
        <div class="calc-evs-head muted">EVs Champions (0-32 per stat)</div>
        <div class="calc-evs-grid">
          ${["hp","atk","def","spa","spd","spe"].map((s) => `
            <label>${s.toUpperCase()}
              <input data-ev="${s}" type="number" min="0" max="32" step="1" value="0" />
            </label>
          `).join("")}
        </div>
      </div>
      <div class="calc-boosts">
        <div class="calc-boosts-head muted">Boosts (-6 ÷ +6)</div>
        <div class="calc-boosts-grid">
          ${["atk","def","spa","spd","spe"].map((s) => `
            <div class="boost-cell">
              <span class="boost-label">${s.toUpperCase()}</span>
              <div class="boost-controls">
                <button type="button" class="boost-btn" data-boost-stat="${s}" data-boost-delta="-1">−</button>
                <span class="boost-value" data-boost-value="${s}">0</span>
                <button type="button" class="boost-btn" data-boost-stat="${s}" data-boost-delta="1">+</button>
              </div>
            </div>
          `).join("")}
        </div>
      </div>
      <label>Tera type
        <input data-field="teraType" placeholder="" />
      </label>
      <div class="calc-card-flags">
        <label class="chip"><input type="checkbox" data-field="isBurned" /> burn (atk × 0.5)</label>
        <label class="chip"><input type="checkbox" data-field="isParalyzed" /> para (spe × 0.5)</label>
      </div>
      <div class="live-stats" data-live-stats></div>
    </div>
  `;
}

async function populateCalcDropdowns() {
  const [moves, names] = await Promise.all([
    fetchJson("/api/calc/moves"),
    Promise.resolve(state.catalog.pokemon.map((mon) => mon.name)),
  ]);
  calcState.moves = moves.moves;
  renderCalcMoveDropdown();
  ["attacker", "defender"].forEach((role) => {
    const card = document.querySelector(`.calc-card[data-role='${role}']`);
    const nameSelect = card.querySelector("[data-field='name']");
    nameSelect.innerHTML = '<option value="">(pick one)</option>' + names.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    nameSelect.addEventListener("change", async () => {
      if (!nameSelect.value) return;
      const data = await fetchJson(`/api/combatant?name=${encodeURIComponent(nameSelect.value)}`);
      if (data.error) return;
      calcState[role] = data;
      ["hp","atk","def","spa","spd","spe"].forEach((s) => {
        const el = card.querySelector(`[data-ev='${s}']`);
        if (el) el.value = (data.evs && data.evs[s]) || 0;
      });
      const natureField = card.querySelector("[data-field='nature']");
      natureField.innerHTML = Object.keys(NATURES).map((n) => `<option value="${n}" ${n === data.nature ? "selected" : ""}>${n}</option>`).join("");
      const teraField = card.querySelector("[data-field='teraType']");
      teraField.value = "";
      if (role === "attacker") {
        await loadAttackerLearnset(nameSelect.value);
      }
      updateLivePreview();
    });
    card.querySelector("[data-field='nature']").innerHTML = Object.keys(NATURES).map((n) => `<option value="${n}">${n}</option>`).join("");
  });
  document.querySelector("#calcShowAllMoves").addEventListener("change", (event) => {
    calcState.showAllMoves = event.target.checked;
    renderCalcMoveDropdown();
  });
  syncCalcField();
  updateLivePreview();
}

async function loadAttackerLearnset(name) {
  try {
    const data = await fetchJson(`/api/learnset?name=${encodeURIComponent(name)}`);
    calcState.attackerLearnset = data;
  } catch (error) {
    calcState.attackerLearnset = null;
  }
  renderCalcMoveDropdown();
}

function renderCalcMoveDropdown() {
  const select = document.querySelector("#calcMove");
  const hint = document.querySelector("#calcMoveHint");
  const learnset = calcState.attackerLearnset;
  const all = calcState.moves || [];
  let moves = all;
  let hintText = `${all.length} moves total.`;
  if (learnset && learnset.hasLearnset && !calcState.showAllMoves) {
    const legalSet = new Set(learnset.calcable || []);
    moves = all.filter((m) => legalSet.has(m));
    hintText = `${moves.length} legal moves for ${learnset.name} (toggle to see all ${all.length}).`;
  } else if (learnset && !learnset.hasLearnset) {
    hintText = `${all.length} moves total. (no learnset loaded for ${learnset.name} - run sync-moves)`;
  }
  if (!moves.length) moves = all;
  select.innerHTML = moves.map((move) => `<option value="${escapeHtml(move)}">${escapeHtml(move)}</option>`).join("");
  hint.textContent = hintText;
}

const NATURES = {
  Hardy: 1, Adamant: 1, Modest: 1, Jolly: 1, Timid: 1, Bold: 1, Impish: 1, Calm: 1,
  Careful: 1, Naive: 1, Hasty: 1, Brave: 1, Quiet: 1, Relaxed: 1, Sassy: 1, Mild: 1,
  Lonely: 1, Naughty: 1, Rash: 1, Gentle: 1,
};

function formatEvs(evs) {
  return `${evs.hp} / ${evs.atk} / ${evs.def} / ${evs.spa} / ${evs.spd} / ${evs.spe}`;
}

function parseEvs(text) {
  const parts = String(text || "").split("/").map((p) => parseInt(p.trim(), 10) || 0);
  while (parts.length < 6) parts.push(0);
  const [hp, atk, def_, spa, spd, spe] = parts;
  return { hp, atk, def: def_, spa, spd, spe };
}

function parseBoosts(text) {
  const out = { atk: 0, def: 0, spa: 0, spd: 0, spe: 0 };
  String(text || "").split(/[\s,]+/).filter(Boolean).forEach((token) => {
    const match = token.match(/^(atk|def|spa|spd|spe)([+-]?\d+)$/i);
    if (match) out[match[1].toLowerCase()] = parseInt(match[2], 10) || 0;
  });
  return out;
}

function syncCalcField() {
  calcState.field = {
    weather: document.querySelector("#calcWeather").value,
    terrain: document.querySelector("#calcTerrain").value,
    spread: document.querySelector("#calcSpread").checked,
    crit: document.querySelector("#calcCrit").checked,
    reflect: document.querySelector("#calcReflect").checked,
    lightScreen: document.querySelector("#calcLight").checked,
    auroraVeil: document.querySelector("#calcVeil").checked,
    tailwind: document.querySelector("#calcTailwind")?.checked || false,
    trickRoom: document.querySelector("#calcTrickRoom")?.checked || false,
  };
}

function collectCombatant(role) {
  const base = calcState[role];
  if (!base) return null;
  const card = document.querySelector(`.calc-card[data-role='${role}']`);
  const nature = card.querySelector("[data-field='nature']").value;
  const evs = {};
  ["hp","atk","def","spa","spd","spe"].forEach((s) => {
    const el = card.querySelector(`[data-ev='${s}']`);
    const v = el ? parseInt(el.value, 10) : 0;
    evs[s] = Number.isFinite(v) ? Math.max(0, Math.min(32, v)) : 0;
  });
  const boosts = {};
  ["atk","def","spa","spd","spe"].forEach((s) => {
    const el = card.querySelector(`[data-boost-value='${s}']`);
    boosts[s] = el ? (parseInt(el.textContent, 10) || 0) : 0;
  });
  const teraType = (card.querySelector("[data-field='teraType']").value || "").trim().toLowerCase() || null;
  const isBurned = card.querySelector("[data-field='isBurned']").checked;
  const isParalyzed = card.querySelector("[data-field='isParalyzed']")?.checked || false;
  return { ...base, nature, evs, boosts, teraType, isBurned, isParalyzed };
}

async function runCalc() {
  const attacker = collectCombatant("attacker");
  const defender = collectCombatant("defender");
  const move = document.querySelector("#calcMove").value;
  const outputEl = document.querySelector("#calcOutput");
  const cardEl = document.querySelector("#calcResultCard");
  if (!attacker || !defender || !move) {
    outputEl.textContent = "Pick attacker, defender, and a move, then Calculate.";
    outputEl.classList.remove("hidden");
    cardEl.classList.add("hidden");
    return;
  }
  let response;
  if (window.calc && window.calc.calculate) {
    try {
      const text = computeWithSmogonCalc(attacker, defender, move, calcState.field);
      response = { ok: true, smogonText: text };
    } catch (error) {
      console.warn("smogon calc failed, falling back to lite calc", error);
    }
  }
  if (!response) {
    response = await fetchJson("/api/damage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ attacker, defender, move, field: calcState.field }),
    });
  }
  if (!response.ok) {
    outputEl.textContent = `Error: ${response.error}`;
    outputEl.classList.remove("hidden");
    cardEl.classList.add("hidden");
    return;
  }
  renderCalcResult(attacker, defender, move, response);
}

function renderCalcResult(attacker, defender, move, response) {
  const outputEl = document.querySelector("#calcOutput");
  const cardEl = document.querySelector("#calcResultCard");
  outputEl.classList.add("hidden");
  cardEl.classList.remove("hidden");

  const r = response.result || {};
  const verdict = document.querySelector("#calcVerdict");
  const typeChip = `<span class="chip ${typeTone(r.type)}">${escapeHtml(r.type || "?")}</span>`;
  const catChip = `<span class="chip">${escapeHtml(r.category || "?")}</span>`;
  verdict.innerHTML = `
    <div class="calc-headline">
      <strong>${escapeHtml(attacker.name)}</strong>
      <span class="muted">→ ${escapeHtml(move)} →</span>
      <strong>${escapeHtml(defender.name)}</strong>
    </div>
    <div class="calc-damage">${r.min}–${r.max} HP <span class="muted">(${r.minPercent}%–${r.maxPercent}%)</span></div>
    <div class="calc-ko">${escapeHtml(r.koChance || "")} ${typeChip} ${catChip}</div>
  `;

  const speedEl = document.querySelector("#calcSpeed");
  if (response.speed) {
    const a = response.speed.attacker;
    const d = response.speed.defender;
    const verdictText = response.speed.verdict;
    speedEl.innerHTML = `<span class="chip green">Speed</span> ${escapeHtml(verdictText)}`;
  } else {
    speedEl.textContent = "";
  }

  const statsGrid = document.querySelector("#calcStatsGrid");
  if (response.stats) {
    statsGrid.innerHTML = `
      ${statsBlock("Attacker", attacker.name, response.stats.attacker, attacker)}
      ${statsBlock("Defender", defender.name, response.stats.defender, defender)}
    `;
  } else {
    statsGrid.innerHTML = "";
  }

  const rollsEl = document.querySelector("#calcRolls");
  rollsEl.textContent = `Rolls (16): ${(r.rolls || []).join(" · ")}`;
}

function statsBlock(label, name, stats, combatant) {
  const order = ["hp", "atk", "def", "spa", "spd", "spe"];
  const rows = order.map((k) => {
    const value = stats[k] ?? 0;
    const boost = (combatant.boosts || {})[k] || 0;
    const boostBadge = boost ? `<span class="chip ${boost>0?'gold':'red'}">${boost>0?'+':''}${boost}</span>` : "";
    return `<div class="stat-row"><span>${k.toUpperCase()}</span><span>${value} ${boostBadge}</span></div>`;
  }).join("");
  return `
    <div class="stats-block">
      <div class="stats-block-title">${escapeHtml(label)}: <strong>${escapeHtml(name)}</strong> <span class="muted">${escapeHtml((combatant.nature || ""))}</span></div>
      ${rows}
    </div>
  `;
}

function typeTone(type) {
  return { fire: "red", water: "", grass: "green", electric: "gold", dragon: "", dark: "", fairy: "" }[type] || "";
}

function computeWithSmogonCalc(attacker, defender, move, field) {
  const gen = window.calc.Generations.get(9);
  const attackingMon = new window.calc.Pokemon(gen, attacker.name, {
    level: attacker.level,
    nature: attacker.nature,
    evs: attacker.evs,
    boosts: attacker.boosts,
    item: attacker.item,
    ability: attacker.ability,
    teraType: attacker.teraType || undefined,
    status: attacker.isBurned ? "brn" : "",
  });
  const defendingMon = new window.calc.Pokemon(gen, defender.name, {
    level: defender.level,
    nature: defender.nature,
    evs: defender.evs,
    boosts: defender.boosts,
    item: defender.item,
    ability: defender.ability,
    teraType: defender.teraType || undefined,
  });
  const moveObj = new window.calc.Move(gen, move, {
    isCrit: field.crit,
    isSpread: field.spread,
  });
  const fieldObj = new window.calc.Field({
    weather: field.weather ? field.weather.charAt(0).toUpperCase() + field.weather.slice(1) : "",
    terrain: field.terrain ? field.terrain.charAt(0).toUpperCase() + field.terrain.slice(1) : "",
    attackerSide: { isReflect: field.reflect, isLightScreen: field.lightScreen, isAuroraVeil: field.auroraVeil },
    defenderSide: { isReflect: field.reflect, isLightScreen: field.lightScreen, isAuroraVeil: field.auroraVeil },
  });
  const result = window.calc.calculate(gen, attackingMon, defendingMon, moveObj, fieldObj);
  return `${result.fullDesc()}`;
}

function renderState(data) {
  state.selected = data.selected;
  renderTeam(data.team);
  renderCatalog();
  renderRecommendations(data.recommendations);
  renderNotes(els.synergyPanel, data.synergy);
  renderNotes(els.warningsPanel, data.warnings.length ? data.warnings : ["none"]);
  els.threatReport.textContent = data.threatReport;
  renderThreatCards(data.threatEntries || []);
  renderCounters(data.counters);
  els.showdownExport.value = data.showdown;
  renderDigest(data.digest);
}

function renderThreatCards(entries) {
  if (!els.threatCards) return;
  const countEl = document.querySelector("#threatCount");
  if (!entries.length) {
    els.threatCards.innerHTML = '<div class="muted">Aggiungi Pokémon per iniziare l\'analisi matchup.</div>';
    if (countEl) countEl.textContent = "";
    return;
  }
  if (countEl) {
    const danger = entries.filter((e) => e.severity === "danger").length;
    const risky = entries.filter((e) => e.severity === "risky").length;
    const safe = entries.filter((e) => e.severity === "safe").length;
    countEl.textContent = `${entries.length} threats · ${danger} pericolose · ${risky} risky · ${safe} coperte`;
  }
  const groups = { danger: [], risky: [], safe: [] };
  entries.forEach((e) => {
    const bucket = groups[e.severity] || groups.risky;
    bucket.push(e);
  });
  const sectionTitles = { danger: "Pericolose", risky: "Da tenere d'occhio", safe: "Coperte" };
  const sectionTones = { danger: "red", risky: "gold", safe: "green" };
  const parts = [];
  ["danger", "risky", "safe"].forEach((sev) => {
    if (!groups[sev].length) return;
    parts.push(`<div class="threat-section threat-${sev}">`);
    parts.push(`<div class="threat-section-title"><span class="chip ${sectionTones[sev]}">${sectionTitles[sev]}</span></div>`);
    groups[sev].forEach((entry) => {
      const sourceChip = entry.source === "pokekipe"
        ? `<span class="chip green">Pokékipe</span>`
        : `<span class="chip gray">type-based</span>`;
      const num = numForName(entry.name);
      parts.push(`
        <div class="threat-card">
          <div class="threat-card-head">
            ${spriteImg(num, entry.name, "threat-card-sprite")}
            <strong>${escapeHtml(entry.name)}</strong>
            <span class="muted">${entry.usage.toFixed(1)}%</span>
            ${sourceChip}
          </div>
          <div class="threat-card-body">${escapeHtml(entry.summary)}</div>
        </div>
      `);
    });
    parts.push(`</div>`);
  });
  els.threatCards.innerHTML = parts.join("");
}

function renderDigest(digest) {
  if (!els.teamDigest) return;
  if (!digest || digest.team_size < 4) {
    els.teamDigest.classList.add("hidden");
    return;
  }
  els.teamDigest.classList.remove("hidden");
  const threats = (digest.top_threats || [])
    .map((t) => `<span class="chip red">${escapeHtml(t.name)} <small>(${t.hits} mon)</small></span>`)
    .join(" ");
  const counters = (digest.top_counters || [])
    .map((c) => `<span class="chip gold">${escapeHtml(c.name)} <small>(${c.hits} mon)</small></span>`)
    .join(" ");
  const sourceTag = (digest.top_counters || []).some((c) => c.source === "pokekipe")
    ? chip("Pokekipe data", "green")
    : chip("type-based fallback", "gray");
  els.teamDigest.innerHTML = `
    <div class="digest-head">Team digest <span class="muted">(${digest.team_size}/6 mon)</span> ${sourceTag}</div>
    <div class="digest-row"><strong>Top threats:</strong> ${threats || '<span class="muted">none</span>'}</div>
    <div class="digest-row"><strong>Top counters:</strong> ${counters || '<span class="muted">none</span>'}</div>
  `;
}

function renderTeam(team) {
  const slots = [];
  for (let i = 0; i < 6; i += 1) {
    const member = team[i];
    if (!member) {
      slots.push(`<div class="slot empty">Slot ${i + 1}</div>`);
      continue;
    }
    const isOverridden = !!state.overrides[member.species];
    const num = numForName(member.species);
    slots.push(`
      <div class="slot" data-species="${escapeHtml(member.species)}">
        ${spriteImg(num, member.species, "slot-sprite")}
        <div class="slot-body">
          <div class="slot-title">
            <div class="slot-title-name">
              <span>${escapeHtml(member.species)}</span>
              ${isOverridden ? chip("custom", "gold") : ""}
            </div>
            <div class="slot-title-actions">
              <button type="button" data-edit="${escapeHtml(member.species)}">Edit</button>
              <button type="button" data-remove="${escapeHtml(member.species)}">×</button>
            </div>
          </div>
          <div class="slot-meta">
            ${(member.types || []).map((t) => typeChip(t)).join("")}
            ${chip(member.item, isMegaItem(member.item) ? "gold" : "")}
            ${chip(member.ability)}
            ${chip(member.nature || "")}
          </div>
          <div class="slot-moves">${escapeHtml(member.moves.join(" · "))}</div>
          <div class="slot-evs">EVs: ${formatEvs(member.evs)}</div>
        </div>
        <div class="slot-edit hidden" data-edit-for="${escapeHtml(member.species)}">${slotEditTemplate(member)}</div>
      </div>
    `);
  }
  els.teamSlots.innerHTML = slots.join("");
  els.teamSlots.querySelectorAll("[data-remove]").forEach((button) => {
    button.addEventListener("click", async () => {
      const name = button.dataset.remove;
      state.selected = state.selected.filter((n) => n !== name);
      delete state.overrides[name];
      await refresh();
    });
  });
  els.teamSlots.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const species = button.dataset.edit;
      const panel = button.closest(".slot")?.querySelector(`[data-edit-for]`);
      if (panel) panel.classList.toggle("hidden");
    });
  });
  // Pre-populate dropdowns for every visible slot so they're ready when user opens edit
  els.teamSlots.querySelectorAll(".slot-edit[data-edit-for]").forEach((panel) => {
    populateSlotEditDropdowns(panel, panel.dataset.editFor);
  });
  els.teamSlots.querySelectorAll(".slot-edit form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const species = form.dataset.species;
      const item = form.elements.item.value.trim();
      const ability = form.elements.ability.value.trim();
      const nature = form.elements.nature.value;
      const moves = [
        form.elements.move1.value.trim(),
        form.elements.move2.value.trim(),
        form.elements.move3.value.trim(),
        form.elements.move4.value.trim(),
      ].filter(Boolean);
      const evs = {
        hp: parseInt(form.elements.evHp.value, 10) || 0,
        atk: parseInt(form.elements.evAtk.value, 10) || 0,
        def: parseInt(form.elements.evDef.value, 10) || 0,
        spa: parseInt(form.elements.evSpa.value, 10) || 0,
        spd: parseInt(form.elements.evSpd.value, 10) || 0,
        spe: parseInt(form.elements.evSpe.value, 10) || 0,
      };
      state.overrides[species] = { item, ability, nature, moves, evs };
      await refresh();
    });
  });
  els.teamSlots.querySelectorAll(".slot-edit button[data-reset]").forEach((button) => {
    button.addEventListener("click", async () => {
      delete state.overrides[button.dataset.reset];
      await refresh();
    });
  });
}

function slotEditTemplate(member) {
  const evs = member.evs || { hp: 0, atk: 0, def: 0, spa: 0, spd: 0, spe: 0 };
  return `
    <form data-species="${escapeHtml(member.species)}">
      <div class="slot-edit-grid">
        <label>Item<select name="item" data-current="${escapeHtml(member.item || "")}"><option>${escapeHtml(member.item || "")}</option></select></label>
        <label>Ability<select name="ability" data-current="${escapeHtml(member.ability || "")}"><option>${escapeHtml(member.ability || "")}</option></select></label>
        <label>Nature
          <select name="nature">
            ${["Hardy","Adamant","Modest","Jolly","Timid","Bold","Impish","Calm","Careful","Naive","Hasty","Brave","Quiet","Relaxed","Sassy","Mild","Lonely","Naughty","Rash","Gentle"].map((n) => `<option value="${n}" ${n===member.nature?"selected":""}>${n}</option>`).join("")}
          </select>
        </label>
      </div>
      <div class="slot-edit-moves">
        ${[0,1,2,3].map((i) => `<label>Move ${i+1}<select name="move${i+1}" data-current="${escapeHtml(member.moves[i] || "")}"><option>${escapeHtml(member.moves[i] || "")}</option></select></label>`).join("")}
      </div>
      <div class="slot-edit-evs-head muted">EVs (scala Champions: 0-32 per stat, ≈66 tot.)</div>
      <div class="slot-edit-evs">
        ${["hp","atk","def","spa","spd","spe"].map((s) => `<label>${s.toUpperCase()}<input name="ev${s.charAt(0).toUpperCase()+s.slice(1)}" type="number" min="0" max="32" value="${evs[s]||0}" /></label>`).join("")}
      </div>
      <div class="slot-edit-actions">
        <button type="submit" class="primary">Apply</button>
        <button type="button" data-reset="${escapeHtml(member.species)}">Reset to suggested</button>
      </div>
    </form>
  `;
}

async function populateSlotEditDropdowns(panel, species) {
  if (!panel || !species) return;
  if (panel.dataset.populating === "1") return;
  panel.dataset.populating = "1";
  try {
    const opts = await fetchJson(`/api/options?name=${encodeURIComponent(species)}`);
    if (opts.notFound) {
      console.warn("options not found for", species);
      return;
    }
    const form = panel.querySelector("form");
    if (!form) {
      console.warn("no form in panel for", species);
      return;
    }
    const itemSel = form.querySelector("select[name='item']");
    const abilitySel = form.querySelector("select[name='ability']");
    if (itemSel) fillSelect(itemSel, opts.legalItems || [], itemSel.dataset.current || "");
    if (abilitySel) fillSelect(abilitySel, opts.legalAbilities || [], abilitySel.dataset.current || "");
    for (let i = 1; i <= 4; i += 1) {
      const moveSel = form.querySelector(`select[name='move${i}']`);
      if (moveSel) fillSelect(moveSel, ["", ...(opts.legalMoves || [])], moveSel.dataset.current || "");
    }
    if (opts.megaItem && itemSel) {
      const opt = Array.from(itemSel.options).find((o) => o.value === opts.megaItem);
      if (opt) opt.textContent = `${opts.megaItem} (Mega → ${opts.megaForm || "—"})`;
    }
    panel.dataset.populated = "1";
  } catch (error) {
    console.warn("failed to load slot options for", species, error);
  } finally {
    panel.dataset.populating = "";
  }
}

function fillSelect(selectEl, values, current) {
  const seen = new Set();
  const opts = [];
  if (current && !values.includes(current)) {
    opts.push(`<option value="${escapeHtml(current)}">${escapeHtml(current)} (current)</option>`);
    seen.add(current);
  }
  values.forEach((v) => {
    if (seen.has(v)) return;
    seen.add(v);
    const sel = v === current ? "selected" : "";
    opts.push(`<option value="${escapeHtml(v)}" ${sel}>${escapeHtml(v || "(none)")}</option>`);
  });
  selectEl.innerHTML = opts.join("");
}

function cssEscape(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function renderCatalog() {
  const selected = new Set(state.selected);
  const query = state.query;
  const matches = state.catalog.pokemon
    .filter((mon) => !selected.has(mon.name))
    .filter((mon) => !query || mon.name.toLowerCase().includes(query));
  matches.sort((a, b) => {
    if (a.offMeta !== b.offMeta) return a.offMeta ? 1 : -1;
    return (b.usage || 0) - (a.usage || 0);
  });
  const limit = query ? 80 : 40;
  const pokemon = matches.slice(0, limit);
  els.catalogList.innerHTML = pokemon
    .map((mon) => {
      const usageChip = mon.offMeta
        ? chip("off-meta", "gray")
        : chip(`${mon.usage.toFixed(1)}%`, "gold");
      return `
        <div class="mon-row${mon.offMeta ? " off-meta" : ""}">
          ${spriteImg(mon.num, mon.name, "mon-row-sprite")}
          <div class="mon-row-body">
            <div class="mon-row-name">${escapeHtml(mon.name)}</div>
            <div class="mon-row-meta">
              ${(mon.types || []).map((t) => typeChip(t)).join("")}
              ${usageChip}
            </div>
          </div>
          <button type="button" data-add="${escapeHtml(mon.name)}">+</button>
        </div>
      `;
    })
    .join("");
  els.catalogList.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", async () => addPokemon(button.dataset.add));
  });
}

function renderRecommendations(recommendations) {
  els.recommendations.innerHTML = recommendations
    .map((rec) => {
      const num = numForName(rec.name);
      return `
        <article class="rec">
          ${spriteImg(num, rec.name, "rec-sprite")}
          <div class="rec-body">
            <div class="rec-title">${escapeHtml(rec.name)}</div>
            <div class="rec-meta">
              ${(rec.types || []).map((t) => typeChip(t)).join("")}
              ${chip(`score ${rec.score}`, "gold")}
              ${chip(rec.item, isMegaItem(rec.item) ? "gold" : "")}
            </div>
            <p>${escapeHtml(rec.reasons.join("; "))}</p>
          </div>
          <button class="primary" type="button" data-add="${escapeHtml(rec.name)}">Add</button>
        </article>
      `;
    })
    .join("");
  els.recommendations.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", async () => addPokemon(button.dataset.add));
  });
}

function renderNotes(target, notes) {
  target.innerHTML = notes.map((note) => `<div class="note">${escapeHtml(note)}</div>`).join("");
}

async function addPokemon(name) {
  if (state.selected.length >= 6 || state.selected.includes(name)) {
    return;
  }
  state.selected.push(name);
  await refresh();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function chip(text, tone = "") {
  if (!text) {
    return "";
  }
  return `<span class="chip ${tone}">${escapeHtml(text)}</span>`;
}

const _POKEMON_TYPES = new Set(["normal","fire","water","electric","grass","ice","fighting","poison","ground","flying","psychic","bug","rock","ghost","dragon","dark","steel","fairy"]);
function typeChip(type) {
  if (!type) return "";
  const t = String(type).toLowerCase();
  if (_POKEMON_TYPES.has(t)) {
    return `<span class="chip type-${t}">${escapeHtml(t)}</span>`;
  }
  return chip(t);
}

function spriteUrl(num) {
  if (!num) return "";
  return `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${num}.png`;
}

function spriteImg(num, alt, cls = "") {
  if (!num) return `<div class="${cls}"></div>`;
  return `<div class="${cls}"><img src="${spriteUrl(num)}" alt="${escapeHtml(alt || "")}" loading="lazy" onerror="this.style.display='none'" /></div>`;
}

function numForName(name) {
  if (!state.catalog) return null;
  const found = state.catalog.pokemon.find((mon) => mon.name === name);
  if (found) return found.num;
  // try mega forms
  const mega = (state.catalog.megaForms || []).find((m) => m.name === name);
  if (mega) return mega.num;
  // try base of mega form name
  if (name && name.includes("-Mega")) {
    const base = name.split("-Mega")[0];
    const baseEntry = state.catalog.pokemon.find((mon) => mon.name === base);
    if (baseEntry) return baseEntry.num;
  }
  return null;
}

function isMegaItem(item) {
  return item && (item.endsWith("ite") || item === "Charizardite X" || item === "Charizardite Y");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init().catch((error) => {
  document.body.innerHTML = `<pre>${escapeHtml(error.stack || error.message)}</pre>`;
});
