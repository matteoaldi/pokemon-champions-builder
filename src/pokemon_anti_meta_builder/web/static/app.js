const state = {
  catalog: null,
  selected: [],
  query: "",
  moveFilter: "",
  moveFilterUsers: null,
  movesList: [],
  allMoves: [],
  searchMode: "name",
  poolFilter: "all",
  showUnplayed: false,
  typeFilter: null,
  activeTab: "threats",
  counters: null,
  overrides: {},
  savedTeams: [],
  currentTeamId: null,
  currentTeamName: "",
  lastTeam: [],
};

const els = {
  autoBuildButton: document.querySelector("#autoBuildButton"),
  coachButton: document.querySelector("#coachButton"),
  clearButton: document.querySelector("#clearButton"),
  teamSlots: document.querySelector("#teamSlots"),
  teamDigest: document.querySelector("#teamDigest"),
  currentTeamLabel: document.querySelector("#currentTeamLabel"),
  catalogList: document.querySelector("#catalogList"),
  showUnplayedToggle: document.querySelector("#showUnplayedToggle"),
  searchInput: document.querySelector("#searchInput"),
  moveFilterOptions: document.querySelector("#moveFilterOptions"),
  moveFilterHint: document.querySelector("#moveFilterHint"),
  searchModeName: document.querySelector("#searchModeName"),
  searchModeMove: document.querySelector("#searchModeMove"),
  savedTeamsButton: document.querySelector("#savedTeamsButton"),
  savedTeamsMenu: document.querySelector("#savedTeamsMenu"),
  savedTeamsDropdown: document.querySelector("#savedTeamsDropdown"),
  savedTeamsCount: document.querySelector("#savedTeamsCount"),
  catalogFilterToggle: document.querySelector("#catalogFilterToggle"),
  catalogFilterPanel: document.querySelector("#catalogFilterPanel"),
  catalogTypeChips: document.querySelector("#catalogTypeChips"),
  recommendations: document.querySelector("#recommendations"),
  synergyPanel: document.querySelector("#synergyPanel"),
  threatReport: document.querySelector("#threatReport"),
  threatCards: document.querySelector("#threatCards"),
  warningsPanel: document.querySelector("#warningsPanel"),
  coachPanel: document.querySelector("#coachPanel"),
  countersPanel: document.querySelector("#countersPanel"),
  refreshCountersButton: document.querySelector("#refreshCountersButton"),
  calcPanel: document.querySelector("#calcPanel"),
  lookupInput: document.querySelector("#lookupInput"),
  lookupOptions: document.querySelector("#lookupOptions"),
  lookupResult: document.querySelector("#lookupResult"),
  saveTeamName: document.querySelector("#saveTeamName"),
  saveTeamButton: document.querySelector("#saveTeamButton"),
  savedTeamsList: document.querySelector("#savedTeamsList"),
  tabs: document.querySelectorAll(".tab"),
  panels: document.querySelectorAll(".tab-panel"),
  evtunerPanel: document.querySelector("#evtunerPanel"),
  evtabs: document.querySelectorAll(".evtab"),
};

async function init() {
  state.catalog = await fetchJson("/api/catalog");
  try {
    const [calc, all] = await Promise.all([
      fetchJson("/api/calc/moves"),
      fetchJson("/api/moves_index"),
    ]);
    state.movesList = calc.moves || [];
    state.allMoves = all.moves || [];
    populateMoveDatalist();
  } catch (e) {
    state.movesList = [];
    state.allMoves = [];
  }
  bindEvents();
  await Promise.all([refresh(), loadSavedTeams()]);
}

function populateMoveDatalist() {
  if (!els.moveFilterOptions) return;
  const list = state.allMoves.length ? state.allMoves : state.movesList;
  els.moveFilterOptions.innerHTML = list
    .map((m) => `<option value="${escapeHtml(m)}">`)
    .join("");
}

function setSearchMode(mode) {
  state.searchMode = mode === "move" ? "move" : "name";
  const nameBtn = els.searchModeName;
  const moveBtn = els.searchModeMove;
  if (nameBtn) nameBtn.classList.toggle("active", state.searchMode === "name");
  if (moveBtn) moveBtn.classList.toggle("active", state.searchMode === "move");
  if (state.searchMode === "move") {
    els.searchInput.setAttribute("list", "moveFilterOptions");
    els.searchInput.placeholder = "Cerca per mossa (es. Tailwind)...";
    // Reset the name-search query so it doesn't keep filtering by name
    // while we filter by move.
    state.query = "";
    // Clear the input so the user starts fresh; otherwise leftover "tail"
    // from name-mode would look like an active move filter on resize.
    els.searchInput.value = "";
    state.moveFilter = "";
    state.moveFilterUsers = null;
    if (els.moveFilterHint) els.moveFilterHint.textContent = "";
    renderCatalog();
  } else {
    els.searchInput.removeAttribute("list");
    els.searchInput.placeholder = "Cerca Pokémon...";
    if (els.moveFilterHint) els.moveFilterHint.textContent = "";
    state.moveFilter = "";
    state.moveFilterUsers = null;
    els.searchInput.value = "";
    state.query = "";
    renderCatalog();
  }
}

const ALL_TYPES = [
  "normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison",
  "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy",
];

function populateTypeChips() {
  if (!els.catalogTypeChips) return;
  els.catalogTypeChips.innerHTML = ALL_TYPES
    .map((t) => `<button class="filter-chip type-${t}" data-type="${t}" type="button">${t}</button>`)
    .join("");
  els.catalogTypeChips.querySelectorAll("[data-type]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const t = btn.dataset.type;
      state.typeFilter = state.typeFilter === t ? null : t;
      els.catalogTypeChips.querySelectorAll("[data-type]").forEach((b) => {
        b.classList.toggle("active", b.dataset.type === state.typeFilter);
      });
      renderCatalog();
    });
  });
}

async function applyMoveFilter() {
  const raw = (els.searchInput?.value || "").trim();
  if (!raw) {
    state.moveFilter = "";
    state.moveFilterUsers = null;
    if (els.moveFilterHint) els.moveFilterHint.textContent = "";
    renderCatalog();
    return;
  }
  // Only fetch when the typed value matches a known move (avoid spamming
  // the endpoint while typing). Comparison is case-insensitive.
  const pool = state.allMoves.length ? state.allMoves : state.movesList;
  const lower = raw.toLowerCase();
  // Try exact match first (the user picked from the datalist), then
  // startsWith ("tail" → Tailwind), finally substring includes.
  let match = pool.find((m) => m.toLowerCase() === lower);
  if (!match) match = pool.find((m) => m.toLowerCase().startsWith(lower));
  if (!match) match = pool.find((m) => m.toLowerCase().includes(lower));
  if (!match) {
    state.moveFilter = "";
    state.moveFilterUsers = null;
    if (els.moveFilterHint) els.moveFilterHint.textContent = `Mossa "${raw}" non trovata nel learnset gen 9.`;
    renderCatalog();
    return;
  }
  if (els.moveFilterHint) els.moveFilterHint.textContent = `Cerco chi impara ${match}…`;
  try {
    const data = await fetchJson(`/api/move_users?move=${encodeURIComponent(match)}`);
    state.moveFilter = match;
    state.moveFilterUsers = new Set((data.species || []).map((s) => s.toLowerCase()));
    if (els.moveFilterHint) {
      els.moveFilterHint.textContent = `${data.species.length} Pokémon imparano ${match}.`;
    }
  } catch (e) {
    state.moveFilter = "";
    state.moveFilterUsers = null;
    if (els.moveFilterHint) els.moveFilterHint.textContent = `Errore: ${e.message || e}`;
  }
  renderCatalog();
}

function bindEvents() {
  // Unified search input: behaviour depends on state.searchMode ("name" | "move")
  let searchDebounce;
  els.searchInput.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    if (state.searchMode === "name") {
      state.query = (els.searchInput.value || "").toLowerCase();
      renderCatalog();
    } else {
      searchDebounce = setTimeout(applyMoveFilter, 200);
    }
  });
  [els.searchModeName, els.searchModeMove].forEach((btn) => {
    if (!btn) return;
    btn.addEventListener("click", () => setSearchMode(btn.dataset.mode));
  });
  if (els.catalogFilterToggle) {
    els.catalogFilterToggle.addEventListener("click", () => {
      els.catalogFilterPanel?.classList.toggle("hidden");
    });
  }
  document.querySelectorAll("[data-pool]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.poolFilter = btn.dataset.pool;
      document.querySelectorAll("[data-pool]").forEach((b) => b.classList.toggle("active", b === btn));
      renderCatalog();
    });
  });
  if (els.showUnplayedToggle) {
    els.showUnplayedToggle.addEventListener("change", () => {
      state.showUnplayed = els.showUnplayedToggle.checked;
      renderCatalog();
    });
  }
  populateTypeChips();
  if (els.savedTeamsButton && els.savedTeamsMenu) {
    els.savedTeamsButton.addEventListener("click", (event) => {
      event.stopPropagation();
      els.savedTeamsMenu.classList.toggle("hidden");
    });
    document.addEventListener("click", (event) => {
      if (!els.savedTeamsDropdown) return;
      if (!els.savedTeamsDropdown.contains(event.target)) {
        els.savedTeamsMenu.classList.add("hidden");
      }
    });
  }
  els.clearButton.addEventListener("click", async () => {
    state.selected = [];
    state.currentTeamId = null;
    state.currentTeamName = "";
    state.overrides = {};
    els.coachPanel.textContent = "";
    renderCurrentTeamLabel();
    await refresh();
  });
  els.autoBuildButton.addEventListener("click", autoBuild);
  els.coachButton.addEventListener("click", askCoach);
  if (els.saveTeamButton) {
    els.saveTeamButton.addEventListener("click", saveCurrentTeam);
  }
  if (els.saveTeamName) {
    els.saveTeamName.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        saveCurrentTeam();
      }
    });
  }
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
  initEvTuner();
  populateLookupDatalist();
}

async function loadSavedTeams() {
  try {
    const data = await fetchJson("/api/teams");
    state.savedTeams = data.teams || [];
  } catch (error) {
    state.savedTeams = [];
  }
  renderSavedTeams();
}

function renderSavedTeams() {
  if (!els.savedTeamsList) return;
  if (els.savedTeamsCount) {
    els.savedTeamsCount.textContent = state.savedTeams.length ? `${state.savedTeams.length} salvati` : "vuoto";
  }
  if (!state.savedTeams.length) {
    els.savedTeamsList.innerHTML = '<div class="muted saved-teams-empty">Nessun team salvato.</div>';
    return;
  }
  els.savedTeamsList.innerHTML = state.savedTeams
    .map((team) => {
      const active = team.id === state.currentTeamId ? " active" : "";
      return `
        <div class="saved-team-row${active}" data-team-id="${escapeHtml(team.id)}">
          <button type="button" class="saved-team-load" data-load="${escapeHtml(team.id)}">
            <span class="saved-team-name">${escapeHtml(team.name)}</span>
            <span class="saved-team-meta muted">${team.size}/6</span>
          </button>
          <button type="button" class="saved-team-delete" data-delete="${escapeHtml(team.id)}" title="Elimina">×</button>
        </div>
      `;
    })
    .join("");
  els.savedTeamsList.querySelectorAll("[data-load]").forEach((btn) => {
    btn.addEventListener("click", () => loadTeam(btn.dataset.load));
  });
  els.savedTeamsList.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteTeam(btn.dataset.delete);
    });
  });
}

