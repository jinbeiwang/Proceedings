/* ClinProc · 静态站前端逻辑
   加载 JSON 数据 -> 构建 Lunr 索引 -> 筛选/搜索/排序/分页渲染
   纯客户端,无服务端依赖。

   v6 — "Scholar" redesign
   Semantic Scholar 的学术清爽 + Hugging Face Papers 的 Trending 信息流。
   保留全部核心功能:骨架屏 + 数字递增 + 暗色/亮色主题 + 筛选级联联动。 */

(() => {
  "use strict";

  const PER_PAGE = 30;
  const $ = (s) => document.querySelector(s);
  const THEME_KEY = "clinproc-theme";
  // 仓库推送到 GitHub 后在此填入地址,导航栏会自动显示 GitHub 入口
  const REPO_URL = "";

  // ---- 状态 ----
  const state = {
    papers: [],
    confs: [],
    idx: null,                 // Lunr 索引
    filters: { conf: new Set(), region: new Set(), year: new Set(), section: new Set() },
    query: "",
    sort: "year-desc",
    page: 1,
    ready: false,
  };

  // ---- 工具 ----
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const toast = (msg) => {
    const t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (t.hidden = true), 2600);
  };

  // ---- 数字递增动画 ----
  function animateValue(el, end, duration = 900) {
    if (typeof end !== "number" || isNaN(end) || end === 0) {
      el.textContent = typeof end === "number" ? end.toLocaleString() : end;
      return;
    }
    const startTime = performance.now();
    function step(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.floor(end * eased);
      el.textContent = current.toLocaleString();
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = end.toLocaleString();
    }
    requestAnimationFrame(step);
  }

  // ---- 主题管理 ----
  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = saved || (prefersDark ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  }
  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(THEME_KEY, next);
  }

  // ---- 加载骨架屏 ----
  function showSkeleton() {
    const box = $("#results-list");
    box.innerHTML = Array(8).fill('<div class="skeleton-card"></div>').join("");
  }

  // ---- 数据加载 ----
  async function load() {
    showSkeleton();
    try {
      const [pRes, cRes] = await Promise.all([
        fetch("data/papers.json"),
        fetch("data/conferences.json"),
      ]);
      if (!pRes.ok) throw new Error("papers.json 加载失败");
      state.papers = await pRes.json();
      state.confs = cRes.ok ? await cRes.json() : [];
      buildIndex();
      renderStats();
      renderTrending();
      renderConfGrid();
      renderFilters();
      state.ready = true;
      apply();
    } catch (e) {
      console.error(e);
      $("#results-count").innerHTML = `<span style="color:var(--danger)">数据加载失败: ${esc(e.message)}。请通过本地 HTTP 服务器预览(file:// 协议无法 fetch JSON)。</span>`;
      $("#results-list").innerHTML = "";
      toast("数据加载失败");
    }
  }

  // ---- Lunr 索引 ----
  function buildIndex() {
    if (typeof lunr === "undefined") {
      toast("搜索引擎未加载,仅支持筛选");
      return;
    }
    state.idx = lunr(function () {
      this.ref("id");
      this.field("title", { boost: 4 });
      this.field("authors", { boost: 3 });
      this.field("section_name", { boost: 2 });
      this.field("conference_name", { boost: 2 });
      this.field("paper_code", { boost: 1 });
      this.field("section_code", { boost: 1 });
      for (const p of state.papers) {
        this.add({
          id: p.id,
          title: p.title || "",
          authors: (p.authors || []).join("; "),
          section_name: p.section_name || "",
          conference_name: p.conference_name || "",
          paper_code: p.paper_code || "",
          section_code: p.section_code || "",
        });
      }
    });
  }

  // ---- 统计 ----
  function renderStats() {
    const ps = state.papers;
    const years = ps.map((p) => p.year).filter(Boolean);
    animateValue($("#stat-papers"), ps.length);
    const confCount = new Set(ps.map((p) => p.conference)).size;
    animateValue($("#stat-confs"), confCount);
    $("#stat-years").textContent = years.length
      ? `${Math.min(...years)}–${Math.max(...years)}` : "—";
    // 最近更新:取最大 added_at 的日期部分
    const latest = ps.map((p) => p.added_at || "").filter(Boolean).sort().pop();
    $("#stat-updated").textContent = latest ? latest.slice(0, 10) : "—";
  }

  // ---- 最新收录(HF Papers 风格信息流) ----
  function renderTrending() {
    const box = $("#trending-list");
    if (!box) return;
    // 按抓取时间取最新 6 篇;14 天内入库的打 NEW 标
    const now = Date.now();
    const latest = [...state.papers]
      .filter((p) => p.added_at)
      .sort((a, b) => b.added_at.localeCompare(a.added_at))
      .slice(0, 6);
    if (!latest.length) { box.closest(".trending").style.display = "none"; return; }
    $("#trending-sub").textContent =
      `最近更新 ${latest[0].added_at.slice(0, 10)}`;
    box.innerHTML = latest.map((p, i) => {
      const isNew = now - Date.parse(p.added_at) < 14 * 864e5;
      const href = p.pdf_url || p.source_url || "#";
      return `<a class="trend-card" href="${esc(href)}" target="_blank" rel="noopener">
        <span class="trend-rank">${String(i + 1).padStart(2, "0")}</span>
        <span class="trend-conf">${esc(p.conference_name)} ${p.year || ""}</span>
        <span class="trend-title">${esc(p.title)}</span>
        <span class="trend-meta">
          ${isNew ? `<span class="trend-new">NEW</span>` : ""}
          ${p.authors && p.authors.length ? esc(p.authors[0]) + (p.authors.length > 1 ? " 等" : "") : ""}
          ${p.pdf_url ? "· PDF" : ""}
        </span>
      </a>`;
    }).join("");
  }

  // ---- 会议卡片 ----
  function renderConfGrid() {
    const grid = $("#conf-grid");
    grid.innerHTML = state.confs.map((c) => {
      const yr = c.year_min && c.year_max
        ? `${c.year_min}–${c.year_max}` : (c.year_min || "—");
      const status = c.implemented
        ? `<div class="conf-status ready">● 已收录</div>`
        : `<div class="conf-status todo">○ 待接入</div>`;
      return `<div class="conf-card ${c.implemented ? "" : "disabled"}" data-conf="${esc(c.code)}" data-region="${esc(c.region)}">
        <div class="conf-name">${esc(c.name)}</div>
        <div class="conf-region">${esc(c.region)} · ${esc(c.lang)}</div>
        <div class="conf-stat"><span><b>${c.count.toLocaleString()}</b> 篇</span><span>${yr}</span></div>
        ${status}
      </div>`;
    }).join("");
    grid.querySelectorAll(".conf-card").forEach((card) => {
      card.addEventListener("click", () => {
        if (card.classList.contains("disabled")) return;
        const code = card.dataset.conf;
        state.filters.conf = new Set([code]);
        state.page = 1;
        renderFilters();
        apply();
        document.getElementById("results").scrollIntoView({ behavior: "smooth" });
      });
    });
  }

  // ---- 筛选器（级联联动）----
  // 核心逻辑：渲染某个维度的筛选项时，只显示「在其他已选筛选项约束下」仍有数据的选项。
  // 例如：选了 SGF 后，年份只显示 2007-2020，主题只显示 SGF 的 sections。
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
    // 会议 — 始终显示全部已实现的会议，但计数随其他筛选动态变化
    const confBase = getFilteredPapers("conf");
    renderChips("#filter-conf", state.confs.filter((c) => c.implemented).map((c) => ({
      key: c.code, label: c.name,
      count: confBase.filter((p) => p.conference === c.code).length,
    })).filter((it) => it.count > 0 || state.filters.conf.has(it.key)), state.filters.conf, true);

    // 地区 — 只显示在当前筛选下有数据的地区
    const regionBase = getFilteredPapers("region");
    const regionMap = {};
    for (const p of regionBase) {
      const r = p.region || "其他";
      regionMap[r] = (regionMap[r] || 0) + 1;
    }
    renderChips("#filter-region", Object.entries(regionMap).map(([k, v]) => ({
      key: k, label: k, count: v,
    })).sort((a, b) => b.count - a.count), state.filters.region);

    // 年份 — 只显示在当前筛选下有数据的年份
    const yearBase = getFilteredPapers("year");
    const yearMap = {};
    for (const p of yearBase) {
      if (p.year) yearMap[p.year] = (yearMap[p.year] || 0) + 1;
    }
    renderChips("#filter-year", Object.entries(yearMap).map(([k, v]) => ({
      key: k, label: k, count: v,
    })).sort((a, b) => Number(b.key) - Number(a.key)), state.filters.year);

    // Section — 只显示在当前筛选下有数据的主题
    const secBase = getFilteredPapers("section");
    const secMap = {};
    for (const p of secBase) {
      if (p.section_name) secMap[p.section_name] = (secMap[p.section_name] || 0) + 1;
    }
    renderChips("#filter-section", Object.entries(secMap).map(([k, v]) => ({
      key: k, label: k, count: v,
    })).sort((a, b) => b.count - a.count), state.filters.section);

    // 更新各筛选组的活跃计数标记
    updateFilterGroupCounts();
  }

  function updateFilterGroupCounts() {
    const dims = [
      ["conf", "#filter-conf"],
      ["region", "#filter-region"],
      ["year", "#filter-year"],
      ["section", "#filter-section"],
    ];
    for (const [dim, sel] of dims) {
      const group = document.querySelector(sel)?.closest(".filter-group");
      if (!group) continue;
      const count = state.filters[dim].size;
      const badge = group.querySelector(".filter-active-count");
      if (badge) {
        badge.textContent = count > 0 ? count : "";
        badge.style.display = count > 0 ? "" : "none";
      }
      // 有活跃选择时自动展开该组
      if (count > 0) {
        group.classList.remove("collapsed");
      }
      // 如果该维度有被其他筛选约束掉的选项，给标签加个标记
      const total = state.papers.length;
      const filtered = getFilteredPapers(dim).length;
      if (filtered < total && count === 0) {
        group.classList.add("filter-constrained");
      } else {
        group.classList.remove("filter-constrained");
      }
    }
    // 渲染活跃筛选标签栏
    renderActiveBar();
  }

  function renderActiveBar() {
    const bar = $("#filter-active-bar");
    if (!bar) return;
    const tags = [];
    const dimLabels = { conf: "会议", region: "地区", year: "年份", section: "主题" };
    const dimMaps = {
      conf: Object.fromEntries(state.confs.map((c) => [c.code, c.name])),
      region: {}, year: {}, section: {},
    };
    for (const p of state.papers) {
      if (p.region && !dimMaps.region[p.region]) dimMaps.region[p.region] = p.region;
      if (p.year && !dimMaps.year[String(p.year)]) dimMaps.year[String(p.year)] = String(p.year);
      if (p.section_name && !dimMaps.section[p.section_name]) dimMaps.section[p.section_name] = p.section_name;
    }
    for (const [dim, label] of Object.entries(dimLabels)) {
      for (const key of state.filters[dim]) {
        const display = dimMaps[dim][key] || key;
        tags.push(`<span class="filter-tag" data-dim="${dim}" data-key="${esc(key)}"><span class="filter-tag-cat">${label}:</span>${esc(display)} ×</span>`);
      }
    }
    bar.innerHTML = tags.join("");
    bar.querySelectorAll(".filter-tag").forEach((tag) => {
      tag.addEventListener("click", () => {
        const dim = tag.dataset.dim;
        const key = tag.dataset.key;
        state.filters[dim].delete(key);
        state.page = 1;
        renderFilters();
        apply();
      });
    });
  }

  function renderChips(selector, items, activeSet, abbreviate) {
    const el = $(selector);
    if (!items.length) { el.innerHTML = `<span style="font-size:12px;color:var(--text-faint)">无数据</span>`; return; }
    el.innerHTML = items.map((it) => {
      const active = activeSet.has(it.key) ? "active" : "";
      const label = abbreviate && it.label.length > 22 ? it.label.slice(0, 21) + "…" : it.label;
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

  // ---- 筛选 + 搜索 + 排序 + 分页 ----
  function apply() {
    let list = state.papers;
    let searchResults = null;

    // 文本搜索
    const q = state.query.trim();
    if (q && state.idx) {
      try {
        const terms = q.split(/\s+/).filter(Boolean).map((t) => t.replace(/[*+\-~^:]/g, " "));
        const results = state.idx.search(terms.map((t) => `${t}*`).join(" "));
        const scoreMap = new Map(results.map((r) => [r.ref, r.score]));
        list = list.filter((p) => scoreMap.has(p.id));
        searchResults = scoreMap;
      } catch {
        const ql = q.toLowerCase();
        list = list.filter((p) =>
          (p.title || "").toLowerCase().includes(ql) ||
          (p.section_name || "").toLowerCase().includes(ql) ||
          (p.paper_code || "").toLowerCase().includes(ql));
      }
    }

    // 分类筛选(同类 OR,跨类 AND)
    list = list.filter((p) => {
      if (state.filters.conf.size && !state.filters.conf.has(p.conference)) return false;
      if (state.filters.region.size && !state.filters.region.has(p.region)) return false;
      if (state.filters.year.size && !state.filters.year.has(String(p.year))) return false;
      if (state.filters.section.size && !state.filters.section.has(p.section_name)) return false;
      return true;
    });

    // 排序
    const sort = state.sort;
    list = [...list];
    if (sort === "relevance" && searchResults) {
      list.sort((a, b) => (searchResults.get(b.id) || 0) - (searchResults.get(a.id) || 0));
    } else if (sort === "year-desc") {
      list.sort((a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title));
    } else if (sort === "year-asc") {
      list.sort((a, b) => (a.year || 0) - (b.year || 0) || a.title.localeCompare(b.title));
    } else if (sort === "title") {
      list.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
    } else if (sort === "relevance") {
      // 无搜索时退化为年份降序
      list.sort((a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title));
    }

    renderResults(list);
    updateFilterCount();
  }

  function renderResults(list) {
    $("#results-count").innerHTML = `共 <b>${list.length.toLocaleString()}</b> 篇${
      hasActiveFilters() ? ` · 筛选自 ${state.papers.length.toLocaleString()} 篇` : ""
    }`;

    const total = list.length;
    const pages = Math.ceil(total / PER_PAGE) || 1;
    if (state.page > pages) state.page = 1;
    const start = (state.page - 1) * PER_PAGE;
    const slice = list.slice(start, start + PER_PAGE);

    const box = $("#results-list");
    if (!slice.length) {
      box.innerHTML = `<div class="empty-state"><div class="empty-icon">∅</div>未找到匹配论文。<br>尝试调整搜索词或清除筛选条件。</div>`;
      $("#pager").hidden = true;
      return;
    }

    const pdfIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v5h5M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V8z"/></svg>`;
    box.innerHTML = slice.map((p, i) => {
      const href = p.pdf_url || p.source_url || "#";
      const tldr = (p.abstract || "").replace(/\s+/g, " ").trim();
      return `
      <a class="paper-card" href="${esc(href)}" target="_blank" rel="noopener" style="animation-delay:${Math.min(i * 25, 300)}ms">
        <div class="paper-title">${esc(p.title)}</div>
        ${p.authors && p.authors.length ? `<div class="paper-authors">${esc(p.authors.join("; "))}</div>` : ""}
        ${tldr ? `<div class="paper-tldr"><b>摘要</b>${esc(tldr.slice(0, 220))}${tldr.length > 220 ? "…" : ""}</div>` : ""}
        <div class="paper-meta">
          <span class="badge badge-conf">${esc(p.conference_name)}</span>
          ${p.section_name ? `<span class="badge badge-section">${esc(p.section_name)}</span>` : ""}
          ${p.year ? `<span class="badge badge-year">${p.year}</span>` : ""}
          <span class="paper-code">${esc(p.paper_code)}</span>
          <span class="paper-pdf ${p.pdf_url ? "" : "nopdf"}">${pdfIcon}${p.pdf_url ? "PDF" : "原文页"}</span>
        </div>
      </a>`;
    }).join("");

    // 分页
    const pager = $("#pager");
    if (pages <= 1) { pager.hidden = true; return; }
    pager.hidden = false;
    let html = "";
    html += `<button ${state.page === 1 ? "disabled" : ""} data-go="${state.page - 1}">‹</button>`;
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
    return state.query.trim() ||
      state.filters.conf.size || state.filters.region.size ||
      state.filters.year.size || state.filters.section.size;
  }

  // ---- 筛选计数 ----
  function updateFilterCount() {
    const count = state.filters.conf.size + state.filters.region.size +
      state.filters.year.size + state.filters.section.size;
    const els = document.querySelectorAll("#filter-count, #filter-count-mobile");
    els.forEach((el) => {
      if (count > 0) {
        el.textContent = count;
        el.classList.add("visible");
      } else {
        el.classList.remove("visible");
        el.textContent = "";
      }
    });
  }

  // ---- 事件绑定 ----
  function bind() {
    // 主题切换
    $("#theme-toggle").addEventListener("click", toggleTheme);

    // 搜索
    const input = $("#search");
    let dt;
    input.addEventListener("input", () => {
      clearTimeout(dt);
      dt = setTimeout(() => {
        state.query = input.value;
        $("#search-clear").hidden = !input.value;
        state.page = 1;
        apply();
      }, 200);
    });
    $("#search-clear").addEventListener("click", () => {
      input.value = ""; state.query = "";
      $("#search-clear").hidden = true; state.page = 1; apply(); input.focus();
    });

    // 排序
    $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; state.page = 1; apply(); });

    // 重置筛选
    $("#reset-filters").addEventListener("click", () => {
      state.filters = { conf: new Set(), region: new Set(), year: new Set(), section: new Set() };
      state.query = ""; $("#search").value = ""; $("#search-clear").hidden = true;
      state.page = 1; renderFilters(); apply();
    });

    // 筛选组折叠/展开
    document.querySelectorAll(".filter-label").forEach((label) => {
      label.addEventListener("click", () => {
        label.closest(".filter-group").classList.toggle("collapsed");
      });
    });

    // 键盘快捷键: / 聚焦搜索框
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== input) {
        e.preventDefault();
        input.focus();
      }
      if (e.key === "Escape" && document.activeElement === input) {
        input.blur();
      }
    });

    // 移动端筛选面板切换
    const filterToggle = $("#filter-toggle");
    const filtersPanel = $("#filters");
    if (filterToggle) {
      filterToggle.addEventListener("click", () => {
        filterToggle.classList.toggle("open");
        filtersPanel.classList.toggle("open");
      });
    }

    // 回到顶部按钮
    const scrollTop = $("#scroll-top");
    if (scrollTop) {
      window.addEventListener("scroll", () => {
        if (window.scrollY > 600) {
          scrollTop.classList.add("visible");
        } else {
          scrollTop.classList.remove("visible");
        }
      }, { passive: true });
      scrollTop.addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  // ---- 初始化 ----
  function initGitHubLink() {
    const link = $("#github-link");
    if (link && REPO_URL) {
      link.href = REPO_URL;
      link.hidden = false;
    }
  }

  initTheme();
  document.addEventListener("DOMContentLoaded", () => { bind(); load(); initGitHubLink(); });
})();
