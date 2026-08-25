/* ClinProc · favorites module (v1)
   Client-side paper favorites: localStorage persistence, star buttons
   injected into result cards, and the #/favorites view.

   Fully self-contained and defensive: if anything here fails, the main
   site keeps working — only the star buttons / view would be missing.
   Data schema (localStorage key "clinproc-favorites"):
     { version: 1, categories: [string], items: [
        { id, title, authors[], conference, conference_name, section_name,
          region, year, paper_code, pdf_url, source_url,
          category, note, savedAt } ] } */

(() => {
  "use strict";

  const STORE_KEY = "clinproc-favorites";
  const SCHEMA_VERSION = 1;
  const DEFAULT_CAT = "General";
  const NEW_CAT = "__new__";
  const STAR_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17.3l-6.2 3.7 1.6-7L2 9.2l7.1-.6L12 2l2.9 6.6 7.1.6-5.4 4.8 1.6 7z"/></svg>';

  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "#";

  const toast = (msg) => {
    try {
      const t = $("#toast");
      if (!t) return;
      t.textContent = msg; t.hidden = false;
      clearTimeout(toast._t);
      toast._t = setTimeout(() => (t.hidden = true), 2600);
    } catch { /* non-fatal */ }
  };

  // ---- state ----
  let store = { version: SCHEMA_VERSION, categories: [], items: [] };
  let favQuery = "";
  let favCat = ""; // "" = all categories

  const isValidItem = (it) =>
    it && typeof it === "object" && typeof it.id === "string" &&
    typeof it.title === "string" && it.title.trim();

  function loadStore() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.items)) {
        store = {
          version: SCHEMA_VERSION,
          categories: (Array.isArray(data.categories) ? data.categories : [])
            .filter((c) => typeof c === "string" && c.trim()).map((c) => c.trim()),
          items: data.items.filter(isValidItem),
        };
      }
    } catch (e) {
      console.warn("[favorites] store unreadable, starting fresh:", e);
    }
  }

  function persist() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(store));
    } catch (e) {
      console.warn("[favorites] save failed:", e);
      toast("Could not save favorites (storage blocked?)");
    }
  }

  const findItem = (id) => store.items.find((it) => it.id === id);
  const catOf = (it) => (it.category && String(it.category).trim()) ? String(it.category).trim() : DEFAULT_CAT;

  function allCategories() {
    const set = new Set(store.categories);
    for (const it of store.items) set.add(catOf(it));
    set.delete(DEFAULT_CAT);
    return [DEFAULT_CAT, ...[...set].sort((a, b) => a.localeCompare(b))];
  }

  function ensureCategory(name) {
    const n = String(name || "").trim().slice(0, 40);
    if (!n || n === DEFAULT_CAT) return n || DEFAULT_CAT;
    if (!store.categories.includes(n)) store.categories.push(n);
    return n;
  }

  // ---- nav badge ----
  function updateNavCount() {
    const el = $("#fav-nav-count");
    if (!el) return;
    const n = store.items.length;
    el.textContent = n > 99 ? "99+" : String(n);
    el.hidden = n === 0;
  }

  // ---- star buttons on browse result cards ----
  function decorateCard(card) {
    if (card.querySelector(":scope > .fav-btn")) return;
    let data;
    try { data = JSON.parse(card.dataset.fav || ""); } catch { return; }
    if (!data || !data.id) return;

    const btn = document.createElement("span");
    btn.className = "fav-btn" + (findItem(data.id) ? " active" : "");
    btn.setAttribute("role", "button");
    btn.setAttribute("tabindex", "0");
    btn.setAttribute("aria-label", "Save to favorites");
    btn.title = "Save to favorites";
    btn.innerHTML = STAR_SVG;
    const onClick = (e) => {
      e.preventDefault(); e.stopPropagation();
      toggleFav(data);
      btn.classList.toggle("active", !!findItem(data.id));
      btn.setAttribute("aria-label", btn.classList.contains("active") ? "Remove from favorites" : "Save to favorites");
    };
    btn.addEventListener("click", onClick);
    btn.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(e); }
    });
    card.appendChild(btn);
  }

  function toggleFav(data) {
    const idx = store.items.findIndex((it) => it.id === data.id);
    if (idx >= 0) {
      store.items.splice(idx, 1);
      persist();
      toast("Removed from favorites");
    } else {
      store.items.unshift({
        id: data.id,
        title: data.title || "",
        authors: Array.isArray(data.authors) ? data.authors : [],
        conference: data.conference || "",
        conference_name: data.conference_name || "",
        section_name: data.section_name || "",
        region: data.region || "",
        year: data.year || null,
        paper_code: data.paper_code || "",
        pdf_url: data.pdf_url || "",
        source_url: data.source_url || "",
        category: "",
        note: "",
        savedAt: new Date().toISOString(),
      });
      persist();
      toast("Saved to favorites ★");
    }
    updateNavCount();
    if (isFavRoute()) renderFavorites();
  }

  function watchResults() {
    const box = document.getElementById("results-list");
    if (!box) return;
    const scan = () => box.querySelectorAll(".paper-card[data-fav]").forEach(decorateCard);
    scan();
    try {
      new MutationObserver(scan).observe(box, { childList: true });
    } catch (e) { console.warn("[favorites] observer failed:", e); }
  }

  // ---- favorites view ----
  const isFavRoute = () => /^#\/favorites/.test(location.hash || "#/");

  function favCardHtml(it) {
    const href = safeUrl(it.pdf_url || it.source_url);
    const authors = (it.authors || []).join("; ");
    const cats = allCategories();
    const cat = catOf(it);
    const options = cats.map((c) =>
      `<option value="${esc(c)}" ${c === cat ? "selected" : ""}>${esc(c)}</option>`).join("");
    return `
    <div class="fav-card" data-fid="${esc(it.id)}">
      <div class="fav-card-top">
        <a class="fav-title" href="${esc(href)}" target="_blank" rel="noopener">${esc(it.title)}</a>
        <span class="fav-star active" data-act="remove" role="button" tabindex="0" title="Remove from favorites" aria-label="Remove from favorites">${STAR_SVG}</span>
      </div>
      ${authors ? `<div class="fav-authors">${esc(authors)}</div>` : ""}
      ${it.note ? `<div class="fav-note"><b>NOTE</b>${esc(it.note)}</div>` : ""}
      <div class="fav-meta">
        ${it.conference_name ? `<span class="badge badge-conf">${esc(it.conference_name)}</span>` : ""}
        ${it.section_name ? `<span class="badge badge-section">${esc(it.section_name)}</span>` : ""}
        ${it.year ? `<span class="badge badge-year">${esc(it.year)}</span>` : ""}
        ${it.paper_code ? `<span class="paper-code">${esc(it.paper_code)}</span>` : ""}
        <span class="fav-date">${it.pdf_url ? "PDF" : "Source page"}${it.savedAt ? " · saved " + esc(String(it.savedAt).slice(0, 10)) : ""}</span>
      </div>
      <div class="fav-actions">
        <select class="fav-cat" aria-label="Category">${options}<option value="${NEW_CAT}">＋ New category…</option></select>
        <button class="fav-act" data-act="note">${it.note ? "Edit note" : "＋ Note"}</button>
        <button class="fav-act fav-act-danger" data-act="remove">Remove</button>
      </div>
    </div>`;
  }

  function renderFavorites() {
    const main = $("#favorites-main");
    if (!main) return;

    const stats = $("#fav-stats");
    if (stats) stats.textContent =
      `${store.items.length} saved paper${store.items.length === 1 ? "" : "s"} · ${allCategories().length} categor${allCategories().length === 1 ? "y" : "ies"}`;

    // category chips (counts over ALL favorites, not the filtered set)
    const counts = {};
    for (const it of store.items) { const c = catOf(it); counts[c] = (counts[c] || 0) + 1; }
    const chipBox = $("#fav-cat-chips");
    if (chipBox) {
      chipBox.innerHTML =
        `<span class="chip ${favCat === "" ? "active" : ""}" data-cat="">All<span class="chip-count">${store.items.length}</span></span>` +
        allCategories().map((c) =>
          `<span class="chip ${favCat === c ? "active" : ""}" data-cat="${esc(c)}">${esc(c)}<span class="chip-count">${counts[c] || 0}</span></span>`
        ).join("");
      chipBox.querySelectorAll(".chip").forEach((ch) => {
        ch.addEventListener("click", () => {
          favCat = ch.dataset.cat;
          renderFavorites();
        });
      });
    }

    renderCatManage();

    if (!store.items.length) {
      main.innerHTML = `<div class="empty-state"><div class="empty-icon">☆</div>No favorites yet.<br>Browse papers and click the <b>star</b> on a card to save it here.<br>Everything stays in your own browser.</div>`;
      return;
    }

    const q = favQuery.trim().toLowerCase();
    let items = store.items;
    if (favCat) items = items.filter((it) => catOf(it) === favCat);
    if (q) {
      items = items.filter((it) => {
        const hay = [it.title, (it.authors || []).join(" "), it.note,
          it.conference_name, it.paper_code, it.section_name].join(" ").toLowerCase();
        return q.split(/\s+/).every((t) => hay.includes(t));
      });
    }
    if (!items.length) {
      main.innerHTML = `<div class="empty-state"><div class="empty-icon">∅</div>No favorites match. Clear the filter or keywords.</div>`;
      return;
    }

    const cats = favCat ? [favCat] : allCategories().filter((c) => items.some((it) => catOf(it) === c));
    main.innerHTML = cats.map((cat) => {
      const list = items.filter((it) => catOf(it) === cat)
        .sort((a, b) => (b.savedAt || "").localeCompare(a.savedAt || ""));
      return `<section class="res-section">
        <div class="res-section-head">
          <h2 class="res-section-title">${esc(cat)}</h2>
          <span class="res-section-count">${list.length}</span>
        </div>
        <div class="fav-list">${list.map(favCardHtml).join("")}</div>
      </section>`;
    }).join("");
  }

  function renderCatManage() {
    const box = $("#fav-cat-list");
    if (!box) return;
    const counts = {};
    for (const it of store.items) { const c = catOf(it); counts[c] = (counts[c] || 0) + 1; }
    const cats = allCategories().filter((c) => c !== DEFAULT_CAT);
    box.innerHTML = cats.length ? cats.map((c) => `
      <span class="fav-cat-item">
        <b>${esc(c)}</b><span class="fav-cat-count">${counts[c] || 0}</span>
        <button class="fav-mini" data-ren="${esc(c)}" title="Rename category">✎</button>
        <button class="fav-mini danger" data-delcat="${esc(c)}" title="Delete category (papers move to ${esc(DEFAULT_CAT)})">✕</button>
      </span>`).join("") :
      `<span class="fav-storage-note">Only the default “${DEFAULT_CAT}” category exists. Add one above.</span>`;
  }

  // ---- category card events (delegated) ----
  function bindFavMain() {
    const main = $("#favorites-main");
    if (!main) return;

    main.addEventListener("click", (e) => {
      const star = e.target.closest(".fav-star");
      const actEl = e.target.closest("[data-act]");
      const card = e.target.closest("[data-fid]");
      if (!card) return;
      const item = findItem(card.dataset.fid);
      if (!item) { renderFavorites(); return; }
      const act = (actEl || star)?.dataset.act;
      if (act === "remove") {
        toggleFav({ id: item.id });
        renderFavorites();
      } else if (act === "note") {
        const v = prompt("Note for this paper (why you saved it, what to reuse…):", item.note || "");
        if (v !== null) { item.note = v.slice(0, 1000); persist(); renderFavorites(); }
      }
    });
    main.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.classList?.contains("fav-star")) {
        e.preventDefault(); e.target.click();
      }
    });

    main.addEventListener("change", (e) => {
      if (!e.target.classList.contains("fav-cat")) return;
      const card = e.target.closest("[data-fid]");
      const item = card && findItem(card.dataset.fid);
      if (!item) return;
      let v = e.target.value;
      if (v === NEW_CAT) {
        const name = prompt("New category name:");
        if (name && name.trim()) v = ensureCategory(name);
        else { renderFavorites(); return; }
      }
      item.category = v === DEFAULT_CAT ? "" : v;
      persist();
      renderFavorites();
    });
  }

  function bindFavSearch() {
    const input = $("#search-favorites"), clear = $("#search-clear-favorites");
    if (!input) return;
    let dt;
    input.addEventListener("input", () => {
      clearTimeout(dt);
      dt = setTimeout(() => {
        favQuery = input.value;
        if (clear) clear.hidden = !input.value;
        renderFavorites();
      }, 180);
    });
    clear?.addEventListener("click", () => {
      input.value = ""; favQuery = ""; clear.hidden = true;
      renderFavorites(); input.focus();
    });
    $("#search-form-favorites")?.addEventListener("submit", (e) => {
      e.preventDefault();
      favQuery = input.value;
      if (clear) clear.hidden = !input.value;
      renderFavorites();
    });
  }

  function bindCatManage() {
    const addBtn = $("#fav-add-cat"), input = $("#fav-new-cat-input");
    const addCat = () => {
      const name = input?.value?.trim();
      if (!name) { input?.focus(); return; }
      ensureCategory(name);
      if (input) input.value = "";
      persist();
      renderFavorites();
      toast(`Category “${name}” added`);
    };
    addBtn?.addEventListener("click", addCat);
    input?.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addCat(); } });

    $("#fav-cat-list")?.addEventListener("click", (e) => {
      const ren = e.target.closest("[data-ren]")?.dataset.ren;
      const del = e.target.closest("[data-delcat]")?.dataset.delcat;
      if (ren) {
        const name = prompt("Rename category (applies to all its papers):", ren);
        if (!name || !name.trim() || name.trim() === ren) return;
        const n = ensureCategory(name);
        for (const it of store.items) if (catOf(it) === ren) it.category = n === DEFAULT_CAT ? "" : n;
        store.categories = store.categories.filter((c) => c !== ren);
        if (favCat === ren) favCat = n;
        persist(); renderFavorites();
      } else if (del) {
        if (!confirm(`Delete category “${del}”? Its papers move to “${DEFAULT_CAT}”.`)) return;
        for (const it of store.items) if (catOf(it) === del) it.category = "";
        store.categories = store.categories.filter((c) => c !== del);
        if (favCat === del) favCat = "";
        persist(); renderFavorites();
      }
    });

    $("#fav-export")?.addEventListener("click", exportFavs);
    $("#fav-import")?.addEventListener("click", () => $("#fav-import-file")?.click());
    $("#fav-import-file")?.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) importFavs(file);
      e.target.value = "";
    });
  }

  function exportFavs() {
    try {
      const blob = new Blob([JSON.stringify(store, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `clinproc-favorites-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      toast(`Exported ${store.items.length} favorites`);
    } catch (e) {
      console.warn("[favorites] export failed:", e);
      toast("Export failed");
    }
  }

  function importFavs(file) {
    file.text().then((txt) => {
      const data = JSON.parse(txt);
      if (!data || !Array.isArray(data.items)) throw new Error("not a favorites backup");
      const byId = new Map(store.items.map((it) => [it.id, it]));
      let n = 0;
      for (const it of data.items) {
        if (!isValidItem(it)) continue;
        byId.set(it.id, { ...it, savedAt: it.savedAt || new Date().toISOString() });
        n++;
      }
      if (!n) throw new Error("no valid items found");
      store.items = [...byId.values()];
      for (const c of data.categories || []) ensureCategory(c);
      persist(); renderFavorites(); updateNavCount();
      toast(`Imported ${n} favorites (merged by paper id)`);
    }).catch((e) => toast("Import failed: " + e.message));
  }

  // ---- view switching (app.js also handles #/favorites; this is a fallback) ----
  function onHash() {
    if (!isFavRoute()) return;
    const fav = document.getElementById("view-favorites");
    if (!fav) return;
    document.title = "Favorites · ClinProc";
    for (const id of ["view-home", "view-browse", "view-resources"]) {
      const el = document.getElementById(id);
      if (el) el.hidden = true;
    }
    fav.hidden = false;
    renderFavorites();
  }

  // ---- init ----
  function init() {
    loadStore();
    updateNavCount();
    watchResults();
    bindFavSearch();
    bindFavMain();
    bindCatManage();
    window.addEventListener("hashchange", onHash);
    onHash();
  }

  try {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  } catch (e) {
    console.warn("[favorites] init failed:", e);
  }
})();