function renderCurrentTeamLabel() {
  if (!els.currentTeamLabel) return;
  if (!state.currentTeamId) {
    els.currentTeamLabel.classList.add("hidden");
    els.currentTeamLabel.textContent = "";
    return;
  }
  els.currentTeamLabel.classList.remove("hidden");
  els.currentTeamLabel.innerHTML = `Team caricato: <strong>${escapeHtml(state.currentTeamName || state.currentTeamId)}</strong>`;
}

async function saveCurrentTeam() {
  const inputName = (els.saveTeamName?.value || "").trim();
  const name = inputName || state.currentTeamName || `Team ${new Date().toLocaleString("it-IT")}`;
  if (!state.selected.length) {
    alert("Aggiungi almeno un Pokémon al team prima di salvare.");
    return;
  }
  const payload = {
    name,
    selected: state.selected,
    overrides: state.overrides,
  };
  // If we're editing a loaded team and the user didn't change the name,
  // overwrite that team's file instead of creating a new one.
  if (state.currentTeamId && (!inputName || inputName === state.currentTeamName)) {
    payload.id = state.currentTeamId;
    payload.name = state.currentTeamName || name;
  }
  let saved;
  try {
    saved = await fetchJson("/api/teams", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    alert(`Errore salvataggio team: ${error.message}`);
    return;
  }
  state.currentTeamId = saved.id;
  state.currentTeamName = saved.name;
  if (els.saveTeamName) els.saveTeamName.value = "";
  renderCurrentTeamLabel();
  await loadSavedTeams();
}

async function loadTeam(teamId) {
  let team;
  try {
    team = await fetchJson(`/api/teams/${encodeURIComponent(teamId)}`);
  } catch (error) {
    alert(`Errore caricamento team: ${error.message}`);
    return;
  }
  state.currentTeamId = team.id;
  state.currentTeamName = team.name;
  state.selected = Array.isArray(team.selected) ? [...team.selected] : [];
  state.overrides = team.overrides && typeof team.overrides === "object" ? { ...team.overrides } : {};
  if (els.saveTeamName) els.saveTeamName.value = "";
  renderCurrentTeamLabel();
  renderSavedTeams();
  await refresh();
}

async function deleteTeam(teamId) {
  const target = state.savedTeams.find((t) => t.id === teamId);
  const label = target ? target.name : teamId;
  if (!confirm(`Eliminare il team "${label}"?`)) return;
  try {
    await fetchJson(`/api/teams/${encodeURIComponent(teamId)}`, { method: "DELETE" });
  } catch (error) {
    alert(`Errore eliminazione team: ${error.message}`);
    return;
  }
  if (state.currentTeamId === teamId) {
    state.currentTeamId = null;
    state.currentTeamName = "";
    renderCurrentTeamLabel();
  }
  await loadSavedTeams();
}

function populateLookupDatalist() {
  if (!els.lookupOptions || !state.catalog) return;
  const baseOpts = visibleMons().map((mon) => `<option value="${escapeHtml(mon.name)}"></option>`);
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
  const sourceChip = data.source === "pokekipe" ? chip("Pokékipe", "green") : "";
  const typesChips = (data.types || []).map((t) => typeChip(t)).join(" ");
  const metaCounters = (data.counters || []).filter((c) => !c.offMeta);
  const offMetaCounters = (data.counters || []).filter((c) => c.offMeta);
  const renderRow = (c) => {
    const num = numForName(c.name);
    const why = (c.reasons || []).length
      ? `<div class="counter-why">${(c.reasons || []).map((r) => `<span class="why-chip">${escapeHtml(r)}</span>`).join("")}</div>`
      : "";
    return `
      <div class="counter-row${c.offMeta ? " off-meta" : ""}">
        ${spriteImg(num, c.name, "counter-row-sprite")}
        <div class="counter-row-main">
          <span>${escapeHtml(c.name)} ${(c.types || []).map((t) => typeChip(t)).join(" ")}${c.offMeta ? " " + chip("off-meta", "gray") : ""}</span>
          ${why}
        </div>
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
  const anyPokekipe = data.members.some((m) => m.source === "pokekipe");
  const allSameSource = !anyPokekipe || data.members.every((m) => m.source === "pokekipe");
  els.countersPanel.innerHTML = data.members
    .map((member) => {
      const tag = member.source === "pokekipe" && !allSameSource
        ? chip("Pokékipe data", "green")
        : "";
      const megaFallback = member.megaFallback
        ? `<span class="muted mega-fallback-note">Counter Pokékipe non disponibili per la mega → stima da tipi</span>`
        : "";
      const megaChip = member.isMega ? chip("Mega", "gold") : "";
      const rows = member.counters.length
        ? member.counters
            .map((entry) => {
              const num = numForName(entry.name);
              const entryMega = entry.isMega ? chip("Mega", "gold") : "";
              return `
                <div class="counter-row">
                  ${spriteImg(num, entry.form || entry.name, "counter-row-sprite")}
                  <span>${escapeHtml(entry.form || entry.name)}</span>
                  ${entryMega}
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
          ${megaFallback}
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
      <label class="from-team-row" data-from-team-wrap hidden>Dal team
        <select data-from-team>
          <option value="">(scegli slot)</option>
        </select>
      </label>
      <label>Pokemon
        <input data-field="name" type="search" list="calcMonsList" placeholder="Scrivi un nome..." autocomplete="off" />
      </label>
      <div class="calc-quick-row">
        <label class="calc-quick-label">Counter (chi lo batte) → carica nell'altro slot
          <select data-quick="counters"><option value="">—</option></select>
        </label>
        <label class="calc-quick-label">Counterati (chi batte) → carica nell'altro slot
          <select data-quick="victims"><option value="">—</option></select>
        </label>
      </div>
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
    Promise.resolve(visibleMons().map((mon) => mon.name)),
  ]);
  calcState.moves = moves.moves;
  renderCalcMoveDropdown();
  // Shared datalist for both attacker and defender name fields
  let monsDatalist = document.querySelector("#calcMonsList");
  if (!monsDatalist) {
    monsDatalist = document.createElement("datalist");
    monsDatalist.id = "calcMonsList";
    els.calcPanel.prepend(monsDatalist);
  }
  monsDatalist.innerHTML = names.map((name) => `<option value="${escapeHtml(name)}">`).join("");
  const namesLower = new Set(names.map((n) => n.toLowerCase()));
  ["attacker", "defender"].forEach((role) => {
    const card = document.querySelector(`.calc-card[data-role='${role}']`);
    const nameInput = card.querySelector("[data-field='name']");
    const loadByName = async (raw) => {
      const value = (raw || "").trim();
      if (!value) return;
      // Case-insensitive resolve against the catalog so users can write
      // "garchomp" or "GARCHOMP" and still hit the right entry.
      if (!namesLower.has(value.toLowerCase())) return;
      const data = await fetchJson(`/api/combatant?name=${encodeURIComponent(value)}`);
      if (data.error) return;
      // Normalize the input to the canonical name
      nameInput.value = data.name || value;
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
        await loadAttackerLearnset(nameInput.value);
      }
      updateLivePreview();
      // Populate the "counter / counterati" quick selects for this card.
      refreshCalcQuickSelects(role, nameInput.value);
    };
    nameInput.addEventListener("change", () => loadByName(nameInput.value));
    nameInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        loadByName(nameInput.value);
      }
    });
    card.querySelector("[data-field='nature']").innerHTML = Object.keys(NATURES).map((n) => `<option value="${n}">${n}</option>`).join("");

    // Quick-select dropdowns: pick a counter or a target → load it in the OTHER role
    const otherRole = role === "attacker" ? "defender" : "attacker";
    const quickCounters = card.querySelector("[data-quick='counters']");
    const quickVictims = card.querySelector("[data-quick='victims']");
    [quickCounters, quickVictims].forEach((sel) => {
      if (!sel) return;
      sel.addEventListener("change", () => {
        if (!sel.value) return;
        const otherCard = document.querySelector(`.calc-card[data-role='${otherRole}']`);
        const otherInput = otherCard?.querySelector("[data-field='name']");
        if (otherInput) {
          otherInput.value = sel.value;
          otherInput.dispatchEvent(new Event("change"));
        }
        sel.value = "";
      });
    });
  });
  document.querySelector("#calcShowAllMoves").addEventListener("change", (event) => {
    calcState.showAllMoves = event.target.checked;
    renderCalcMoveDropdown();
  });
  ["attacker", "defender"].forEach((role) => {
    const card = document.querySelector(`.calc-card[data-role='${role}']`);
    const teamSelect = card.querySelector("[data-from-team]");
    if (teamSelect) {
      teamSelect.addEventListener("change", () => {
        if (teamSelect.value === "") return;
        pickFromTeam(role, parseInt(teamSelect.value, 10));
        teamSelect.value = "";
      });
    }
  });
  refreshCalcTeamPickers();
  syncCalcField();
  updateLivePreview();
}

async function refreshCalcQuickSelects(role, monName) {
  const card = document.querySelector(`.calc-card[data-role='${role}']`);
  if (!card || !monName) return;
  const countersSel = card.querySelector("[data-quick='counters']");
  const victimsSel = card.querySelector("[data-quick='victims']");
  if (!countersSel || !victimsSel) return;
  countersSel.innerHTML = '<option value="">— caricamento —</option>';
  victimsSel.innerHTML = '<option value="">— caricamento —</option>';
  let counters = [], victims = [];
  try {
    const data = await fetchJson(`/api/counter_lookup?name=${encodeURIComponent(monName)}`);
    counters = data.counters || [];
  } catch (e) { /* swallow */ }
  try {
    const data = await fetchJson(`/api/countered_by?name=${encodeURIComponent(monName)}`);
    victims = data.victims || [];
  } catch (e) { /* swallow */ }
  const fmt = (lst, label) => {
    if (!lst.length) return `<option value="">— ${label} —</option>`;
    return [`<option value="">— ${label} —</option>`].concat(
      lst.map((c) => {
        const usage = c.meta_usage ? ` (${c.meta_usage.toFixed(1)}%)` : "";
        const off = c.offMeta ? " · off-meta" : "";
        return `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}${usage}${off}</option>`;
      })
    ).join("");
  };
  countersSel.innerHTML = fmt(counters, `${counters.length} counter`);
  victimsSel.innerHTML = fmt(victims, `${victims.length} battuti`);
}

function refreshCalcTeamPickers() {
  ["attacker", "defender"].forEach((role) => {
    const card = document.querySelector(`.calc-card[data-role='${role}']`);
    if (!card) return;
    const wrap = card.querySelector("[data-from-team-wrap]");
    const select = card.querySelector("[data-from-team]");
    if (!wrap || !select) return;
    if (!state.lastTeam.length) {
      wrap.setAttribute("hidden", "");
      select.innerHTML = '<option value="">(scegli slot)</option>';
      return;
    }
    wrap.removeAttribute("hidden");
    const options = ['<option value="">(scegli slot)</option>'].concat(
      state.lastTeam.map((member, idx) => {
        const label = `${idx + 1}. ${member.species}`;
        return `<option value="${idx}">${escapeHtml(label)}</option>`;
      })
    );
    select.innerHTML = options.join("");
  });
}

