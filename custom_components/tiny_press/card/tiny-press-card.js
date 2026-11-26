/*
 * Tiny Press dashboard card (custom:tiny-press-card).
 *
 * Served by the integration and loaded automatically, so there is nothing
 * extra to install. Plain web component, no build step, no dependencies.
 * Nothing prints unless someone presses a button.
 */

const CARD_VERSION = "0.11.2";

const PRINTS = {
  maze: { label: "Maze", icon: "mdi:map-marker-path" },
  word_search: { label: "Word search", icon: "mdi:text-search-variant" },
  math: { label: "Math", icon: "mdi:calculator-variant-outline" },
  joke: { label: "Joke", icon: "mdi:emoticon-happy-outline" },
  fact: { label: "Fun fact", icon: "mdi:lightbulb-on-outline" },
  kid_pack: { label: "Kid pack", icon: "mdi:package-variant-closed" },
  kid_sudoku: { label: "Kid sudoku", icon: "mdi:grid" },
  spelling: { label: "Spelling", icon: "mdi:alphabetical-variant" },
  spelling_search: { label: "Spelling search", icon: "mdi:text-box-search-outline" },
  sudoku: { label: "Sudoku", icon: "mdi:grid", adult: true },
  crossword: { label: "Crossword", icon: "mdi:alpha-c-box-outline", adult: true },
  cryptogram: { label: "Cryptogram", icon: "mdi:lock-question", adult: true },
  puzzle_pack: { label: "Puzzle pack", icon: "mdi:puzzle-outline", adult: true },
  story: { label: "Bedtime story", icon: "mdi:book-open-page-variant-outline", service: "print_story" },
  next_chapter: { label: "Next chapter", icon: "mdi:book-arrow-right-outline", service: "continue_story" },
  morning_slip: { label: "Morning slip", icon: "mdi:weather-sunset-up", service: "print_morning_slip" },
  weather: { label: "Weather", icon: "mdi:weather-partly-cloudy" },
};
const DEFAULT_BUTTONS = [
  "maze", "word_search", "math", "kid_sudoku", "spelling", "spelling_search", "joke", "kid_pack",
  "story", "next_chapter", "sudoku", "crossword", "cryptogram", "puzzle_pack",
  "morning_slip", "weather",
];

const PAPER = {
  ok: { label: "Paper OK", tone: "ok", icon: "mdi:paper-roll-outline" },
  near_end: { label: "Paper low", tone: "warn", icon: "mdi:paper-roll" },
  out: { label: "Out of paper", tone: "bad", icon: "mdi:paper-roll-outline" },
  cover_open: { label: "Cover open", tone: "bad", icon: "mdi:printer-pos-alert-outline" },
  offline: { label: "Offline", tone: "bad", icon: "mdi:printer-pos-off-outline" },
};

