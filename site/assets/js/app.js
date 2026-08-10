/* ClinProc · static-site frontend logic
   Loads JSON data -> builds Lunr index -> filter/search/sort/paginate.
   Pure client-side, no server dependency.

   v7 — two-view layout (Home + Browse), HF-style conference tabs,
   reliable multi-strategy search, English UI, pastel card tints. */

(() => {
  "use strict";

  const PER_PAGE = 30;
  const $ = (s) => document.querySelector(s);
  const THEME_KEY = "clinproc-theme";

  // ---- English conference blurbs (shown on home cards) ----
  const CONF_DESC = {
    "sugi": "SAS Users Group International — the legacy SAS user meeting (1976–2006), archived by SAS.",
    "pharmasug-us": "Pharmaceutical-industry SAS users group, US chapter. CDISC- and clinical-trial-focused.",
    "sgf": "SAS Global Forum — SAS's flagship worldwide conference (2007–2021), succeeded by SAS Innovate.",
    "phuse-eu": "PHUSE EU Connect — applied clinical research, data standards and statistical programming.",
    "phuse-us": "PHUSE US Connect — the North-American PHUSE workshop series.",
    "phuse-apac": "PHUSE APAC Connect — the Asia-Pacific edition of the PHUSE conference.",
    "r-pharma": "R/Pharma — R for pharmaceutical statistics and clinical programming.",
    "pharmasug-cn": "PharmaSUG China — regional proceedings, Chinese and English.",
    "phuse-css": "FDA/PHUSE Clinical Study Submission workshop — regulatory submission standards.",
    "mwsug": "MidWest SAS Users Group — regional SAS conference.",
    "sas-innovate": "SAS Innovate (2025–) — successor to SAS Global Forum; sessions hosted on GitHub.",
    "pharmasug-jp": "PharmaSUG Japan — regional proceedings, Japanese and English.",
    "wuss": "Western Users Group for SAS.",
    "sesug": "SouthEast SAS Users Group.",
    "nesug": "Northeast SAS Users Group.",
    "scsug": "SouthCentral SAS Users Group.",
    "seugi": "SAS European Users Group International.",
    "basug": "Boston Area SAS Users Group.",
    "pnwsug": "Pacific Northwest SAS Users Group.",
    "psi": "PSI — statistics in the pharmaceutical industry (UK/EU).",
    "posit-conf": "posit::conf — Posit's annual R & open-source data science conference.",
    "sas-explore": "SAS Explore — SAS analytics & AI event.",
    "pharmarug-cn": "PharmaRUG China — R users group for the pharmaceutical industry.",
    "views": "VIEWS — European data-visualisation conference.",
  };

  // ---- state ----
  const state = {
    papers: [],
    confs: [],
    idx: null,
    filters: { conf: new Set(), region: new Set(), year: new Set(), section: new Set() },
    query: "",
    sort: "year-desc",
    page: 1,
    ready: false,
    view: "home",
  };

  // ---- utils ----
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  // only allow http(s) links from data; everything else degrades to "#"
  const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "#";
  const toast = (msg) => {
    const t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (t.hidden = true), 2600);
  };
  const haystack = (p) => p._hay || (p._hay = [
    p.title, (p.authors || []).join(" "), p.section_name, p.conference_name,
    p.paper_code, p.abstract,
  ].join(" ").toLowerCase());

  function animateValue(el, end, duration = 900) {
    if (typeof end !== "number" || isNaN(end) || end === 0) {
      el.textContent = typeof end === "number" ? end.toLocaleString() : end;
      return;
    }
    const startTime = performance.now();
    function step(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.floor(end * eased).toLocaleString();
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = end.toLocaleString();
    }
    requestAnimationFrame(step);
  }

  // ---- theme ----
  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.setAttribute("data-theme", saved || (prefersDark ? "dark" : "light"));
  }
  function toggleTheme() {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(THEME_KEY, next);
  }

  // ---- data ----
  function showSkeleton() {
    $("#results-list").innerHTML = Array(8).fill('<div class="skeleton-card"></div>').join("");
  }

  async function load() {
    try {
      const [pRes, cRes] = await Promise.all([
        fetch("data/papers.json"),
        fetch("data/conferences.json"),
      ]);
      if (!pRes.ok) throw new Error("failed to load papers.json");
      state.papers = await pRes.json();
      state.confs = cRes.ok ? await cRes.json() : [];
      // stable tint per conference (index in conferences.json)
      state.confs.forEach((c, i) => { c.tint = i % 8; });
      buildIndex();
      renderStats();
      renderTrending();
      renderConfGrid();
      state.ready = true;
      route();
    } catch (e) {
      console.error(e);
      $("#results-count").innerHTML =
        `<span style="color:var(--danger)">Data failed to load: ${esc(e.message)}. Preview via a local HTTP server — file:// cannot fetch JSON.</span>`;
      $("#results-list").innerHTML = "";
      toast("Data failed to load");
    }
  }

  // ---- Lunr index ----
  function buildIndex() {
    if (typeof lunr === "undefined") { toast("Search engine unavailable — filters only"); return; }
    state.idx = lunr(function () {
      this.ref("id");
      this.field("title", { boost: 4 });
      this.field("authors", { boost: 3 });
      this.field("section_name", { boost: 2 });
      this.field("conference_name", { boost: 2 });
      this.field("paper_code", { boost: 2 });
      this.field("abstract");
      for (const p of state.papers) {
        this.add({
          id: p.id,
          title: p.title || "",
          authors: (p.authors || []).join("; "),
          section_name: p.section_name || "",
          conference_name: p.conference_name || "",
          paper_code: (p.paper_code || "").replace(/[^\w]/g, " "),
          abstract: p.abstract || "",
        });
      }
    });
  }

  // ---- search: AND-terms -> OR-terms -> substring fallback, plus code/phrase boosts ----
  function doSearch(q, base) {
    const raw = q.toLowerCase().split(/\s+/).map((t) => t.trim()).filter(Boolean);
    if (!raw.length) return { list: base, mode: null, scores: null };
    const full = raw.join(" ");

    const phraseHits = new Set();
    const codeHits = new Set();
    const codeToks = raw.map((t) => t.replace(/[^\w-]/g, "")).filter((t) => t.length >= 4 && /\d/.test(t) && /[a-z]/.test(t));
    for (const p of base) {
      if (haystack(p).includes(full)) phraseHits.add(p.id);
      const code = (p.paper_code || "").toLowerCase();
      if (code && codeToks.some((t) => code.includes(t))) codeHits.add(p.id);
    }

    let scores = null, mode = "all-terms";
    if (state.idx) {
      // split "AP-011:" into [ap, 011] so code fragments reach the index
      const terms = [];
      for (const t of raw) for (const w of t.replace(/[^\w]/g, " ").split(/\s+/)) if (w.length >= 2) terms.push(w);
      if (terms.length) {
        try {
          const r = state.idx.search(terms.map((t) => `+${t}*`).join(" ")); // every term must match
          if (r.length) scores = new Map(r.map((x) => [x.ref, x.score]));
        } catch { /* fall through */ }
        if (!scores) {
          try {
            const r = state.idx.search(terms.map((t) => `${t}*`).join(" ")); // any term
            if (r.length) { scores = new Map(r.map((x) => [x.ref, x.score])); mode = "any-term"; }
          } catch { /* fall through */ }
        }
      }
    }

    let list;
    if (scores) {
      for (const p of base) if (codeHits.has(p.id) && !scores.has(p.id)) scores.set(p.id, 0.5);
      list = base.filter((p) => scores.has(p.id));
    } else {
      mode = "keywords";
      list = base.filter((p) => raw.every((t) => haystack(p).includes(t)));
      if (!list.length) { // relax: any term
        list = base.filter((p) => raw.some((t) => haystack(p).includes(t)));
        mode = "keywords-any";
      }
    }
    return { list, mode, scores, phraseHits, codeHits };
  }

  // ---- stats / trending ----
  function renderStats() {
    const ps = state.papers;
    const years = ps.map((p) => p.year).filter(Boolean);
    animateValue($("#stat-papers"), ps.length);
    animateValue($("#stat-confs"), new Set(ps.map((p) => p.conference)).size);
    $("#stat-years").textContent = years.length ? `${Math.min(...years)}–${Math.max(...years)}` : "—";
    const latest = ps.map((p) => p.added_at || "").filter(Boolean).sort().pop();
    $("#stat-updated").textContent = latest ? latest.slice(0, 10) : "—";
  }

  function renderTrending() {
    const box = $("#trending-list");
    if (!box) return;
    const now = Date.now();
    const latest = [...state.papers]
      .filter((p) => p.added_at)
      .sort((a, b) => b.added_at.localeCompare(a.added_at))
      .slice(0, 6);
    if (!latest.length) { box.closest(".trending").style.display = "none"; return; }
    $("#trending-sub").textContent = `last updated ${latest[0].added_at.slice(0, 10)}`;
    box.innerHTML = latest.map((p, i) => {
      const isNew = now - Date.parse(p.added_at) < 14 * 864e5;
      const href = safeUrl(p.pdf_url || p.source_url);
      const tint = confTint(p.conference);
      return `<a class="trend-card tint-${tint}" href="${esc(href)}" target="_blank" rel="noopener">
        <span class="trend-rank">${String(i + 1).padStart(2, "0")}</span>
        <span class="trend-conf">${esc(p.conference_name)} ${p.year || ""}</span>
        <span class="trend-title">${esc(p.title)}</span>
        <span class="trend-meta">
          ${isNew ? `<span class="trend-new">NEW</span>` : ""}
          ${p.authors && p.authors.length ? esc(p.authors[0]) + (p.authors.length > 1 ? " et al." : "") : ""}
          ${p.pdf_url ? "· PDF" : ""}
        </span>
      </a>`;
    }).join("");
  }

  const confTint = (code) => {
    const c = state.confs.find((x) => x.code === code);
    return c ? c.tint : 0;
  };

  // ---- home: conference cards ----
  function renderConfGrid() {
    const grid = $("#conf-grid");
    grid.innerHTML = state.confs.map((c) => {
      const yr = c.year_min && c.year_max ? `${c.year_min}–${c.year_max}` : (c.year_min || "—");
      const status = c.implemented
        ? `<div class="conf-status ready">● indexed</div>`
        : `<div class="conf-status todo">○ planned</div>`;
      return `<div class="conf-card tint-${c.tint} ${c.implemented ? "" : "disabled"}" data-conf="${esc(c.code)}">
        <div class="conf-name">${esc(c.name)}</div>
        ${status}
        <div class="conf-desc">${esc(CONF_DESC[c.code] || "Regional user-group proceedings.")}</div>
        <div class="conf-region">${esc(c.region)} · ${esc(c.lang)}</div>
        <div class="conf-stat"><span><b>${c.count.toLocaleString()}</b> papers</span><span>${yr}</span></div>
      </div>`;
    }).join("");
    grid.querySelectorAll(".conf-card").forEach((card) => {
      card.addEventListener("click", () => {
        if (card.classList.contains("disabled")) return;
        location.hash = `#/browse/${card.dataset.conf}`;
      });
    });
  }

  // ---- browse: conference tab strip (HF-style secondary nav) ----
  function renderTabs() {
    const bar = $("#conf-tabs");
    const items = [{ key: "", label: "All conferences", count: state.papers.length }]
      .concat(state.confs.filter((c) => c.implemented).map((c) => ({
        key: c.code, label: c.name, count: c.count, tint: c.tint,
      })));
    const active = [...state.filters.conf][0] || "";
    bar.innerHTML = items.map((it) =>
      `<button class="conf-tab ${it.key === active ? "active" : ""} ${it.tint !== undefined ? "tint-" + it.tint : ""}" data-key="${esc(it.key)}">
        ${esc(it.label)}<span class="chip-count">${(it.count || 0).toLocaleString()}</span>
      </button>`).join("");
    bar.querySelectorAll(".conf-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        location.hash = tab.dataset.key ? `#/browse/${tab.dataset.key}` : "#/browse";
      });
    });
  }

  // ---- filters (cascading) ----
  function getFilteredPapers(excludeDim) {
    return state.papers.filter((p) => {
      if (excludeDim !== "conf" && state.filters.conf.size && !state.filters.conf.has(p.conference)) return false;
      if (excludeDim !== "region" && state.filters.region.size && !state.filters.region.has(p.region)) return false;
      if (excludeDim !== "year" && state.filters.year.size && !state.filters.year.has(String(p.year))) return false;
      if (excludeDim !== "section" && state.filters.section.size && !state.filters.section.has(p.section_name)) return false;
      return true;
    });
  }

  function renderFilters() {
    const regionBase = getFilteredPapers("region");
    const regionMap = {};
    for (const p of regionBase) regionMap[p.region || "Other"] = (regionMap[p.region || "Other"] || 0) + 1;
    renderChips("#filter-region", Object.entries(regionMap).map(([k, v]) => ({
      key: k, label: k, count: v,
    })).sort((a, b) => b.count - a.count), state.filters.region);

    const yearBase = getFilteredPapers("year");
    const yearMap = {};
    for (const p of yearBase) if (p.year) yearMap[p.year] = (yearMap[p.year] || 0) + 1;
    renderChips("#filter-year", Object.entries(yearMap).map(([k, v]) => ({
      key: k, label: k, count: v,
    })).sort((a, b) => Number(b.key) - Number(a.key)), state.filters.year);

    const secBase = getFilteredPapers("section");
    const secMap = {};
    for (const p of secBase) if (p.section_name) secMap[p.section_name] = (secMap[p.section_name] || 0) + 1;
    renderChips("#filter-section", Object.entries(secMap).map(([k, v]) => ({
      key: k, label: k, count: v,
    })).sort((a, b) => b.count - a.count), state.filters.section);

    updateFilterGroupCounts();
  }

  function updateFilterGroupCounts() {
    for (const [dim, sel] of [["region", "#filter-region"], ["year", "#filter-year"], ["section", "#filter-section"]]) {
      const group = document.querySelector(sel)?.closest(".filter-group");
      if (!group) continue;
      const count = state.filters[dim].size;
      const badge = group.querySelector(".filter-active-count");
      if (badge) {
        badge.textContent = count > 0 ? count : "";
        badge.style.display = count > 0 ? "" : "none";
      }
      if (count > 0) group.classList.remove("collapsed");
      const constrained = getFilteredPapers(dim).length < state.papers.length && count === 0;
      group.classList.toggle("filter-constrained", constrained);
    }
    renderActiveBar();
  }

  function renderActiveBar() {
    const bar = $("#filter-active-bar");
    if (!bar) return;
    const tags = [];
    const dimLabels = { conf: "Conference", region: "Region", year: "Year", section: "Topic" };
    const nameOf = (dim, key) => dim === "conf"
      ? (state.confs.find((c) => c.code === key)?.name || key) : key;
    for (const [dim, label] of Object.entries(dimLabels)) {
      for (const key of state.filters[dim]) {
        tags.push(`<span class="filter-tag" data-dim="${dim}" data-key="${esc(key)}"><span class="filter-tag-cat">${label}:</span>${esc(nameOf(dim, key))} ×</span>`);
      }
    }
    bar.innerHTML = tags.join("");
    bar.querySelectorAll(".filter-tag").forEach((tag) => {
      tag.addEventListener("click", () => {
        const dim = tag.dataset.dim, key = tag.dataset.key;
        if (dim === "conf") location.hash = "#/browse";
        else { state.filters[dim].delete(key); state.page = 1; renderFilters(); apply(); }
      });
    });
  }

  function renderChips(selector, items, activeSet) {
    const el = $(selector);
    if (!items.length) { el.innerHTML = `<span style="font-size:12px;color:var(--text-faint)">no data</span>`; return; }
    el.innerHTML = items.map((it) => {
      const active = activeSet.has(it.key) ? "active" : "";
      const label = it.label.length > 26 ? it.label.slice(0, 25) + "…" : it.label;
      return `<span class="chip ${active}" data-key="${esc(it.key)}">${esc(label)}<span class="chip-count">${it.count.toLocaleString()}</span></span>`;
    }).join("");
    el.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const k = chip.dataset.key;
        if (activeSet.has(k)) activeSet.delete(k); else activeSet.add(k);
        state.page = 1;
        renderFilters();
        apply();
      });
    });
  }

  // ---- apply: search + filter + sort + paginate ----
  function apply() {
    let list = state.papers;
    let search = null;

    const q = state.query.trim();
    if (q) {
      search = doSearch(q, list);
      list = search.list;
      if (state.sort === "year-desc" || state.sort === "relevance") {
        // searching defaults to relevance ordering
        state.sort = "relevance";
        const sel = $("#sort"); if (sel) sel.value = "relevance";
      }
    }

    list = list.filter((p) => {
      if (state.filters.conf.size && !state.filters.conf.has(p.conference)) return false;
      if (state.filters.region.size && !state.filters.region.has(p.region)) return false;
      if (state.filters.year.size && !state.filters.year.has(String(p.year))) return false;
      if (state.filters.section.size && !state.filters.section.has(p.section_name)) return false;
      return true;
    });

    list = [...list];
    const sort = state.sort;
    if (sort === "relevance" && search && search.scores) {
      list.sort((a, b) => scoreOf(b, search) - scoreOf(a, search));
    } else if (sort === "relevance") {
      list.sort((a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title));
    } else if (sort === "year-desc") {
      list.sort((a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title));
    } else if (sort === "year-asc") {
      list.sort((a, b) => (a.year || 0) - (b.year || 0) || a.title.localeCompare(b.title));
    } else if (sort === "title") {
      list.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
    }

    renderResults(list, q, search);
    updateFilterCount();
  }

  function scoreOf(p, search) {
    let s = search.scores ? (search.scores.get(p.id) || 0) : 0;
    if (search.phraseHits && search.phraseHits.has(p.id)) s += 100;
    if (search.codeHits && search.codeHits.has(p.id)) s += 60;
    // every alphabetic query term present in the title = strong match
    const q = state.query.trim().toLowerCase();
    if ((p.title || "").toLowerCase().includes(q)) s += 40;
    const titleL = (p.title || "").toLowerCase();
    const alpha = q.split(/[^a-z]+/).filter((t) => t.length >= 3);
    if (alpha.length && alpha.every((t) => titleL.includes(t))) s += 30;
    return s;
  }

  function renderResults(list, q, search) {
    const countEl = $("#results-count");
    let label;
    if (q) {
      const modeNote = search && search.mode === "keywords" ? " · keyword match"
        : search && search.mode === "keywords-any" ? " · partial keyword match"
        : search && search.mode === "any-term" ? " · some terms matched" : "";
      label = `<b>${list.length.toLocaleString()}</b> result${list.length === 1 ? "" : "s"} for “${esc(q)}”${modeNote}`;
      if (hasActiveFilters()) label += ` · within current filters`;
    } else {
      label = `<b>${list.length.toLocaleString()}</b> papers${hasActiveFilters() ? ` · filtered from ${state.papers.length.toLocaleString()}` : ""}`;
    }
    countEl.innerHTML = label;

    const pages = Math.ceil(list.length / PER_PAGE) || 1;
    if (state.page > pages) state.page = 1;
    const start = (state.page - 1) * PER_PAGE;
    const slice = list.slice(start, start + PER_PAGE);

    const box = $("#results-list");
    if (!slice.length) {
      box.innerHTML = `<div class="empty-state"><div class="empty-icon">∅</div>No matching papers.<br>Try different keywords, a paper code (e.g. AP-011), or clear some filters.</div>`;
      $("#pager").hidden = true;
      return;
    }

    const pdfIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v5h5M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V8z"/></svg>`;
    box.innerHTML = slice.map((p, i) => {
      const href = safeUrl(p.pdf_url || p.source_url);
      const tldr = (p.abstract || "").replace(/\s+/g, " ").trim();
      const tint = confTint(p.conference);
      return `
      <a class="paper-card tint-${tint}" href="${esc(href)}" target="_blank" rel="noopener" style="animation-delay:${Math.min(i * 25, 300)}ms">
        <div class="paper-title">${esc(p.title)}</div>
        ${p.authors && p.authors.length ? `<div class="paper-authors">${esc(p.authors.join("; "))}</div>` : ""}
        ${tldr ? `<div class="paper-tldr"><b>TLDR</b>${esc(tldr.slice(0, 220))}${tldr.length > 220 ? "…" : ""}</div>` : ""}
        <div class="paper-meta">
          <span class="badge badge-conf">${esc(p.conference_name)}</span>
          ${p.section_name ? `<span class="badge badge-section">${esc(p.section_name)}</span>` : ""}
          ${p.year ? `<span class="badge badge-year">${p.year}</span>` : ""}
          <span class="paper-code">${esc(p.paper_code)}</span>
          <span class="paper-pdf ${p.pdf_url ? "" : "nopdf"}">${pdfIcon}${p.pdf_url ? "PDF" : "Source page"}</span>
        </div>
      </a>`;
    }).join("");

    const pager = $("#pager");
    if (pages <= 1) { pager.hidden = true; return; }
    pager.hidden = false;
    let html = `<button ${state.page === 1 ? "disabled" : ""} data-go="${state.page - 1}">‹</button>`;
    const win = 2;
    for (let i = 1; i <= pages; i++) {
      if (i === 1 || i === pages || (i >= state.page - win && i <= state.page + win)) {
        html += `<button class="${i === state.page ? "active" : ""}" data-go="${i}">${i}</button>`;
      } else if (i === state.page - win - 1 || i === state.page + win + 1) {
        html += `<button disabled>…</button>`;
      }
    }
    html += `<button ${state.page === pages ? "disabled" : ""} data-go="${state.page + 1}">›</button>`;
    pager.innerHTML = html;
    pager.querySelectorAll("button[data-go]").forEach((b) => {
      b.addEventListener("click", () => {
        state.page = Number(b.dataset.go);
        apply();
        document.getElementById("results").scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function hasActiveFilters() {
    return state.filters.conf.size || state.filters.region.size ||
      state.filters.year.size || state.filters.section.size;
  }

  function updateFilterCount() {
    const count = state.filters.conf.size + state.filters.region.size +
      state.filters.year.size + state.filters.section.size;
    document.querySelectorAll("#filter-count, #filter-count-mobile").forEach((el) => {
      if (count > 0) { el.textContent = count; el.classList.add("visible"); }
      else { el.classList.remove("visible"); el.textContent = ""; }
    });
  }

  // ---- routing ----
  let pendingScroll = null;
  function showView(view) {
    if (state.view === view) return;
    state.view = view;
    $("#view-home").hidden = view !== "home";
    $("#view-browse").hidden = view !== "browse";
    document.querySelectorAll("[data-nav]").forEach((a) =>
      a.classList.toggle("active", a.dataset.nav === view));
    document.title = view === "browse"
      ? "Browse Papers · ClinProc"
      : "ClinProc · Clinical Programming Conference Proceedings Index";
    window.scrollTo({ top: 0 });
  }

  function route() {
    const h = location.hash || "#/";
    const m = h.match(/^#\/browse(?:\/([\w.-]+))?/);
    if (m) {
      showView("browse");
      const code = m[1] && state.confs.some((c) => c.code === m[1]) ? m[1] : "";
      state.filters.conf = code ? new Set([code]) : new Set();
      state.page = 1;
      renderTabs();
      renderFilters();
      if (state.ready) apply();
    } else {
      showView("home");
      if (pendingScroll) {
        const id = pendingScroll; pendingScroll = null;
        requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }));
      }
    }
  }

  // ---- events ----
  function bindSearchInput(input, clearBtn) {
    let dt;
    input.addEventListener("input", () => {
      clearTimeout(dt);
      dt = setTimeout(() => {
        state.query = input.value;
        syncSearchInputs(input.value);
        state.page = 1;
        if (state.view === "browse") apply();
      }, 220);
    });
    clearBtn.addEventListener("click", () => {
      input.value = ""; state.query = "";
      syncSearchInputs("");
      state.page = 1;
      if (state.view === "browse") apply();
      input.focus();
    });
  }

  function syncSearchInputs(value) {
    for (const id of ["#search", "#search-browse"]) {
      const el = $(id); if (el) el.value = value;
    }
    $("#search-clear").hidden = !value;
    $("#search-clear-browse").hidden = !value;
  }

  function bind() {
    $("#theme-toggle").addEventListener("click", toggleTheme);

    // home search: submit -> browse view
    bindSearchInput($("#search"), $("#search-clear"));
    $("#search-form-home").addEventListener("submit", (e) => {
      e.preventDefault();
      state.query = $("#search").value;
      state.page = 1;
      if (state.view === "browse") { apply(); return; }
      syncSearchInputs(state.query);
      location.hash = "#/browse";
      if ((location.hash || "#/") === "#/browse") route(); // hash unchanged case
    });

    // browse search: live + submit
    bindSearchInput($("#search-browse"), $("#search-clear-browse"));
    $("#search-form-browse").addEventListener("submit", (e) => {
      e.preventDefault();
      state.query = $("#search-browse").value;
      syncSearchInputs(state.query);
      state.page = 1;
      apply();
    });

    $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; state.page = 1; apply(); });

    $("#reset-filters").addEventListener("click", () => {
      state.filters = { conf: new Set(), region: new Set(), year: new Set(), section: new Set() };
      state.query = ""; syncSearchInputs("");
      state.page = 1;
      location.hash = "#/browse";
      renderTabs(); renderFilters(); apply();
    });

    document.querySelectorAll(".filter-label").forEach((label) => {
      label.addEventListener("click", () => label.closest(".filter-group").classList.toggle("collapsed"));
    });

    // top-nav scroll links (Conferences / About live on home)
    document.querySelectorAll("[data-scroll]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const id = a.dataset.scroll;
        if (state.view === "home") document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
        else { pendingScroll = id; location.hash = "#/"; route(); }
      });
    });

    // keyboard: / focuses the visible search box
    document.addEventListener("keydown", (e) => {
      const homeInput = $("#search"), browseInput = $("#search-browse");
      const active = state.view === "home" ? homeInput : browseInput;
      if (e.key === "/" && document.activeElement !== homeInput && document.activeElement !== browseInput) {
        e.preventDefault(); active.focus();
      }
      if (e.key === "Escape" && document.activeElement === active) active.blur();
    });

    const filterToggle = $("#filter-toggle");
    if (filterToggle) {
      filterToggle.addEventListener("click", () => {
        filterToggle.classList.toggle("open");
        $("#filters").classList.toggle("open");
      });
    }

    const scrollTop = $("#scroll-top");
    if (scrollTop) {
      window.addEventListener("scroll", () => {
        scrollTop.classList.toggle("visible", window.scrollY > 600);
      }, { passive: true });
      scrollTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    }

    window.addEventListener("hashchange", route);
  }

  initTheme();
  document.addEventListener("DOMContentLoaded", () => { bind(); load(); });
})();