async function pickFromTeam(role, index) {
  const member = state.lastTeam[index];
  if (!member) return;
  const card = document.querySelector(`.calc-card[data-role='${role}']`);
  if (!card) return;
  // Pull a damage-calc-ready payload (handles mega form swap, types, base stats).
  let data;
  try {
    data = await fetchJson(`/api/combatant?name=${encodeURIComponent(member.species)}`);
  } catch (error) {
    console.warn("failed to load combatant for", member.species, error);
    return;
  }
  if (data.error) return;
  calcState[role] = data;
  const nameField = card.querySelector("[data-field='name']");
  if (nameField) {
    nameField.value = data.name || member.species;
  }
  // Overlay actual team member values on top of the auto-built defaults so
  // user-edited EVs/nature/item make it into the calc.
  const memberEvs = member.evs || {};
  ["hp", "atk", "def", "spa", "spd", "spe"].forEach((s) => {
    const el = card.querySelector(`[data-ev='${s}']`);
    if (el) el.value = memberEvs[s] ?? data.evs?.[s] ?? 0;
  });
  const natureField = card.querySelector("[data-field='nature']");
  if (natureField) {
    const natures = Object.keys(NATURES);
    natureField.innerHTML = natures.map((n) => `<option value="${n}">${n}</option>`).join("");
    natureField.value = member.nature || data.nature || "Hardy";
  }
  const teraField = card.querySelector("[data-field='teraType']");
  if (teraField) teraField.value = "";
  card.querySelectorAll("[data-boost-value]").forEach((el) => {
    el.textContent = "0";
    el.classList.remove("boost-positive", "boost-negative");
  });
  // Reset status flags
  const burnEl = card.querySelector("[data-field='isBurned']");
  const paraEl = card.querySelector("[data-field='isParalyzed']");
  if (burnEl) burnEl.checked = false;
  if (paraEl) paraEl.checked = false;
  if (role === "attacker") {
    await loadAttackerLearnset(member.species);
  }
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
  // @smogon/calc's fullDesc() throws on 0-damage matchups (immunities, status moves).
  // Guard it so the real calc keeps working instead of falling back to the lite engine.
  const raw = result.damage;
  const flat = Array.isArray(raw) ? raw.flat(Infinity) : [raw];
  const maxDmg = flat.length ? Math.max(...flat) : 0;
  if (!maxDmg) {
    return `${attacker.name} ${move} vs. ${defender.name}: 0 danni — immunità o nessun effetto.`;
  }
  return `${result.fullDesc()}`;
}

function renderState(data) {
  state.selected = data.selected;
  state.lastTeam = Array.isArray(data.team) ? data.team : [];
  renderTeam(data.team);
  renderCatalog();
  renderRecommendations(data.recommendations);
  renderNotes(els.synergyPanel, data.synergy);
  renderNotes(els.warningsPanel, data.warnings.length ? data.warnings : ["none"]);
  els.threatReport.textContent = data.threatReport;
  renderThreatCards(data.threatEntries || []);
  renderCounters(data.counters);
  renderDigest(data.digest);
  refreshCalcTeamPickers();
  refreshTunerTeamPickers();
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
      // Source chip only shown when there's a mix (some pokekipe, some fallback).
      // When all entries use the same source it's just noise; hide it.
      const sourceChip = entry.source === "pokekipe" && _shouldShowSourceChip(entries)
        ? `<span class="chip green">Pokékipe</span>`
        : "";
      const num = numForName(entry.name);
      const label = entry.form || entry.name;
      const megaChip = entry.isMega ? `<span class="chip gold">Mega</span>` : "";
      const pressN = (entry.pressures || []).length;
      const pressChip = pressN
        ? `<span class="chip ${pressN >= 3 ? "red" : "gray"}">preme ${pressN}</span>`
        : "";
      parts.push(`
        <div class="threat-card">
          <div class="threat-card-head">
            ${spriteImg(num, label, "threat-card-sprite")}
            <strong>${escapeHtml(label)}</strong>
            ${megaChip}
            <span class="muted">${entry.usage.toFixed(1)}%</span>
            ${pressChip}
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
    ? chip("Pokékipe", "green")
    : "";
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
              <button type="button" class="slot-tune" data-tune="${escapeHtml(member.species)}" title="Apri EV Tuner con questo Pokémon">Tuna</button>
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
  els.teamSlots.querySelectorAll("[data-tune]").forEach((button) => {
    button.addEventListener("click", () => openTuner(button.dataset.tune));
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
      // Clamp EV inputs to Champions range (0-32) so out-of-range typed
      // values don't silently block the submit via HTML5 validation.
      const clamp = (raw) => {
        const n = parseInt(raw, 10);
        if (Number.isNaN(n)) return 0;
        return Math.max(0, Math.min(32, n));
      };
      const evs = {
        hp: clamp(form.elements.evHp.value),
        atk: clamp(form.elements.evAtk.value),
        def: clamp(form.elements.evDef.value),
        spa: clamp(form.elements.evSpa.value),
        spd: clamp(form.elements.evSpd.value),
        spe: clamp(form.elements.evSpe.value),
      };
      const total = Object.values(evs).reduce((a, b) => a + b, 0);
      const status = form.querySelector(".slot-edit-status") || (() => {
        const div = document.createElement("div");
        div.className = "slot-edit-status muted";
        div.style.fontSize = "11px";
        form.querySelector(".slot-edit-actions").appendChild(div);
        return div;
      })();
      if (total > 66) {
        status.textContent = `⚠ Totale EV ${total} > 66 (cap Champions). Riduci prima di applicare.`;
        status.style.color = "var(--red)";
        showToast(`Totale EV ${total} > 66: riduci prima di salvare.`, "error");
        return;
      }
      status.style.color = "";
      status.textContent = "Salvataggio…";
      state.overrides[species] = { item, ability, nature, moves, evs };
      console.log("[edit slot]", species, "override →", state.overrides[species]);
      try {
        await refresh();
        showToast(`${species}: override applicato (${formatEvs(evs)} ${nature}).`, "success");
      } catch (err) {
        status.textContent = `Errore: ${err.message || err}`;
        showToast(`Errore salvando ${species}: ${err.message || err}`, "error");
      }
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

// Pokémon that are legal in Reg M-A but have no real usage/set data (hasData=false)
// are hidden everywhere by default; the "mostra non-giocati" toggle reveals them.
function visibleMons() {
  if (!state.catalog) return [];
  if (state.showUnplayed) return state.catalog.pokemon;
  return state.catalog.pokemon.filter((mon) => mon.hasData !== false);
}

function renderCatalog() {
  const selected = new Set(state.selected);
  const query = state.query;
  const moveUsers = state.moveFilterUsers;
  const pool = state.poolFilter;
  const type = state.typeFilter;
  const matches = visibleMons()
    .filter((mon) => !selected.has(mon.name))
    .filter((mon) => !query || mon.name.toLowerCase().includes(query))
    .filter((mon) => !moveUsers || moveUsers.has(mon.name.toLowerCase()))
    .filter((mon) => pool === "all" || (pool === "meta" ? !mon.offMeta : !!mon.offMeta))
    .filter((mon) => !type || (mon.types || []).some((t) => t.toLowerCase() === type));
  matches.sort((a, b) => {
    if (a.offMeta !== b.offMeta) return a.offMeta ? 1 : -1;
    return (b.usage || 0) - (a.usage || 0);
  });
  const pokemon = matches;
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
      const b = rec.breakdown || {};
      const breakdownChips = b && Object.keys(b).length
        ? `<div class="rec-breakdown muted">Sinergia ${b.synergy} · Counter ${b.counter} · Compagni ${b.teammate} · Meta ${b.meta}</div>`
        : "";
      return `
        <article class="rec">
          ${spriteImg(num, rec.name, "rec-sprite")}
          <div class="rec-body">
            <div class="rec-title">${escapeHtml(rec.name)}${rec.offMeta ? " " + chip("off-meta", "gray") : ""}</div>
            <div class="rec-meta">
              ${(rec.types || []).map((t) => typeChip(t)).join("")}
              ${chip(`score ${rec.score}`, "gold")}
              ${chip(rec.item, isMegaItem(rec.item) ? "gold" : "")}
            </div>
            ${breakdownChips}
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

function _shouldShowSourceChip(items) {
  // Mixed sources → useful to mark which ones are real Pokékipe data.
  // All same → noise, hide it.
  if (!items || !items.length) return false;
  const sources = new Set(items.map((i) => i.source));
  return sources.size > 1;
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

// =================== EV TUNER ===================

const evtuner = {
  mode: "survive",
  ourSpecies: "",
  ourNatureLock: "",
  targetSpecies: "",
  relevantLearnset: null,
  learnsetCache: {},
  spreadIndex: 0,
  manualSpread: { nature: "Adamant", evs: { hp: 0, atk: 0, def: 0, spa: 0, spd: 0, spe: 0 } },
  useManual: false,
  lastSpeEv: 0,
  move: "",
  condition: "none",
  threshold: "guaranteed",
  goal: "ohko",
  field: { weather: "", terrain: "", lightScreen: false, reflect: false, auroraVeil: false, spread: true, crit: false },
  lastResult: null,
  movesList: [],
  spreadsCache: {},
};

const EVT_NATURES = ["Hardy","Adamant","Modest","Jolly","Timid","Bold","Impish","Calm","Careful","Naive","Hasty","Brave","Quiet","Relaxed","Sassy","Mild","Lonely","Naughty","Rash","Gentle","Serious","Docile","Bashful","Quirky"];

const EVT_STATS = ["hp","atk","def","spa","spd","spe"];

async function initEvTuner() {
  if (!els.evtunerPanel) return;
  // Bind sub-tabs
  els.evtabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      evtuner.mode = tab.dataset.evtab;
      els.evtabs.forEach((t) => t.classList.toggle("active", t === tab));
      renderEvTuner();
    });
  });
  // Preload move list once (shared with Damage Calc)
  try {
    const moves = await fetchJson("/api/calc/moves");
    evtuner.movesList = moves.moves || [];
  } catch (e) {
    evtuner.movesList = [];
  }
  renderEvTuner();
}

function renderEvTuner() {
  if (!els.evtunerPanel) return;
  els.evtunerPanel.innerHTML = evtunerFormHtml(evtuner.mode) + `
    <div id="evtResultCard" class="calc-result-card hidden"></div>
  `;
  attachEvTunerHandlers();
  refreshTunerTeamPickers();
}

function refreshTunerTeamPickers() {
  // Re-populate every team-derived dropdown in the tuner / spread maker so
  // they reflect state.selected. Called both at render time and whenever the
  // team changes via refresh().
  const teamOpts = (placeholder) => {
    const opts = [`<option value="">${placeholder}</option>`];
    state.selected.forEach((s, i) => {
      opts.push(`<option value="${escapeHtml(s)}">${i + 1}. ${escapeHtml(s)}</option>`);
    });
    if (!state.selected.length) {
      opts.push('<option value="" disabled>(nessun mon nel team)</option>');
    }
    return opts.join("");
  };
  const fromTeam = document.querySelector("#evtOurFromTeam");
  if (fromTeam) fromTeam.innerHTML = teamOpts("— seleziona slot del team —");
  const smFromTeam = document.querySelector("#smOurFromTeam");
  if (smFromTeam) smFromTeam.innerHTML = teamOpts("— slot del team —");
  const applyTarget = document.querySelector("#evtApplyTarget");
  if (applyTarget) {
    const opts = ['<option value="">—</option>'];
    state.selected.forEach((s, i) => {
      opts.push(`<option value="${escapeHtml(s)}">${i + 1}. ${escapeHtml(s)}</option>`);
    });
    applyTarget.innerHTML = opts.join("");
  }
  const smApply = document.querySelector("#smApplyTarget");
  if (smApply) {
    const opts = ['<option value="">—</option>'];
    state.selected.forEach((s, i) => {
      opts.push(`<option value="${escapeHtml(s)}">${i + 1}. ${escapeHtml(s)}</option>`);
    });
    smApply.innerHTML = opts.join("");
  }
}