// translation_key -> role, used to find this printer's entities.
const ROLES = {
  online: "online",
  paper: "paper",
  paper_used: "paperUsed",
  last_print: "lastPrint",
  prints_left: "printsLeft",
  kid_profile: "kidProfile",
  adult_profile: "adultProfile",
  maze_difficulty: "mazeDifficulty",
  sudoku_difficulty: "sudokuDifficulty",
  story_length: "storyLength",
  next_chapter: "nextChapter",
  morning_slip: "morningSlip",
};

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class TinyPressCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = { busy: false, message: null, tone: null, preview: null, previewType: null };
    this._signature = "";
    this._tick = null;
    this._hold = null;
  }

  static getStubConfig() {
    return { kid_mode: false, show_preview: false };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "device_id", selector: { device: { integration: "tiny_press" } } },
        {
          name: "buttons",
          selector: {
            select: {
              multiple: true,
              mode: "list",
              options: Object.entries(PRINTS).map(([value, p]) => ({ value, label: p.label })),
            },
          },
        },
        { name: "kid_mode", selector: { boolean: {} } },
        { name: "history", selector: { object: {} } },
        { name: "feeds", selector: { object: {} } },
        { name: "show_preview", selector: { boolean: {} } },
        { name: "ignore_limits", selector: { boolean: {} } },
      ],
      computeLabel: (s) =>
        ({
          title: "Title",
          device_id: "Printer (only needed with more than one)",
          buttons: "Buttons",
          kid_mode: "Kid mode (hold to print, no settings or answers)",
          show_preview: "Preview before printing",
          ignore_limits: "Parent card: ignore kid-mode limits",
          history:
            "History buttons, e.g. - {name: Freezer, entity: sensor.freezer, hours: 24}",
          feeds: "Feed buttons, e.g. - {name: News, feed: BBC News, items: 5, qr: true}",
        })[s.name],
    };
  }

  setConfig(config) {
    this._config = {
      title: "Tiny Press",
      buttons: DEFAULT_BUTTONS,
      kid_mode: false,
      show_preview: false,
      ignore_limits: false,
      hold_ms: 800,
      ...config,
    };
    if (!Array.isArray(this._config.buttons) || !this._config.buttons.length) {
      this._config.buttons = DEFAULT_BUTTONS;
    }
    this._signature = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const entities = this._entities();
    // Kids' spelling to-do lists too, so the Spelling tiles follow them live.
    const kidSel = entities.kidProfile ? hass.states[entities.kidProfile] : undefined;
    const lists = (kidSel?.attributes?.profiles || []).map((p) => p.spelling_todo).filter(Boolean);
    const signature = [...Object.values(entities), ...lists]
      .map((id) => {
        const s = hass.states[id];
        return s ? `${id}:${s.state}:${s.last_updated}` : id;
      })
      .join("|");
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  getCardSize() {
    return this._config?.kid_mode ? 5 : 6;
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    this._tick = null;
  }

  connectedCallback() {
    if (!this._tick) this._tick = setInterval(() => this._updateCountdown(), 1000);
  }

  // ---- data ---------------------------------------------------------------

  _entities() {
    const hass = this._hass;
    if (!hass?.entities) return {};
    const found = {};
    const wantDevice = this._config?.device_id;
    for (const entry of Object.values(hass.entities)) {
      if (entry.platform !== "tiny_press") continue;
      if (wantDevice && entry.device_id !== wantDevice) continue;
      const role = ROLES[entry.translation_key];
      if (role && !found[role]) found[role] = entry.entity_id;
      if (!this._deviceId) this._deviceId = entry.device_id;
    }
    return found;
  }

  _configEntryId() {
    const device = this._hass?.devices?.[this._config?.device_id || this._deviceId];
    return device?.config_entries?.[0];
  }

  _stateOf(role) {
    const id = this._entities()[role];
    return id ? this._hass.states[id] : undefined;
  }

  // Who's looking at the card: an admin (prints as anyone, never limited), a
  // kid or adult linked to a profile (sees only their own things), or a
  // shared account (the card's own settings decide).
  _viewer() {
    const user = this._hass?.user;
    const profiles = this._stateOf("kidProfile")?.attributes?.profiles || [];
    const linked = user ? profiles.find((p) => p.ha_user && p.ha_user === user.id) : undefined;
    if (user?.is_admin) return { mode: "admin", profiles, linked };
    if (linked?.kind === "kid") return { mode: "kid", profiles, profile: linked };
    if (linked?.kind === "adult") return { mode: "adult", profiles, profile: linked };
    return { mode: "shared", profiles };
  }

  _kidMode() {
    const viewer = this._viewer();
    if (viewer.mode === "kid") return true;
    if (viewer.mode === "admin" || viewer.mode === "adult") return false;
    return !!this._config.kid_mode;
  }

  // Parents (admins, linked adults, or a card set to ignore limits) aren't limited.
  _parent() {
    const mode = this._viewer().mode;
    return mode === "admin" || mode === "adult" || !!this._config.ignore_limits;
  }

  // The profile prints are for: the linked kid or adult, or the admin's pick.
  _asProfile() {
    const viewer = this._viewer();
    if (viewer.mode === "kid" || viewer.mode === "adult") return viewer.profile;
    if (viewer.mode === "admin") {
      const pick = viewer.profiles.find((p) => p.id === this._state.as);
      if (pick) return pick;
      if (viewer.linked) return viewer.linked;
      const active = this._stateOf("kidProfile")?.state;
      return viewer.profiles.find((p) => p.name === active && p.kind === "kid") || viewer.profiles[0];
    }
    return undefined;
  }

  // The kid whose limits and story to show.
  _kidShown() {
    const p = this._asProfile();
    return p && p.kind === "kid" ? p : undefined;
  }

  _limits() {
    const s = this._stateOf("printsLeft");
    if (!s || !s.attributes.enabled) return { enabled: false };
    const kid = this._kidShown();
    const a = (kid && s.attributes.kids && s.attributes.kids[kid.id]) || s.attributes;
    const left = kid && s.attributes.kids && s.attributes.kids[kid.id] ? a.prints_left : s.state;
    const next = a.next_print_at ? new Date(a.next_print_at) : null;
    const since = a.blocked_since ? new Date(a.blocked_since) : null;
    return {
      enabled: true,
      left: Number(left),
      next,
      since,
      reason: a.blocked_reason,
      waiting: next && next.getTime() > Date.now(),
    };
  }

  _blocked() {
    if (this._parent()) return false;
    const limits = this._limits();
    return limits.enabled && limits.waiting;
  }

  // ---- actions ------------------------------------------------------------

  async _call(service, data, wantResponse) {
    const entryId = this._configEntryId();
    const payload = { ...data };
    if (entryId) payload.config_entry_id = entryId;
    return this._hass.callService("tiny_press", service, payload, undefined, false, wantResponse);
  }

  _flash(message, tone) {
    this._state.message = message;
    this._state.tone = tone;
    this._render();
    clearTimeout(this._flashTimer);
    this._flashTimer = setTimeout(() => {
      this._state.message = null;
      this._render();
    }, 6000);
  }

  async _run(fn, doneText) {
    if (this._state.busy) return;
    this._state.busy = true;
    this._render();
    try {
      const result = await fn();
      if (doneText) this._flash(typeof doneText === "function" ? doneText(result) : doneText, "ok");
    } catch (err) {
      this._flash(err?.message || "Something went wrong. Please try again.", "bad");
    } finally {
      this._state.busy = false;
      this._render();
    }
  }

  _printData(type, seed) {
    const data = { type };
    if (seed !== undefined) data.seed = seed;
    return this._who(data);
  }

  // Add who it's for, and skip limits for parents.
  _who(data) {
    const p = this._asProfile();
    if (p) data.profile = p.id;
    if (this._parent()) data.ignore_limits = true;
    return data;
  }

  _print(type, seed) {
    const label = PRINTS[type]?.label || type;
    const service = PRINTS[type]?.service;
    this._run(
      async () => {
        let data;
        if (service === "print_morning_slip") {
          // Kid-mode cards may print one morning slip a day.
          data = this._kidMode() ? { kid_mode: true } : {};
        } else if (service) {
          data = this._who({});
        } else {
          data = this._printData(type, seed);
        }
        const res = await this._call(service || "print", data, true);
        this._state.preview = null;
        return res?.response;
      },
      (r) => (r?.print_id ? `Printing ${label.toLowerCase()} #${r.print_id}` : `Printing ${label.toLowerCase()}`)
    );
  }

  _preview(type) {
    this._run(async () => {
      const data = { type };
      const p = this._asProfile();
      if (p) data.profile = p.id;
      const res = await this._call("preview", data, true);
      this._state.preview = res?.response;
      this._state.previewType = type;
    });
  }

  _history(index) {
    const item = (this._config.history || [])[index];
    if (!item) return;
    const data = { entity_id: item.entities || item.entity };
    if (item.days) data.days = Number(item.days);
    else data.hours = Number(item.hours || 24);
    if (item.style) data.style = item.style;
    if (item.tall) data.tall = true;
    if (item.grid) data.grid = true;
    if (item.title || item.name) data.title = item.title || item.name;
    this._run(() => this._call("print_history", data, true), `Printing ${item.name || "history"}`);
  }

  _historyHtml() {
    const items = Array.isArray(this._config.history) ? this._config.history : [];
    if (this._kidMode() || !items.length) return "";
    const busy = this._state.busy ? "disabled" : "";
    return `<div class="row-label">History</div><div class="history">${items
      .map((item, i) => {
        const span = item.days ? `${item.days} d` : `${item.hours || 24} h`;
        return `<button class="chipbtn" data-history="${i}" ${busy}><ha-icon icon="${esc(
          item.icon || "mdi:chart-line"
        )}"></ha-icon>${esc(item.name || item.entity || "History")} · ${esc(span)}</button>`;
      })
      .join("")}</div>`;
  }

  _feed(index) {
    const item = (this._config.feeds || [])[index];
    if (!item) return;
    const data = { qr: Boolean(item.qr) };
    if (item.feed) data.feed = String(item.feed);
    if (item.items) data.items = Number(item.items);
    this._run(() => this._call("print_feed", data, true), `Printing ${item.name || item.feed || "the feed"}`);
  }

  _feedsHtml() {
    const items = Array.isArray(this._config.feeds) ? this._config.feeds : [];
    if (this._kidMode() || !items.length) return "";
    const busy = this._state.busy ? "disabled" : "";
    return `<div class="row-label">Feeds</div><div class="history">${items
      .map(
        (item, i) =>
          `<button class="chipbtn" data-feed="${i}" ${busy}><ha-icon icon="${esc(
            item.icon || "mdi:rss"
          )}"></ha-icon>${esc(item.name || item.feed || "Feed")}</button>`
      )
      .join("")}</div>`;
  }

  _answers() {
    this._run(() => this._call("print_answers", {}, true), "Printing the answers");
  }

  _selectOption(role, option) {
    const id = this._entities()[role];
    if (!id) return;
    this._hass.callService("select", "select_option", { entity_id: id, option });
  }

  _press(type) {
    // Stories can't be previewed (each one is freshly written).
    if (this._config.show_preview && !PRINTS[type]?.service) this._preview(type);
    else this._print(type);
  }

  // Hold-to-print (kid mode): press and hold; letting go early cancels.
  _holdStart(button, action) {
    this._holdCancel();
    const ms = Number(this._config.hold_ms) || 800;
    button.style.setProperty("--hold-ms", `${ms}ms`);
    button.classList.add("holding");
    this._hold = { button, timer: setTimeout(() => { this._holdCancel(); action(); }, ms) };
  }

  _holdCancel() {
    if (!this._hold) return;
    clearTimeout(this._hold.timer);
    this._hold.button.classList.remove("holding");
    this._hold = null;
  }

  // ---- rendering ------------------------------------------------------------

  _updateCountdown() {
    const el = this.shadowRoot.querySelector("[data-countdown]");
    const limits = this._limits();
    if (!limits.enabled) return;
    if (!limits.waiting) {
      if (el || this._wasWaiting) {
        this._wasWaiting = false;
        this._render();
      }
      return;
    }
    this._wasWaiting = true;
    if (el) el.textContent = this._countdownText(limits);
    const bar = this.shadowRoot.querySelector("[data-wait-bar]");
    if (bar) bar.style.width = `${this._waitProgress(limits)}%`;
  }

  // How far through the wait we are, 0-100 (for the kid-mode time bar).
  _waitProgress(limits) {
    if (!limits.next || !limits.since) return 0;
    const total = limits.next.getTime() - limits.since.getTime();
    if (total <= 0) return 100;
    const done = Date.now() - limits.since.getTime();
    return Math.max(0, Math.min(100, (done / total) * 100));
  }

  _waitHtml(limits) {
    const pct = this._waitProgress(limits).toFixed(1);
    return `<div class="wait" role="timer" aria-live="off">
      <div class="wait-bar" data-wait-bar style="width:${pct}%"></div>
      <div class="wait-text"><ha-icon icon="mdi:timer-sand"></ha-icon><span data-countdown>${esc(this._countdownText(limits))}</span></div>
    </div>`;
  }

  // The Next chapter tile: the story in progress, or greyed out without one.
  _chapterInfo() {
    const s = this._stateOf("nextChapter");
    if (!s) return { known: false };
    const kid = this._kidShown();
    const mine = kid ? (s.attributes.stories || {})[kid.id] || {} : s.attributes;
    const story = mine.story;
    return {
      known: true,
      story,
      next: story ? Number(mine.chapter || 0) + 1 : null,
      profile: kid ? kid.name : s.attributes.profile,
    };
  }

  _tileLabel(t) {
    if (t === "morning_slip" && this._morningDone()) {
      return `${esc(PRINTS[t].label)}<small>Printed today</small>`;
    }
    if (t === "spelling" || t === "spelling_search") {
      const sp = this._spellingInfo();
      return sp.known ? `${esc(PRINTS[t].label)}<small>${esc(sp.note)}</small>` : esc(PRINTS[t].label);
    }
    if (t !== "next_chapter") return esc(PRINTS[t].label);
    const info = this._chapterInfo();
    if (!info.known) return esc(PRINTS[t].label);
    if (!info.story) return `No story yet<small>Start a Bedtime story</small>`;
    return `Chapter ${info.next}<small>${esc(info.story)}</small>`;
  }

  // Spelling tiles: the kid's spelling to-do list, greyed out when it has no
  // unchecked words (a to-do entity's state is its count of open items).
  _spellingInfo() {
    let kid = this._kidShown();
    if (!kid && this._viewer().mode === "shared") {
      const active = this._stateOf("kidProfile")?.state;
      kid = this._viewer().profiles.find((p) => p.kind === "kid" && p.name === active);
    }
    if (!kid) return { known: false };
    if (!kid.spelling_todo) return { known: true, words: 0, note: "No spelling list" };
    const words = Number(this._hass?.states?.[kid.spelling_todo]?.state);
    if (!Number.isFinite(words)) return { known: true, words: 0, note: "List unavailable" };
    return { known: true, words, note: words ? `${words} word${words === 1 ? "" : "s"}` : "List is empty" };
  }

  _morningDone() {
    return !!this._stateOf("morningSlip")?.attributes?.printed_today;
  }

  _tileDisabled(t) {
    if (t === "morning_slip") return this._morningDone();
    if (t === "spelling" || t === "spelling_search") {
      const sp = this._spellingInfo();
      return sp.known && !sp.words;
    }
    if (t !== "next_chapter") return false;
    const info = this._chapterInfo();
    return info.known && !info.story;
  }

  _countdownText(limits) {
    if (limits.reason === "day" || limits.reason === "paper") return "That's enough printing for today!";
    const secs = Math.max(0, Math.round((limits.next.getTime() - Date.now()) / 1000));
    const m = Math.floor(secs / 60);
    const s = String(secs % 60).padStart(2, "0");
    return `Next print in ${m}:${s}`;
  }

  _statusHtml() {
    const online = this._stateOf("online");
    const paper = this._stateOf("paper");
    const used = this._stateOf("paperUsed");
    const limits = this._limits();
    const p = PAPER[paper?.state] || PAPER.offline;
    const chips = [];
    chips.push(`<span class="chip ${online?.state === "on" ? "ok" : "bad"}"><span class="dot"></span>${online?.state === "on" ? "Online" : "Offline"}</span>`);
    chips.push(`<span class="chip ${p.tone}"><ha-icon icon="${p.icon}"></ha-icon>${p.label}</span>`);
    if (limits.enabled && !this._parent()) {
      // Yellow for the last three prints, red for the last one (or none left).
      const tone = limits.left <= 1 ? "last" : limits.left <= 3 ? "few" : "";
      chips.push(`<span class="chip left ${tone}"><ha-icon icon="mdi:timer-sand"></ha-icon>${esc(limits.left)} left today</span>`);
    }
    if (!this._kidMode() && used && used.state !== "unknown") {
      const metres = (Number(used.state) / 1000).toFixed(1);
      chips.push(`<span class="chip muted"><ha-icon icon="mdi:ruler"></ha-icon>${metres} m used</span>`);
    }
    return `<div class="status">${chips.join("")}</div>`;
  }

  // Whose card this is: the linked person, the admin's pick, or the active kid.
  _headerName() {
    if (!this._hass) return "";
    const p = this._asProfile();
    const name = p ? p.name : this._stateOf("kidProfile")?.state;
    if (!name || name === "unknown" || name === "unavailable") return "";
    return `<span class="who"><ha-icon icon="mdi:account"></ha-icon>${esc(name)}</span>`;
  }

  // Admins: print as any kid or adult (never counted against limits).
  _asHtml() {
    const viewer = this._viewer();
    if (viewer.mode !== "admin" || viewer.profiles.length < 2) return "";
    const current = this._asProfile();
    const kids = viewer.profiles.filter((p) => p.kind === "kid");
    const adults = viewer.profiles.filter((p) => p.kind === "adult");
    const btn = (p) =>
      `<button class="segbtn ${current && p.id === current.id ? "on" : ""}" data-as="${esc(p.id)}">${esc(p.name)}</button>`;
    return `<div class="row as"><span class="row-label">Print as</span><div class="seg">${kids
      .map(btn)
      .join("")}${kids.length && adults.length ? '<span class="seg-gap"></span>' : ""}${adults.map(btn).join("")}</div></div>`;
  }

  _chipsHtml(role, label) {
    const s = this._stateOf(role);
    const options = s?.attributes?.options || [];
    if (options.length < 2) return "";
    return `<div class="row"><span class="row-label">${esc(label)}</span><div class="seg">${options
      .map(
        (o) =>
          `<button class="segbtn ${o === s.state ? "on" : ""}" data-select="${role}" data-option="${esc(o)}">${esc(o)}</button>`
      )
      .join("")}</div></div>`;
  }

  _lastPrintHtml() {
    const last = this._stateOf("lastPrint");
    if (!last || last.state === "unknown" || last.state === "unavailable") return "";
    const label = PRINTS[last.state]?.label || last.state.replace(/_/g, " ");
    const id = last.attributes.print_id ? ` #${esc(last.attributes.print_id)}` : "";
    const when = last.attributes.printed_at ? new Date(last.attributes.printed_at) : null;
    const time = when ? when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
    const answers = this._kidMode()
      ? ""
      : `<button class="link" data-action="answers"><ha-icon icon="mdi:check-decagram-outline"></ha-icon>Answers</button>`;
    return `<div class="last"><span>Last: ${esc(label)}${id} · ${esc(time)}</span>${answers}</div>`;
  }

  _previewHtml() {
    const pv = this._state.preview;
    if (!pv) return "";
    const kid = this._kidMode();
    const label = PRINTS[this._state.previewType]?.label || "print";
    return `<div class="preview">
      <div class="paper"><img alt="Preview of the ${esc(label)}" src="${esc(pv.image)}"></div>
      <div class="pv-meta">${esc(label)} #${esc(pv.print_id)} · about ${Math.round(pv.length_mm / 10)} cm</div>
      <div class="pv-actions">
        <button class="ghost" data-action="cancel">Cancel</button>
        <button class="ghost" data-action="shuffle"><ha-icon icon="mdi:shuffle-variant"></ha-icon>Shuffle</button>
        <button class="primary ${kid ? "hold" : ""}" data-action="print-preview" ${this._state.busy || this._blocked() ? "disabled" : ""}>
          <span class="fill"></span><ha-icon icon="mdi:printer-pos"></ha-icon>${kid ? "Hold to print" : "Print"}
        </button>
      </div>
    </div>`;
  }

  _render() {
    if (!this._config) return;
    const hass = this._hass;
    const kid = this._kidMode();
    const entities = hass ? this._entities() : {};
    const missing = hass && !Object.keys(entities).length;
    const limits = hass ? this._limits() : { enabled: false };
    const blocked = hass ? this._blocked() : false;
    const disabled = this._state.busy || blocked || missing;
    // Kid mode never shows adult puzzles.
    const buttons = this._config.buttons.filter((t) => PRINTS[t] && !(kid && PRINTS[t].adult));
    const hasAdult = buttons.some((t) => PRINTS[t].adult);

    const body = missing
      ? `<div class="empty">No Tiny Press printer found. Add the Tiny Press integration first.</div>`
      : `
        ${this._statusHtml()}
        ${blocked ? this._waitHtml(limits) : ""}
        ${this._asHtml()}
        ${kid || this._viewer().mode === "admin" ? "" : this._chipsHtml("kidProfile", "Kid")}
        ${kid ? "" : this._chipsHtml("mazeDifficulty", "Maze")}
        ${kid || !buttons.includes("story") ? "" : this._chipsHtml("storyLength", "Story")}
        ${kid || !hasAdult || this._viewer().mode === "admin" ? "" : this._chipsHtml("adultProfile", "Adult")}
        ${kid || !hasAdult ? "" : this._chipsHtml("sudokuDifficulty", "Sudoku")}
        ${this._state.preview ? this._previewHtml() : `
          <div class="grid ${kid ? "kid" : ""}">
            ${buttons
              .map(
                (t) => `<button class="tile ${kid && !this._config.show_preview ? "hold" : ""}" data-print="${t}" ${disabled || this._tileDisabled(t) ? "disabled" : ""}>
                  <span class="fill"></span>
                  <ha-icon icon="${PRINTS[t].icon}"></ha-icon>
                  <span class="label">${this._tileLabel(t)}</span>
                </button>`
              )
              .join("")}
          </div>`}
        ${this._state.preview ? "" : this._historyHtml()}
        ${this._state.preview ? "" : this._feedsHtml()}
        ${this._state.busy ? `<div class="notice">Working on it…</div>` : ""}
        ${this._state.message ? `<div class="notice ${this._state.tone}">${esc(this._state.message)}</div>` : ""}
        ${this._lastPrintHtml()}`;

    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <ha-card>
        <div class="header"><ha-icon icon="mdi:printer-pos-outline"></ha-icon><span>${esc(this._config.title)}</span>${this._headerName()}</div>
        <div class="content">${body}</div>
      </ha-card>`;
    this._bind();
  }

  _bind() {
    const root = this.shadowRoot;
    const kid = this._kidMode();
    root.querySelectorAll("[data-print]").forEach((b) => {
      const type = b.dataset.print;
      if (kid && !this._config.show_preview) {
        b.addEventListener("pointerdown", (e) => { e.preventDefault(); this._holdStart(b, () => this._press(type)); });
        ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => b.addEventListener(ev, () => this._holdCancel()));
        b.addEventListener("contextmenu", (e) => e.preventDefault());
      } else {
        b.addEventListener("click", () => this._press(type));
      }
    });
    root.querySelectorAll("[data-select]").forEach((b) =>
      b.addEventListener("click", () => this._selectOption(b.dataset.select, b.dataset.option))
    );
    root.querySelectorAll("[data-as]").forEach((b) =>
      b.addEventListener("click", () => { this._state.as = b.dataset.as; this._render(); })
    );
    const act = (name, fn) => root.querySelectorAll(`[data-action="${name}"]`).forEach((b) => b.addEventListener("click", fn));
    act("answers", () => this._answers());
    root.querySelectorAll("[data-history]").forEach((b) =>
      b.addEventListener("click", () => this._history(Number(b.dataset.history)))
    );
    root.querySelectorAll("[data-feed]").forEach((b) =>
      b.addEventListener("click", () => this._feed(Number(b.dataset.feed)))
    );
    act("cancel", () => { this._state.preview = null; this._render(); });
    act("shuffle", () => this._preview(this._state.previewType));
    const printPreview = root.querySelector('[data-action="print-preview"]');
    if (printPreview) {
      const go = () => this._print(this._state.previewType, this._state.preview.seed);
      if (kid) {
        printPreview.addEventListener("pointerdown", (e) => { e.preventDefault(); this._holdStart(printPreview, go); });
        ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => printPreview.addEventListener(ev, () => this._holdCancel()));
      } else {
        printPreview.addEventListener("click", go);
      }
    }
  }
}

const STYLES = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .header { display: flex; align-items: center; gap: 8px; padding: 16px 16px 4px; font-size: 1.25rem; font-weight: 500; color: var(--primary-text-color); }
  .header ha-icon { color: var(--primary-color); }
  .content { padding: 8px 16px 16px; display: flex; flex-direction: column; gap: 12px; }
  .status { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 999px; font-size: 0.8rem;
    background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); color: var(--primary-text-color); }
  .chip ha-icon { --mdc-icon-size: 16px; }
  .chip.ok { background: color-mix(in srgb, var(--success-color, #43a047) 18%, transparent); }
  .chip.warn { background: color-mix(in srgb, var(--warning-color, #ffa000) 22%, transparent); }
  .chip.bad { background: color-mix(in srgb, var(--error-color, #db4437) 20%, transparent); }
  .chip.left.few { background: #ffd600; color: #000; font-weight: 700; }
  .chip.left.last { background: #d50000; color: #fff; font-weight: 700; }
  .chip.left.few ha-icon, .chip.left.last ha-icon { color: inherit; }
  .header .who { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; font-size: 0.95rem;
    font-weight: 600; padding: 3px 10px; border-radius: 999px;
    background: color-mix(in srgb, var(--primary-color, #03a9f4) 14%, transparent); }
  .header .who ha-icon { --mdc-icon-size: 16px; }
  .chip.muted { color: var(--secondary-text-color); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; opacity: 0.7; }
  .chip.ok .dot { background: var(--success-color, #43a047); opacity: 1; }
  .chip.bad .dot { background: var(--error-color, #db4437); opacity: 1; }
  .row { display: flex; align-items: center; gap: 10px; }
  .row-label { min-width: 40px; color: var(--secondary-text-color); font-size: 0.85rem; }
  .seg { display: flex; flex-wrap: wrap; gap: 6px; }
  .segbtn { border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); border-radius: 999px;
    padding: 4px 12px; font: inherit; font-size: 0.85rem; cursor: pointer; text-transform: capitalize; }
  .segbtn.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; }
  .grid.kid { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
  .tile, .primary { position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 6px; min-height: 84px; border-radius: 16px; border: none; cursor: pointer; font: inherit; font-weight: 500;
    background: color-mix(in srgb, var(--primary-color) 14%, var(--card-background-color)); color: var(--primary-text-color);
    -webkit-user-select: none; user-select: none; touch-action: manipulation; }
  .grid.kid .tile { min-height: 110px; font-size: 1.05rem; }
  .tile ha-icon { --mdc-icon-size: 34px; color: var(--primary-color); position: relative; }
  .grid.kid .tile ha-icon { --mdc-icon-size: 44px; }
  .tile span:not(.fill), .primary span:not(.fill) { position: relative; }
  .tile:disabled, .primary:disabled { opacity: 0.45; cursor: default; }
  .tile .label { max-width: 100%; }
  .tile .label small { display: block; font-size: 0.75rem; opacity: 0.8; margin-top: 2px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  .wait { position: relative; height: 40px; border-radius: 20px; overflow: hidden;
    background: var(--secondary-background-color, rgba(127,127,127,0.15)); margin: 4px 0 8px; }
  .wait-text { position: relative; height: 100%; display: flex; align-items: center; justify-content: center;
    gap: 6px; font-size: 1rem; font-weight: 600; font-variant-numeric: tabular-nums;
    color: var(--primary-text-color, #212121); }
  .wait-text ha-icon { --mdc-icon-size: 20px; }
  .wait-bar { position: absolute; inset: 0 auto 0 0; border-radius: 20px; transition: width 1s linear;
    background: color-mix(in srgb, var(--primary-color, #03a9f4) 45%, transparent); }
  .seg-gap { display: inline-block; width: 10px; }
  .tile:not(:disabled):active { transform: scale(0.97); }
  .fill { position: absolute; inset: 0; width: 0; background: color-mix(in srgb, var(--primary-color) 35%, transparent); }
  .holding .fill { width: 100%; transition: width var(--hold-ms, 800ms) linear; }
  .notice { padding: 8px 12px; border-radius: 10px; font-size: 0.9rem; text-align: center;
    background: color-mix(in srgb, var(--secondary-text-color) 10%, transparent); color: var(--primary-text-color); }
  .notice.ok { background: color-mix(in srgb, var(--success-color, #43a047) 16%, transparent); }
  .notice.bad { background: color-mix(in srgb, var(--error-color, #db4437) 16%, transparent); }
  .last { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 0.85rem; color: var(--secondary-text-color); }
  .link { display: inline-flex; align-items: center; gap: 4px; border: none; background: none; color: var(--primary-color); font: inherit; cursor: pointer; }
  .link ha-icon { --mdc-icon-size: 18px; }
  .preview { display: flex; flex-direction: column; gap: 10px; align-items: center; }
  .paper { background: #fff; border-radius: 6px; padding: 8px; max-height: 420px; overflow-y: auto; box-shadow: 0 1px 4px rgba(0,0,0,0.25); width: min(100%, 300px); }
  .paper img { width: 100%; display: block; image-rendering: pixelated; }
  .pv-meta { font-size: 0.85rem; color: var(--secondary-text-color); }
  .pv-actions { display: flex; gap: 8px; width: 100%; }
  .pv-actions .primary { flex: 1; flex-direction: row; min-height: 48px; background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .pv-actions .primary ha-icon { color: inherit; }
  .ghost { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--divider-color); background: none; border-radius: 12px;
    padding: 0 14px; min-height: 48px; color: var(--primary-text-color); font: inherit; cursor: pointer; }
  .ghost ha-icon { --mdc-icon-size: 18px; }
  .empty { color: var(--secondary-text-color); padding: 12px 0; }
  .history { display: flex; flex-wrap: wrap; gap: 8px; }
  .chipbtn { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--divider-color); background: none;
    border-radius: 999px; padding: 6px 12px; font: inherit; font-size: 0.9rem; color: var(--primary-text-color); cursor: pointer; }
  .chipbtn ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
  .chipbtn:disabled { opacity: 0.45; }
`;

if (!customElements.get("tiny-press-card")) {
  customElements.define("tiny-press-card", TinyPressCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "tiny-press-card",
    name: "Tiny Press",
    description: "Print mazes, puzzles and jokes on your receipt printer. Kid mode adds hold-to-print and shows the print limits.",
    preview: true,
    documentationURL: "https://github.com/thermitehash/ha-tiny-press#dashboard-card",
  });
  console.info(`%c TINY-PRESS-CARD %c ${CARD_VERSION} `, "background:#F28C28;color:#fff;font-weight:700", "");
}