function evtunerFormHtml(mode) {
  if (mode === "spreadmaker") return spreadMakerFormHtml();
  const baseMons = visibleMons().map((m) => m.name);
  const megaMons = (state.catalog?.megaForms || []).map((m) => m.name);
  const monsList = [...baseMons, ...megaMons]
    .map((n) => `<option value="${escapeHtml(n)}">`)
    .join("");
  const movesList = evtuner.movesList.map((m) => `<option value="${escapeHtml(m)}">`).join("");
  // Always render the dropdown shell so it can be updated as the team
  // changes via refreshTunerTeamPickers(). The options are filled there too.
  const teamSelOptions = "";

  const targetSpreadBlock = `
    <label>Spread del bersaglio
      <select id="evtTargetSpread"></select>
    </label>
    <div id="evtManualSpread" class="evt-manual-spread hidden">
      <label>Nature
        <select id="evtManualNature">${EVT_NATURES.map(n => `<option value="${n}">${n}</option>`).join("")}</select>
      </label>
      <div class="calc-evs-grid">
        ${EVT_STATS.map(s => `<label>${s.toUpperCase()}<input type="number" min="0" max="32" data-manual-ev="${s}" value="${evtuner.manualSpread.evs[s]||0}" /></label>`).join("")}
      </div>
      <div class="evt-manual-total muted">Totale: <span id="evtManualTotal">0</span> / 66</div>
    </div>
  `;

  let modeFields = "";
  if (mode === "survive") {
    modeFields = `
      <label>Mossa nemica
        <input id="evtMove" list="evtMovesList" placeholder="Es. Earthquake" value="${escapeHtml(evtuner.move)}" />
      </label>
      <label>Soglia
        <select id="evtThreshold">
          <option value="guaranteed">Garantita (16/16 roll)</option>
          <option value="high">Alta (15/16 roll)</option>
          <option value="median">Mediana (8/16 roll)</option>
        </select>
      </label>
    `;
  } else if (mode === "outspeed") {
    modeFields = `
      <label>Condizione
        <select id="evtCondition">
          <option value="none">Nessuna</option>
          <option value="tailwind_me">Tailwind solo io</option>
          <option value="tailwind_opp">Tailwind solo lui</option>
          <option value="tailwind_both">Tailwind entrambi</option>
          <option value="scarf_me">Choice Scarf io</option>
          <option value="scarf_opp">Choice Scarf lui</option>
          <option value="paralysis_opp">Paralisi sul bersaglio</option>
        </select>
      </label>
    `;
  } else if (mode === "ohko") {
    modeFields = `
      <label>Mossa mia
        <input id="evtMove" list="evtMovesList" placeholder="Es. Close Combat" value="${escapeHtml(evtuner.move)}" />
      </label>
      <label>Obiettivo
        <select id="evtGoal">
          <option value="ohko">OHKO (1 colpo)</option>
          <option value="2hko">2HKO (2 colpi)</option>
        </select>
      </label>
    `;
  } else { // dualspeed (reached only via the Spread Maker speed section, not a sub-tab)
    modeFields = `
      <div class="muted">Calcoliamo Spe che cada nel range (target/2, target): sotto Tailwind più veloce del bersaglio, sotto Trick Room più lento. In entrambi gli scenari attacchi prima.</div>
      <div class="evt-universal-buttons">
        <button data-universal-pool="meta_top" data-universal-limit="40" type="button">Spread vs top 40 usage</button>
        <button data-universal-pool="all" type="button">…vs tutti i mon con dati</button>
        <button data-universal-pool="counters" type="button">…vs i counter del mio mon</button>
        <button data-universal-pool="victims" type="button">…vs i counterati del mio mon</button>
      </div>
    `;
  }

  const fieldFlags = (mode === "survive" || mode === "ohko") ? `
    <div class="calc-card">
      <div class="evt-assumptions">Field</div>
      <div class="calc-grid">
        <label>Weather
          <select id="evtWeather">
            <option value="">none</option><option value="sun">sun</option><option value="rain">rain</option>
            <option value="sand">sand</option><option value="snow">snow</option>
          </select>
        </label>
        <label>Terrain
          <select id="evtTerrain">
            <option value="">none</option><option value="electric">electric</option><option value="grassy">grassy</option>
            <option value="psychic">psychic</option><option value="misty">misty</option>
          </select>
        </label>
      </div>
      <div class="mon-meta">
        <label class="chip"><input type="checkbox" id="evtSpread" checked /> spread (doubles)</label>
        <label class="chip"><input type="checkbox" id="evtCrit" /> crit</label>
        <label class="chip"><input type="checkbox" id="evtReflect" /> reflect</label>
        <label class="chip"><input type="checkbox" id="evtLight" /> light screen</label>
        <label class="chip"><input type="checkbox" id="evtVeil" /> aurora veil</label>
      </div>
    </div>
  ` : "";

  return `
    <datalist id="evtMonsList">${monsList}</datalist>
    <datalist id="evtMovesList">${movesList}</datalist>
    <div class="calc-grid">
      <div class="calc-card">
        <label>Il mio Pokémon
          <input id="evtOurSpecies" list="evtMonsList" placeholder="Es. Iron Hands" value="${escapeHtml(evtuner.ourSpecies)}" />
        </label>
        <label>Oppure dal team
          <select id="evtOurFromTeam">
            <option value="">— seleziona slot del team —</option>
          </select>
        </label>
      </div>
      <div class="calc-card">
        <label>Bersaglio
          <input id="evtTargetSpecies" list="evtMonsList" placeholder="Es. Garchomp" value="${escapeHtml(evtuner.targetSpecies)}" />
        </label>
        ${targetSpreadBlock}
      </div>
    </div>
    <div class="calc-card">
      ${modeFields}
    </div>
    ${fieldFlags}
    <div style="margin-top:10px"><button id="evtRun" class="primary" type="button">Calcola spread minimo</button></div>
  `;
}

function spreadMakerFormHtml() {
  const baseMons = visibleMons().map((m) => m.name);
  const megaMons = (state.catalog?.megaForms || []).map((m) => m.name);
  const monsList = [...baseMons, ...megaMons]
    .map((n) => `<option value="${escapeHtml(n)}">`)
    .join("");
  return `
    <datalist id="evtMonsList">${monsList}</datalist>

    <div class="calc-card">
      <strong>Il mio Pokémon</strong>
      <div class="calc-grid" style="margin-top:6px">
        <label>Species
          <input id="smOurSpecies" list="evtMonsList" placeholder="Es. Snorlax" value="${escapeHtml(evtuner.ourSpecies || "")}" />
        </label>
        <label>Oppure dal team
          <select id="smOurFromTeam"><option value="">— slot del team —</option></select>
        </label>
        <label>Nature
          <select id="smNature">${EVT_NATURES.map(n => `<option value="${n}">${n}</option>`).join("")}</select>
        </label>
        <label>Ruolo
          <select id="smRole">
            <option value="offensive">offensive</option>
            <option value="defensive">defensive</option>
          </select>
        </label>
        <label>Item (opzionale, sovrascrive Pokékipe)
          <input id="smItemOverride" type="search" placeholder="Es. Sitrus Berry (per disabilitare Mega)" />
        </label>
      </div>
      <div id="smResolvedInfo" class="muted" style="font-size:11px;margin-top:4px"></div>
      <details style="margin-top:6px">
        <summary class="muted" style="font-size:11px;cursor:pointer">⚙ Boost di statistiche (es. Swords Dance, Calm Mind, Iron Defense)</summary>
        <div class="calc-grid" style="margin-top:6px;grid-template-columns:repeat(5,1fr)">
          <label>Atk <input data-sm-boost="atk" type="number" min="-6" max="6" value="0" /></label>
          <label>Def <input data-sm-boost="def" type="number" min="-6" max="6" value="0" /></label>
          <label>SpA <input data-sm-boost="spa" type="number" min="-6" max="6" value="0" /></label>
          <label>SpD <input data-sm-boost="spd" type="number" min="-6" max="6" value="0" /></label>
          <label>Spe <input data-sm-boost="spe" type="number" min="-6" max="6" value="0" /></label>
        </div>
      </details>
      <label style="margin-top:6px">Weather attivo (opzionale)
        <select id="smWeather">
          <option value="">nessuno</option>
          <option value="sun">sun (fire ×1.5, water ×0.5)</option>
          <option value="rain">rain (water ×1.5, fire ×0.5)</option>
          <option value="sand">sand (rock SpD +50%)</option>
          <option value="snow">snow (ice Def +50%)</option>
        </select>
      </label>
      <label class="chip" style="margin-top:4px"><input type="checkbox" id="smIgnoreAbWeather" /> ignora weather da ability (Drought / Drizzle / Sand Stream / Snow Warning)</label>
      <div id="smTotalUsed" class="muted" style="font-size:12px;margin-top:6px">EV usati: 0 / 66</div>
    </div>

    <div class="calc-card" style="margin-top:8px">
      <strong>1. Velocità</strong>
      <div class="calc-grid" style="margin-top:6px">
        <label>EV Spe
          <input id="smEvSpe" data-sm-ev="spe" type="number" min="0" max="32" value="${evtuner.lastSpeEv ?? 0}" />
        </label>
        <label>Bersaglio singolo (opz.)
          <input id="smDualTarget" list="evtMonsList" placeholder="Es. Garchomp" />
        </label>
      </div>
      <div id="smSpeedHint" class="muted" style="font-size:11px"></div>
      <div class="evt-universal-buttons" style="margin-top:6px">
        <button data-sm-pool="single" type="button">vs bersaglio singolo</button>
        <button data-sm-pool="meta_top" data-sm-limit="40" type="button">vs top 40 usage</button>
        <button data-sm-pool="all" type="button">vs tutti i mon con dati</button>
        <button data-sm-pool="counters" type="button">vs counter</button>
        <button data-sm-pool="victims" type="button">vs counterati</button>
      </div>
      <div id="smSpeedReport" class="sm-report-box muted" style="margin-top:6px">— inserisci EV Spe e clicca "Aggiorna report" —</div>
    </div>

    <div class="calc-card" style="margin-top:8px">
      <strong>2. Attacchi</strong>
      <div class="calc-grid" style="margin-top:6px">
        <label>EV Atk
          <input id="smEvAtk" data-sm-ev="atk" type="number" min="0" max="32" value="0" />
        </label>
        <label>EV SpA
          <input id="smEvSpa" data-sm-ev="spa" type="number" min="0" max="32" value="0" />
        </label>
      </div>
      <div class="evt-universal-buttons" style="margin-top:6px">
        <button data-sm-dmgpool="single" type="button">vs bersaglio singolo</button>
        <button data-sm-dmgpool="meta_top" type="button">vs top 40 usage</button>
        <button data-sm-dmgpool="all" type="button">vs tutti i mon con dati</button>
        <button data-sm-dmgpool="counters" type="button">vs counter</button>
        <button data-sm-dmgpool="victims" type="button">vs counterati</button>
      </div>
      <div id="smDamageRec" class="muted" style="font-size:11px;margin-top:6px">— scegli un pool per ricevere un consiglio (lo digiti tu sopra) —</div>
      <div id="smDamageReport" class="sm-report-box muted" style="margin-top:6px">— compila gli EV o usa Auto-set, poi clicca "Aggiorna report" in basso —</div>
    </div>

    <div class="calc-card" style="margin-top:8px">
      <strong>3. Bulk</strong>
      <div class="calc-grid" style="margin-top:6px">
        <label>EV HP
          <input id="smEvHp" data-sm-ev="hp" type="number" min="0" max="32" value="0" />
        </label>
        <label>EV Def
          <input id="smEvDef" data-sm-ev="def" type="number" min="0" max="32" value="0" />
        </label>
        <label>EV SpD
          <input id="smEvSpd" data-sm-ev="spd" type="number" min="0" max="32" value="0" />
        </label>
      </div>
      <div class="evt-universal-buttons" style="margin-top:6px">
        <button data-sm-bulkpool="single" type="button">vs bersaglio singolo</button>
        <button data-sm-bulkpool="meta_top" type="button">vs top 40 usage</button>
        <button data-sm-bulkpool="all" type="button">vs tutti i mon con dati</button>
        <button data-sm-bulkpool="counters" type="button">vs counter</button>
        <button data-sm-bulkpool="victims" type="button">vs counterati</button>
      </div>
      <div id="smBulkRec" class="muted" style="font-size:11px;margin-top:6px">— scegli un pool per ricevere un consiglio (lo digiti tu sopra) —</div>
      <div id="smBulkReport" class="sm-report-box muted" style="margin-top:6px">— compila gli EV o usa Auto-set, poi clicca "Aggiorna report" in basso —</div>
    </div>

    <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">
      <button id="smRefresh" class="primary" type="button">Aggiorna report</button>
      <button id="smApplyButton" type="button">Applica al team…</button>
      <select id="smApplyTarget"><option value="">—</option></select>
    </div>
  `;
}

function attachSpreadMakerHandlers() {
  const ourInput = document.querySelector("#smOurSpecies");
  const ourFromTeam = document.querySelector("#smOurFromTeam");
  const natureSel = document.querySelector("#smNature");
  const runBtn = document.querySelector("#smRun");

  if (ourFromTeam) {
    const opts = ['<option value="">— slot del team —</option>'];
    state.selected.forEach((s, i) => {
      opts.push(`<option value="${escapeHtml(s)}">${i + 1}. ${escapeHtml(s)}</option>`);
    });
    ourFromTeam.innerHTML = opts.join("");
    ourFromTeam.addEventListener("change", () => {
      if (!ourFromTeam.value) return;
      const species = ourFromTeam.value;
      if (ourInput) ourInput.value = species;
      resetSpreadMakerFields();
      const override = state.overrides[species] || {};
      const member = (state.lastTeam || []).find((m) => m.species === species);
      const nature = override.nature || member?.nature;
      if (nature && natureSel) natureSel.value = nature;
      // Inherit Spe EV + item override if the team slot has them configured
      const speEv = (override.evs || {}).spe ?? (member?.evs || {}).spe;
      if (speEv != null) smSetEv("spe", speEv);
      const item = override.item || member?.item;
      const itemEl = document.querySelector("#smItemOverride");
      if (itemEl && item) itemEl.value = item;
      resolveAndShowInfo(species);
    });
  }
  if (ourInput) {
    // Track previous species so we only wipe when it actually changes
    let _lastSpecies = ourInput.value.trim().toLowerCase();
    ourInput.addEventListener("change", () => {
      const newSpecies = ourInput.value.trim();
      if (newSpecies.toLowerCase() !== _lastSpecies) {
        resetSpreadMakerFields();
        _lastSpecies = newSpecies.toLowerCase();
      }
      resolveAndShowInfo(newSpecies);
    });
  }
  // Item override → re-resolve info so the user sees Tyranitar vs Tyranitar-Mega live
  const itemOv = document.querySelector("#smItemOverride");
  if (itemOv) {
    itemOv.addEventListener("change", () => {
      const cur = document.querySelector("#smOurSpecies")?.value.trim();
      if (cur) resolveAndShowInfo(cur);
    });
  }
}

function resetSpreadMakerFields() {
  // Wipe EV inputs, boosts and item override so the new mon starts clean.
  EVT_STATS.forEach((k) => smSetEv(k, 0));
  document.querySelectorAll("[data-sm-boost]").forEach((el) => { el.value = 0; });
  const itemEl = document.querySelector("#smItemOverride");
  if (itemEl) itemEl.value = "";
  const rec1 = document.querySelector("#smDamageRec");
  const rec2 = document.querySelector("#smBulkRec");
  if (rec1) rec1.textContent = "— scegli un pool per ricevere un consiglio (lo digiti tu sopra) —";
  if (rec2) rec2.textContent = "— scegli un pool per ricevere un consiglio (lo digiti tu sopra) —";
  recomputeSmTotal();
  // Speed-calc buttons (integrated TW+TR)
  document.querySelectorAll("[data-sm-pool]").forEach((btn) => {
    btn.addEventListener("click", () => runSpeedCalcInSpreadMaker(btn.dataset.smPool, btn.dataset.smLimit));
  });
  // EV inputs → live total + debounced report refresh so manual edits
  // are immediately reflected without needing to click "Aggiorna report".
  let _smInputDebounce;
  document.querySelectorAll("[data-sm-ev]").forEach((el) => {
    el.addEventListener("input", () => {
      recomputeSmTotal();
      clearTimeout(_smInputDebounce);
      _smInputDebounce = setTimeout(() => refreshSmReport(), 500);
    });
  });
  recomputeSmTotal();
  const refreshBtn = document.querySelector("#smRefresh");
  if (refreshBtn) refreshBtn.addEventListener("click", refreshSmReport);
  // Section pool buttons: refresh that report AND compute a textual suggestion
  // ("→ ti basterebbero X EV") based on the remaining EV budget (66 - other fields).
  document.querySelectorAll("[data-sm-dmgpool]").forEach((btn) => {
    btn.addEventListener("click", () => {
      refreshSmReportSection("damage", btn.dataset.smDmgpool);
      computeSuggestion("offensive", btn.dataset.smDmgpool);
    });
  });
  document.querySelectorAll("[data-sm-bulkpool]").forEach((btn) => {
    btn.addEventListener("click", () => {
      refreshSmReportSection("bulk", btn.dataset.smBulkpool);
      computeSuggestion("defensive", btn.dataset.smBulkpool);
    });
  });
  const applyBtn = document.querySelector("#smApplyButton");
  if (applyBtn) applyBtn.addEventListener("click", smApplyToTeam);
}

async function resolveAndShowInfo(name) {
  // Hit /api/combatant — pass the item override if the user typed one, so the
  // backend resolves to the mon's BASE form when the Mega stone is dropped.
  const info = document.querySelector("#smResolvedInfo");
  if (!info) return;
  if (!name) { info.textContent = ""; return; }
  const itemOverride = (document.querySelector("#smItemOverride")?.value || "").trim();
  const qs = new URLSearchParams({ name });
  if (itemOverride) qs.set("item", itemOverride);
  try {
    const d = await fetchJson(`/api/combatant?${qs.toString()}`);
    if (d.error) { info.textContent = d.error; return; }
    const types = (d.types || []).map(escapeHtml).join("/");
    const megaTag = d.isMega ? '<span class="chip gold" style="font-size:10px">MEGA</span> ' : "";
    info.innerHTML = `→ ${megaTag}<strong>${escapeHtml(d.name)}</strong> (${types}) · item <strong>${escapeHtml(d.item || "—")}</strong> · ability <strong>${escapeHtml(d.ability || "—")}</strong>`;
  } catch (e) {
    info.textContent = "";
  }
}

async function computeSuggestion(role, pool) {
  // role ∈ "offensive" | "defensive"
  // We tell the backend which stats the user has already committed (the "other"
  // stats) so its auto-allocation runs only on the remaining budget.
  const ourSpecies = document.querySelector("#smOurSpecies")?.value.trim();
  const nature = document.querySelector("#smNature")?.value;
  const weather = document.querySelector("#smWeather")?.value || "";
  const target = document.querySelector("#smDualTarget")?.value.trim() || "";
  const recId = role === "offensive" ? "#smDamageRec" : "#smBulkRec";
  const recEl = document.querySelector(recId);
  if (!ourSpecies || !nature) {
    if (recEl) recEl.textContent = "Compila Species + Nature per ottenere un consiglio.";
    return;
  }
  // Pin every stat that's NOT the one this role is meant to optimise.
  const allEvs = smReadAllEvs();
  const fixedEvs = {};
  if (role === "offensive") {
    // We're suggesting Atk or SpA — pin everything else.
    ["hp", "def", "spa", "spd", "spe", "atk"].forEach((k) => {
      if (k !== "atk" && k !== "spa") fixedEvs[k] = allEvs[k];
    });
  } else {
    // We're suggesting HP/Def/SpD — pin the rest.
    ["spe", "atk", "spa"].forEach((k) => { fixedEvs[k] = allEvs[k]; });
  }
  if (recEl) recEl.textContent = "Calcolo consiglio…";
  let data;
  try {
    data = await fetchJson("/api/spread-maker", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ourSpecies, nature, fixedEvs, role, weather, pool, targetSpecies: target,
      }),
    });
  } catch (e) {
    if (recEl) recEl.textContent = `Errore: ${e.message || e}`;
    return;
  }
  if (!data.ok) {
    if (recEl) recEl.textContent = `Errore: ${data.error || "calc fallito"}`;
    return;
  }
  const r = data.result || {};
  const newEvs = r.evs || {};
  if (!recEl) return;
  if (role === "offensive") {
    const offStat = r.offensiveStat;
    const offEv = (offStat === "atk" ? newEvs.atk : newEvs.spa) || 0;
    const label = offStat === "atk" ? "Atk" : "SpA";
    const dmgFirst = (r.damageReport && r.damageReport[0])
      ? ` → OHKO ${escapeHtml(r.damageReport[0].name)} con ${escapeHtml(r.damageReport[0].move)}`
      : "";
    recEl.innerHTML = `💡 Consiglio (vs ${escapeHtml(pool)}): <strong>${offEv} EV ${label}</strong> bastano${dmgFirst}. Digita tu il valore sopra.`;
  } else {
    const parts = [];
    if (newEvs.hp) parts.push(`${newEvs.hp} HP`);
    if (newEvs.def) parts.push(`${newEvs.def} Def`);
    if (newEvs.spd) parts.push(`${newEvs.spd} SpD`);
    const summary = parts.length ? parts.join(" + ") : "0 EV difensivi";
    const survives = (r.bulkReport || []).filter((b) => b.survives).length;
    const total = (r.bulkReport || []).length;
    recEl.innerHTML = `💡 Consiglio (vs ${escapeHtml(pool)}): <strong>${escapeHtml(summary)}</strong> → sopravvivi a ${survives}/${total} attacchi del pool. Digita tu i valori sopra.`;
  }
}

function recomputeSmTotal() {
  const total = EVT_STATS.reduce((s, k) => s + smReadEv(k), 0);
  const el = document.querySelector("#smTotalUsed");
  if (!el) return;
  if (total > 66) {
    el.innerHTML = `<span class="evt-manual-total invalid"><strong>EV usati: ${total} / 66</strong> — oltre il cap Champions</span>`;
  } else {
    el.textContent = `EV usati: ${total} / 66 · avanza ${66 - total}`;
  }
}

function smReadEv(stat) {
  const el = document.querySelector(`[data-sm-ev='${stat}']`);
  return Math.max(0, Math.min(32, parseInt(el?.value || "0", 10) || 0));
}

function smReadAllEvs() {
  return EVT_STATS.reduce((acc, k) => { acc[k] = smReadEv(k); return acc; }, {});
}

function smReadBoosts() {
  const boosts = {};
  document.querySelectorAll("[data-sm-boost]").forEach((el) => {
    const stat = el.dataset.smBoost;
    const v = parseInt(el.value || "0", 10);
    if (!Number.isNaN(v) && v !== 0) boosts[stat] = Math.max(-6, Math.min(6, v));
  });
  return boosts;
}

function smSetEv(stat, value) {
  const el = document.querySelector(`[data-sm-ev='${stat}']`);
  if (el) {
    el.value = Math.max(0, Math.min(32, value | 0));
    recomputeSmTotal();
  }
}

async function refreshSmReport(opts = {}) {
  // opts: { scope: "all"|"speed"|"damage"|"bulk", pool: "meta_top"|... }
  const scope = opts.scope || "all";
  const pool = opts.pool || "meta_top";
  const ourSpecies = document.querySelector("#smOurSpecies")?.value.trim();
  const nature = document.querySelector("#smNature")?.value;
  const weather = document.querySelector("#smWeather")?.value || "";
  const speedBox = document.querySelector("#smSpeedReport");
  const damageBox = document.querySelector("#smDamageReport");
  const bulkBox = document.querySelector("#smBulkReport");
  if (!ourSpecies || !nature) {
    if (damageBox) damageBox.textContent = "Compila Species + Nature.";
    return;
  }
  const placeholder = `<div class="muted">Calcolo (pool=${escapeHtml(pool)})…</div>`;
  if (scope === "all" || scope === "speed") speedBox && (speedBox.innerHTML = placeholder);
  if (scope === "all" || scope === "damage") damageBox && (damageBox.innerHTML = placeholder);
  if (scope === "all" || scope === "bulk") bulkBox && (bulkBox.innerHTML = placeholder);
  const targetSpecies = document.querySelector("#smDualTarget")?.value.trim() || "";
  let data;
  try {
    data = await fetchJson("/api/spread-maker/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ourSpecies, nature, evs: smReadAllEvs(), weather,
        pool, targetSpecies, metaLimit: 40,
        boosts: smReadBoosts(),
        ignoreAbilityWeather: document.querySelector("#smIgnoreAbWeather")?.checked || false,
        ourItem: (document.querySelector("#smItemOverride")?.value || "").trim() || undefined,
      }),
    });
  } catch (e) {
    if (damageBox) damageBox.textContent = `Errore: ${e.message || e}`;
    return;
  }
  if (!data.ok) {
    if (damageBox) damageBox.textContent = `Errore: ${data.error || "calc fallito"}`;
    return;
  }
  // Speed report — 3 disjoint columns
  if ((scope === "all" || scope === "speed") && speedBox && data.speed) {
    const sp = data.speed;
    const fmt = (lst) => lst.map((e) => `<li>${escapeHtml(e.name)} <span class="muted">(${e.spe} Spe)</span></li>`).join("");
    speedBox.innerHTML = `
      <div class="muted" style="font-size:11px;margin-bottom:4px">
        La tua Spe finale: <strong>${sp.ourSpeed}</strong>
        · calcolato su <strong>${(data.damageTargets || []).length}</strong> mon
      </div>
      <div class="sm-grid" style="grid-template-columns:repeat(4,1fr)">
        <div>
          <div class="evt-uni-title">Normalmente (${sp.outsped.length})</div>
          <ul class="evt-uni-list">${fmt(sp.outsped) || '<li class="muted">—</li>'}</ul>
        </div>
        <div>
          <div class="evt-uni-title">Con Tailwind (${sp.outspedOnlyTw.length})</div>
          <ul class="evt-uni-list">${fmt(sp.outspedOnlyTw) || '<li class="muted">—</li>'}</ul>
        </div>
        <div>
          <div class="evt-uni-title">Con Trick Room (${(sp.outspedOnlyTr || []).length})</div>
          <div class="muted" style="font-size:10px">più veloci di te senza field → in TR muovi prima (include anche quelli battibili con TW)</div>
          <ul class="evt-uni-list">${fmt(sp.outspedOnlyTr || []) || '<li class="muted">—</li>'}</ul>
        </div>
        <div>
          <div class="evt-uni-title">Speed tie / mai (${(sp.speedTie || []).length})</div>
          <ul class="evt-uni-list">${fmt(sp.speedTie || []) || '<li class="muted">—</li>'}</ul>
        </div>
      </div>
    `;
  }
  const damageHeader = `
    <div class="muted" style="font-size:11px;margin-bottom:4px">
      Calcolato su <strong>${(data.damageTargets || []).length}</strong> mon
      (${data.counterablesCount} counterables, peso 2x):
      <details style="display:inline"><summary>mostra elenco</summary>
        <span style="font-size:11px">${escapeHtml((data.damageTargets || []).join(", "))}</span>
      </details>
    </div>`;
  const dmgRows = (data.damage || []).map((d) => `
    <li>
      <span class="${d.counterPriority ? 'sm-prio' : ''}">${escapeHtml(d.name)}</span>
      <span class="muted">${escapeHtml(d.move)} · ${d.minPct}-${d.maxPct}% · ${escapeHtml(d.koChance)}</span>
    </li>`).join("");
  if ((scope === "all" || scope === "damage") && damageBox) damageBox.innerHTML = damageHeader + (dmgRows
    ? `<ul class="evt-uni-list">${dmgRows}</ul>`
    : '<div class="muted">Nessun damage calcolabile (EV offensivi a 0?).</div>');

  const bulkHeader = `
    <div class="muted" style="font-size:11px;margin-bottom:4px">
      Calcolato vs i top <strong>${(data.bulkTargets || []).length}</strong> mon meta:
      <details style="display:inline"><summary>mostra elenco</summary>
        <span style="font-size:11px">${escapeHtml((data.bulkTargets || []).join(", "))}</span>
      </details>
    </div>`;
  const bulkRows = (data.bulk || []).map((b) => {
    const tag = b.survives
      ? `<span class="chip green" style="font-size:9px">sopravvivi 1 colpo</span>`
      : `<span class="chip red" style="font-size:9px">${escapeHtml(b.koChance)}</span>`;
    return `
    <li>
      <strong>${escapeHtml(b.threat)}</strong> ${tag}
      <span class="muted">${escapeHtml(b.move)} · ${b.minPct}-${b.maxPct}%</span>
    </li>`;
  }).join("");
  if ((scope === "all" || scope === "bulk") && bulkBox) bulkBox.innerHTML = bulkHeader + (bulkRows
    ? `<ul class="evt-uni-list">${bulkRows}</ul>`
    : '<div class="muted">—</div>');
}

function refreshSmReportSection(scope, pool) {
  return refreshSmReport({ scope, pool });
}

async function smAutoFill(scope) {
  const ourSpecies = document.querySelector("#smOurSpecies")?.value.trim();
  const nature = document.querySelector("#smNature")?.value;
  const role = document.querySelector("#smRole")?.value || "offensive";
  const weather = document.querySelector("#smWeather")?.value || "";
  if (!ourSpecies || !nature) {
    showToast("Compila Species + Nature prima di usare auto-set.", "error");
    return;
  }
  const fixedEvs = { spe: smReadEv("spe") };
  // For scope "offensive": want role=offensive
  // For scope "bulk": want role=defensive
  // For scope "all": user-selected role
  let usedRole = role;
  if (scope === "offensive") usedRole = "offensive";
  else if (scope === "bulk") usedRole = "defensive";
  let data;
  try {
    data = await fetchJson("/api/spread-maker", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ourSpecies, nature, fixedEvs, role: usedRole, weather,
        ignoreAbilityWeather: document.querySelector("#smIgnoreAbWeather")?.checked || false,
        ourItem: (document.querySelector("#smItemOverride")?.value || "").trim() || undefined,
      }),
    });
  } catch (e) {
    showToast(`Errore auto-set: ${e.message || e}`, "error");
    return;
  }
  if (!data.ok) {
    showToast(`Errore auto-set: ${data.error || ""}`, "error");
    return;
  }
  const newEvs = (data.result || {}).evs || {};
  // Apply only the relevant stats to the form
  if (scope === "all") {
    EVT_STATS.forEach((k) => smSetEv(k, newEvs[k] || 0));
  } else if (scope === "offensive") {
    ["atk", "spa"].forEach((k) => smSetEv(k, newEvs[k] || 0));
  } else if (scope === "bulk") {
    ["hp", "def", "spd"].forEach((k) => smSetEv(k, newEvs[k] || 0));
  }
  // Show inline recommendation banner
  const r = data.result || {};
  if (scope === "offensive" || scope === "all") {
    const rec = document.querySelector("#smDamageRec");
    if (rec) {
      const offEv = (r.offensiveStat === "atk" ? newEvs.atk : newEvs.spa) || 0;
      const offText = r.offensiveStat === "atk" ? `${offEv} Atk` : `${offEv} SpA`;
      rec.classList.remove("hidden");
      rec.innerHTML = `💡 <strong>Consiglio:</strong> ${escapeHtml(offText)} (minimo per ottenere i KO che ottieni con 32 EV). Avanzi gli EV per la bulk.`;
    }
  }
  if (scope === "bulk" || scope === "all") {
    const rec = document.querySelector("#smBulkRec");
    if (rec) {
      const parts = [];
      if (newEvs.hp) parts.push(`${newEvs.hp} HP`);
      if (newEvs.def) parts.push(`${newEvs.def} Def`);
      if (newEvs.spd) parts.push(`${newEvs.spd} SpD`);
      const summary = parts.length ? parts.join(" / ") : "0 EV difensivi";
      const bulkLine = (r.bulkReport && r.bulkReport[0])
        ? ` Sopravvivi a <strong>${escapeHtml(r.bulkReport[0].threat)}</strong> ${escapeHtml(r.bulkReport[0].move)}.`
        : "";
      rec.classList.remove("hidden");
      rec.innerHTML = `💡 <strong>Consiglio:</strong> ${escapeHtml(summary)}.${bulkLine}`;
    }
  }
  await refreshSmReport();
  showToast(`${ourSpecies}: auto-set ${scope} applicato.`, "success");
}

async function smApplyToTeam() {
  const ourSpecies = document.querySelector("#smOurSpecies")?.value.trim();
  const nature = document.querySelector("#smNature")?.value;
  const target = document.querySelector("#smApplyTarget")?.value;
  if (!ourSpecies || !nature) {
    showToast("Compila Species + Nature prima di applicare.", "error");
    return;
  }
  if (!target) {
    showToast("Seleziona uno slot del team dal dropdown.", "error");
    return;
  }
  const fullEvs = smReadAllEvs();
  const prev = state.overrides[target] || {};
  state.overrides[target] = {
    ...prev,
    nature,
    evs: { ...(prev.evs || {}), ...fullEvs },
  };
  await refresh();
  showToast(`${target}: spread applicato (${formatEvs(fullEvs)} ${nature}).`, "success");
}

async function runSpeedCalcInSpreadMaker(pool, limit) {
  const hint = document.querySelector("#smSpeedHint");
  const ourSpecies = document.querySelector("#smOurSpecies")?.value.trim();
  const natureSel = document.querySelector("#smNature");
  const speInput = document.querySelector("#smFixedSpe");
  if (!ourSpecies) {
    if (hint) hint.textContent = "Inserisci prima il tuo Pokémon.";
    return;
  }
  if (hint) hint.textContent = "Calcolo velocità…";

  const payload = { mode: "dualspeed", ourSpecies };
  if (pool === "single") {
    const target = document.querySelector("#smDualTarget")?.value.trim();
    if (!target) {
      if (hint) hint.textContent = "Per 'vs bersaglio singolo' compila il campo Bersaglio.";
      return;
    }
    payload.targetSpecies = target;
    payload.targetSpreadIndex = 0;
  } else {
    payload.universal = true;
    payload.pool = pool;
    if (limit) payload.metaLimit = parseInt(limit, 10);
  }
  // If user picked a nature from a team slot, honour it as the lock
  if (natureSel?.value) payload.ourNatureLock = natureSel.value;

  let data;
  try {
    data = await fetchJson("/api/ev-optimizer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    if (hint) hint.textContent = `Errore: ${e.message || e}`;
    return;
  }
  if (!data.ok) {
    if (hint) hint.textContent = `Errore: ${data.error || "calcolo fallito"}`;
    return;
  }
  const r = data.result || {};
  const speEv = (r.evs || {}).spe ?? 0;
  if (speInput) speInput.value = speEv;
  if (natureSel && r.nature) natureSel.value = r.nature;
  evtuner.lastSpeEv = speEv;
  const coveredCount = (r.covered || []).length;
  const summary = r.universal
    ? `→ ${r.nature} ${speEv} EV Spe (${r.ourSpeed} Spe); dual-batti ${coveredCount}/${data.assumptions?.metaTargetsCount} target.`
    : `→ ${r.nature} ${speEv} EV Spe (${r.ourSpeed} Spe vs ${r.targetSpeed} bersaglio).`;
  if (hint) hint.textContent = summary;
}

async function runSpreadMaker() {
  const resultCard = document.querySelector("#smResultCard");
  const ourSpecies = document.querySelector("#smOurSpecies")?.value.trim();
  const nature = document.querySelector("#smNature")?.value;
  const fixedSpe = parseInt(document.querySelector("#smFixedSpe")?.value || "0", 10) || 0;
  const role = document.querySelector("#smRole")?.value || "offensive";
  const weather = document.querySelector("#smWeather")?.value || "";
  if (!ourSpecies || !nature) {
    resultCard.classList.remove("hidden");
    resultCard.innerHTML = `<div class="note">Compila il mio Pokémon e la nature.</div>`;
    return;
  }
  resultCard.classList.remove("hidden");
  resultCard.innerHTML = `<div class="muted">Calcolo…</div>`;
  let data;
  try {
    data = await fetchJson("/api/spread-maker", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ourSpecies, nature, fixedEvs: { spe: fixedSpe }, role, weather }),
    });
  } catch (e) {
    resultCard.innerHTML = `<div class="note">Errore: ${escapeHtml(e.message || String(e))}</div>`;
    return;
  }
  if (!data.ok) {
    resultCard.innerHTML = `<div class="note">Errore: ${escapeHtml(data.error || "")}</div>`;
    return;
  }
  renderSpreadMakerResult(data);
}

function renderSpreadMakerResult(data) {
  const card = document.querySelector("#smResultCard");
  if (!card) return;
  const r = data.result || {};
  const evs = r.evs || {};
  const evStr = EVT_STATS.map(k => evs[k] ? `${evs[k]} ${k.toUpperCase()}` : null).filter(Boolean).join(" / ") || "0 EV";
  const damageRows = (r.damageReport || []).slice(0, 10).map((d) => `
    <li>
      <span class="${d.counterPriority ? 'sm-prio' : ''}">${escapeHtml(d.name)}</span>
      <span class="muted">${escapeHtml(d.move)} · ${d.minPct}-${d.maxPct}% · ${escapeHtml(d.koChance)}</span>
    </li>
  `).join("");
  const bulkRows = (r.bulkReport || []).map((b) => `
    <li>
      ${b.survives ? '✓' : '✗'} <strong>${escapeHtml(b.threat)}</strong>
      <span class="muted">${escapeHtml(b.move)} · ${b.minPct}-${b.maxPct}% · ${escapeHtml(b.koChance)}</span>
    </li>
  `).join("");
  const notes = (r.notes || []).map((n) => `<div class="note">${escapeHtml(n)}</div>`).join("");
  const teamApplyOptions = state.selected.map((s, i) => `<option value="${escapeHtml(s)}">${i + 1}. ${escapeHtml(s)}</option>`).join("");
  const applyBlock = teamApplyOptions ? `
    <div class="evt-apply-row">
      <span class="muted" style="font-size:12px">Applica a:</span>
      <select id="smApplyTarget"><option value="">—</option>${teamApplyOptions}</select>
      <button id="smApplyButton" type="button">Applica al team</button>
    </div>
  ` : "";

  card.innerHTML = `
    <div><span class="chip ${r.role === 'offensive' ? 'red' : 'green'}">${escapeHtml(r.role)}</span> <span class="muted" style="font-size:11px">offensive=${escapeHtml(r.offensiveStat)}, bulk=${escapeHtml(r.defensiveStat || '—')}</span></div>
    <div style="margin-top:6px"><span class="evt-spread">${escapeHtml(r.nature)} · ${escapeHtml(evStr)}</span></div>
    <div class="evt-assumptions">${data.metaTargetsCount} mon meta · ${data.counterablesCount} counterables (peso 2x nei danni)</div>
    ${notes}
    <div class="sm-grid">
      <div>
        <div class="evt-uni-title">Danni sui top meta</div>
        <ul class="evt-uni-list">${damageRows || '<li class="muted">—</li>'}</ul>
      </div>
      <div>
        <div class="evt-uni-title">Sopravvivenza vs top STAB</div>
        <ul class="evt-uni-list">${bulkRows || '<li class="muted">—</li>'}</ul>
      </div>
    </div>
    ${applyBlock}
  `;
  const applyBtn = document.querySelector("#smApplyButton");
  if (applyBtn) {
    applyBtn.addEventListener("click", () => applySpreadMakerToTeam(data));
  }
}

async function applySpreadMakerToTeam(data) {
  const sel = document.querySelector("#smApplyTarget");
  const species = sel?.value;
  if (!species) return;
  const r = data.result || {};
  const evs = r.evs || {};
  const fullEvs = { hp: evs.hp || 0, atk: evs.atk || 0, def: evs.def || 0, spa: evs.spa || 0, spd: evs.spd || 0, spe: evs.spe || 0 };
  const prev = state.overrides[species] || {};
  state.overrides[species] = {
    ...prev,
    nature: r.nature || prev.nature,
    evs: { ...(prev.evs || {}), ...fullEvs },
  };
  await refresh();
  showToast(`${species}: spread applicato (${formatEvs(fullEvs)} ${r.nature}).`, "success");
}

function attachEvTunerHandlers() {
  if (evtuner.mode === "spreadmaker") {
    attachSpreadMakerHandlers();
    return;
  }
  const ourInput = document.querySelector("#evtOurSpecies");
  const ourFromTeam = document.querySelector("#evtOurFromTeam");
  const targetInput = document.querySelector("#evtTargetSpecies");
  const targetSpread = document.querySelector("#evtTargetSpread");
  const runButton = document.querySelector("#evtRun");

  if (ourInput) ourInput.addEventListener("change", () => {
    evtuner.ourSpecies = ourInput.value.trim();
    // Manual edit drops any nature lock inherited from the team slot.
    evtuner.ourNatureLock = "";
    // OHKO mode: the move field shows OUR moves, so the suggestion list
    // should bubble up our learnset.
    if (evtuner.mode === "ohko") loadRelevantLearnset(evtuner.ourSpecies);
  });
  if (ourFromTeam) ourFromTeam.addEventListener("change", () => {
    if (!ourFromTeam.value) return;
    const speciesName = ourFromTeam.value;
    evtuner.ourSpecies = speciesName;
    if (ourInput) ourInput.value = speciesName;
    // Lock to the nature the user has configured on that slot (override or
    // SetBuilder default) so the tuner doesn't iterate over other natures.
    const override = state.overrides[speciesName] || {};
    const teamMember = (state.lastTeam || []).find((m) => m.species === speciesName);
    evtuner.ourNatureLock = override.nature || teamMember?.nature || "";
    if (evtuner.mode === "ohko") loadRelevantLearnset(speciesName);
  });
  if (targetInput) {
    targetInput.addEventListener("change", async () => {
      evtuner.targetSpecies = targetInput.value.trim();
      await loadTargetSpreads(targetInput.value.trim());
      // Survive mode: the move field shows ENEMY moves, suggest from the
      // target's learnset.
      if (evtuner.mode === "survive") loadRelevantLearnset(evtuner.targetSpecies);
    });
  }
  if (targetSpread) {
    targetSpread.addEventListener("change", () => {
      const val = targetSpread.value;
      const manual = document.querySelector("#evtManualSpread");
      if (val === "manual") {
        evtuner.useManual = true;
        if (manual) manual.classList.remove("hidden");
      } else {
        evtuner.useManual = false;
        evtuner.spreadIndex = parseInt(val, 10) || 0;
        if (manual) manual.classList.add("hidden");
      }
    });
  }
  document.querySelectorAll("[data-manual-ev]").forEach((input) => {
    input.addEventListener("input", () => {
      const stat = input.dataset.manualEv;
      evtuner.manualSpread.evs[stat] = parseInt(input.value, 10) || 0;
      const total = EVT_STATS.reduce((s, k) => s + (evtuner.manualSpread.evs[k] || 0), 0);
      const totalEl = document.querySelector("#evtManualTotal");
      if (totalEl) {
        totalEl.textContent = total;
        totalEl.parentElement.classList.toggle("invalid", total > 66);
      }
    });
  });
  const manualNature = document.querySelector("#evtManualNature");
  if (manualNature) {
    manualNature.value = evtuner.manualSpread.nature;
    manualNature.addEventListener("change", () => { evtuner.manualSpread.nature = manualNature.value; });
  }
  if (runButton) runButton.addEventListener("click", () => runEvTuner());
  document.querySelectorAll("[data-universal-pool]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const opts = { universal: true, pool: btn.dataset.universalPool };
      if (btn.dataset.universalLimit) opts.metaLimit = parseInt(btn.dataset.universalLimit, 10);
      runEvTuner(opts);
    });
  });

  // Initial spread load if target species already set
  if (evtuner.targetSpecies) loadTargetSpreads(evtuner.targetSpecies);
}

async function loadRelevantLearnset(species) {
  if (!species) {
    evtuner.relevantLearnset = null;
    repopulateEvtMovesDatalist();
    return;
  }
  let moves = evtuner.learnsetCache[species];
  if (!moves) {
    try {
      const data = await fetchJson(`/api/learnset?name=${encodeURIComponent(species)}`);
      moves = data.moves || [];
      evtuner.learnsetCache[species] = moves;
    } catch (e) {
      moves = [];
    }
  }
  evtuner.relevantLearnset = new Set(moves.map((m) => m.toLowerCase()));
  repopulateEvtMovesDatalist();
}

function repopulateEvtMovesDatalist() {
  const dl = document.querySelector("#evtMovesList");
  if (!dl) return;
  const all = evtuner.movesList;
  const relevant = evtuner.relevantLearnset;
  if (relevant && relevant.size > 0) {
    // Learnset moves first (deduplicated), then the rest as suggestions.
    const inLearn = all.filter((m) => relevant.has(m.toLowerCase()));
    const rest = all.filter((m) => !relevant.has(m.toLowerCase()));
    dl.innerHTML = [...inLearn, ...rest].map((m) => `<option value="${escapeHtml(m)}">`).join("");
  } else {
    dl.innerHTML = all.map((m) => `<option value="${escapeHtml(m)}">`).join("");
  }
}

async function loadTargetSpreads(species) {
  const sel = document.querySelector("#evtTargetSpread");
  if (!sel || !species) return;
  let data = evtuner.spreadsCache[species];
  if (!data) {
    try {
      data = await fetchJson(`/api/ev-optimizer/spreads/${encodeURIComponent(species)}`);
      evtuner.spreadsCache[species] = data;
    } catch (e) {
      data = { ok: false, spreads: [] };
    }
  }
  const opts = (data.spreads || []).map((s, i) => {
    const ev = EVT_STATS.map((k) => s.evs[k] || 0).join("/");
    return `<option value="${i}">${escapeHtml(s.nature)} ${ev} · ${s.usage.toFixed(1)}%</option>`;
  });
  if (!opts.length) {
    opts.push(`<option value="0">⚠ Off-meta — uso fallback offensivo</option>`);
  }
  opts.push(`<option value="manual">Personalizzata…</option>`);
  sel.innerHTML = opts.join("");
}

async function runEvTuner(opts = {}) {
  const resultCard = document.querySelector("#evtResultCard");
  const ourSpecies = document.querySelector("#evtOurSpecies")?.value.trim();
  const targetSpecies = document.querySelector("#evtTargetSpecies")?.value.trim();
  const universal = !!opts.universal;
  if (!ourSpecies) {
    if (resultCard) {
      resultCard.classList.remove("hidden");
      resultCard.innerHTML = `<div class="note">Compila il tuo Pokémon.</div>`;
    }
    return;
  }
  if (!universal && !targetSpecies) {
    if (resultCard) {
      resultCard.classList.remove("hidden");
      resultCard.innerHTML = `<div class="note">Compila il bersaglio (o usa "Spread universale").</div>`;
    }
    return;
  }
  evtuner.ourSpecies = ourSpecies;
  if (!universal) evtuner.targetSpecies = targetSpecies;

  const payload = { mode: evtuner.mode, ourSpecies };
  if (universal) {
    payload.universal = true;
    if (opts.pool) payload.pool = opts.pool;
    if (opts.metaLimit) payload.metaLimit = opts.metaLimit;
  } else {
    payload.targetSpecies = targetSpecies;
  }
  if (evtuner.ourNatureLock) payload.ourNatureLock = evtuner.ourNatureLock;
  if (!universal) {
    if (evtuner.useManual) {
      const total = EVT_STATS.reduce((s, k) => s + (evtuner.manualSpread.evs[k] || 0), 0);
      if (total > 66) {
        resultCard.classList.remove("hidden");
        resultCard.innerHTML = `<div class="note">Totale EV manuale ${total} > 66 (cap Champions).</div>`;
        return;
      }
      payload.targetSpreadManual = { nature: evtuner.manualSpread.nature, evs: evtuner.manualSpread.evs };
    } else {
      payload.targetSpreadIndex = evtuner.spreadIndex;
    }
  }

  if (evtuner.mode === "survive") {
    payload.move = document.querySelector("#evtMove")?.value.trim();
    payload.threshold = document.querySelector("#evtThreshold")?.value || "guaranteed";
    payload.field = collectEvtField();
  } else if (evtuner.mode === "ohko") {
    payload.move = document.querySelector("#evtMove")?.value.trim();
    payload.goal = document.querySelector("#evtGoal")?.value || "ohko";
    payload.field = collectEvtField();
  } else if (evtuner.mode === "outspeed") {
    payload.condition = document.querySelector("#evtCondition")?.value || "none";
  }

  resultCard.classList.remove("hidden");
  resultCard.innerHTML = `<div class="muted">Calcolo in corso…</div>`;

  let data;
  try {
    data = await fetchJson("/api/ev-optimizer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    resultCard.innerHTML = `<div class="note">Errore: ${escapeHtml(e.message || String(e))}</div>`;
    return;
  }
  if (!data.ok) {
    resultCard.innerHTML = `<div class="note">Errore: ${escapeHtml(data.error || "calc failed")}</div>`;
    return;
  }
  evtuner.lastResult = data;
  // If this run produced a Spe value (outspeed / trickroom / dualspeed),
  // remember it so the Spread Maker tab can pre-fill the "fixed Spe EV".
  const rEvs = (data.result || {}).evs || {};
  if (rEvs.spe != null) evtuner.lastSpeEv = rEvs.spe;
  renderEvTunerResult(data);
}

function collectEvtField() {
  return {
    weather: document.querySelector("#evtWeather")?.value || "",
    terrain: document.querySelector("#evtTerrain")?.value || "",
    spread: document.querySelector("#evtSpread")?.checked,
    crit: document.querySelector("#evtCrit")?.checked,
    reflect: document.querySelector("#evtReflect")?.checked,
    lightScreen: document.querySelector("#evtLight")?.checked,
    auroraVeil: document.querySelector("#evtVeil")?.checked,
  };
}

function renderEvTunerResult(data) {
  const card = document.querySelector("#evtResultCard");
  if (!card) return;
  const r = data.result || {};
  const evs = r.evs || {};
  const feasibilityChip = r.feasible
    ? `<span class="chip green">Vincolo soddisfatto</span>`
    : `<span class="chip red">Non garantito</span>`;
  const evStr = EVT_STATS.map(k => evs[k] ? `${evs[k]} ${k.toUpperCase()}` : null).filter(Boolean).join(" / ") || "0 EV";
  const ivLine = r.ivs ? `<div class="muted" style="font-size:11px">IV Spe: ${r.ivs.spe ?? 31}</div>` : "";
  const note = r.note ? `<div class="note">${escapeHtml(r.note)}</div>` : "";
  const a = data.assumptions || {};
  const spreadUsed = data.targetSpreadUsed || {};
  const assumptionsBlock = `
    <div class="evt-assumptions">
      vs <strong>${escapeHtml(a.targetName || "")}</strong> @ ${escapeHtml(spreadUsed.source || "?")}
      ${spreadUsed.nature ? `· nature ${escapeHtml(spreadUsed.nature)}` : ""}
      ${spreadUsed.usage != null ? `(${spreadUsed.usage.toFixed(1)}%)` : ""}
      ${a.evScaleNote ? `· ${escapeHtml(a.evScaleNote)}` : ""}
    </div>
  `;
  const narration = data.narration || {};
  const narrationBlock = narration.text ? `
    <div class="evt-narration">${escapeHtml(narration.text)}</div>
    <div class="muted" style="font-size:11px">Fonte: ${escapeHtml(narration.source || "—")} ${narration.enabled ? "" : "(offline)"}</div>
  ` : "";
  // Universal dual-speed extras: tables of who you dual-beat / who's too
  // fast for TR / who's too slow for TW.
  let universalBlock = "";
  if (r.universal) {
    const fmtRow = (m) => `<li>${escapeHtml(m.name)} <span class="muted">(${m.targetSpeed} Spe)</span></li>`;
    const covered = (r.covered || []).map(fmtRow).join("");
    const tooFast = (r.missedTooFastForTr || []).map(fmtRow).join("");
    const tooSlow = (r.missedTooSlowForTw || []).map(fmtRow).join("");
    universalBlock = `
      <div class="evt-universal-grid">
        <div>
          <div class="evt-uni-title">Dual-batti (${(r.covered||[]).length})</div>
          <div class="muted" style="font-size:10px">vinci sia sotto Tailwind che sotto Trick Room</div>
          <ul class="evt-uni-list">${covered || '<li class="muted">—</li>'}</ul>
        </div>
        <div>
          <div class="evt-uni-title">Senza field, perdi (${(r.missedTooFastForTr||[]).length})</div>
          <div class="muted" style="font-size:10px">sei più veloce di loro → in Trick Room muovi dopo</div>
          <ul class="evt-uni-list">${tooFast || '<li class="muted">—</li>'}</ul>
        </div>
        <div>
          <div class="evt-uni-title">Anche con TW non li superi (${(r.missedTooSlowForTw||[]).length})</div>
          <div class="muted" style="font-size:10px">la loro Spe è > 2× la tua</div>
          <ul class="evt-uni-list">${tooSlow || '<li class="muted">—</li>'}</ul>
        </div>
      </div>
    `;
  }
  const suggestions = (data.remainingSuggestions || []).map(s => `<li>${escapeHtml(s)}</li>`).join("");
  const suggBlock = suggestions ? `
    <div class="muted" style="margin-top:8px;font-size:12px;text-transform:uppercase;letter-spacing:0.4px">Residui (${data.remainingEvs || 0} EV avanzano)</div>
    <ul class="evt-suggestions">${suggestions}</ul>
  ` : "";
  const teamApplyOptions = state.selected.map((s, i) => `<option value="${escapeHtml(s)}">${i + 1}. ${escapeHtml(s)}</option>`).join("");
  const applyBlock = teamApplyOptions ? `
    <div class="evt-apply-row">
      <span class="muted" style="font-size:12px">Applica a:</span>
      <select id="evtApplyTarget"><option value="">—</option>${teamApplyOptions}</select>
      <button id="evtApplyButton" type="button">Applica al team</button>
    </div>
  ` : "";

  card.innerHTML = `
    <div>${feasibilityChip}</div>
    <div style="margin-top:6px"><span class="evt-spread">${escapeHtml(r.nature || "?")} · ${escapeHtml(evStr)}</span></div>
    ${ivLine}
    ${assumptionsBlock}
    ${note}
    ${narrationBlock}
    ${universalBlock}
    ${suggBlock}
    ${applyBlock}
  `;

  const applyButton = document.querySelector("#evtApplyButton");
  if (applyButton) {
    applyButton.addEventListener("click", () => applyTunerToTeam(data));
  }
}

async function applyTunerToTeam(data) {
  const sel = document.querySelector("#evtApplyTarget");
  const species = sel?.value;
  if (!species) return;
  const r = data.result || {};
  const evs = r.evs || {};
  // Merge with full 6-stat dict so partial overrides preserved
  const fullEvs = { hp: evs.hp || 0, atk: evs.atk || 0, def: evs.def || 0, spa: evs.spa || 0, spd: evs.spd || 0, spe: evs.spe || 0 };
  const prev = state.overrides[species] || {};
  state.overrides[species] = {
    ...prev,
    nature: r.nature || prev.nature,
    evs: { ...(prev.evs || {}), ...fullEvs },
  };
  await refresh();
}

function openTuner(species) {
  evtuner.ourSpecies = species;
  selectTab("evtuner");
  // Render to pick up the new ourSpecies, then focus the target field
  renderEvTuner();
  setTimeout(() => {
    const targetField = document.querySelector("#evtTargetSpecies");
    if (targetField) targetField.focus();
  }, 50);
}

// =================== /EV TUNER ===================

let _toastTimer = null;
function showToast(message, kind = "info") {
  const el = document.querySelector("#toast");
  if (!el) return;
  el.textContent = message;
  el.classList.remove("hidden", "success", "error");
  if (kind === "success") el.classList.add("success");
  if (kind === "error") el.classList.add("error");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
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
