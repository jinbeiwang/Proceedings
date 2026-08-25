/* ClinProc · updates / changelog module (v1)
   Renders data/changelog.json as a timeline inside the home view.
   Purely additive: on failure the section is simply hidden. */

(() => {
  "use strict";

  const TAGS = {
    feature: { label: "Feature", cls: "feature" },
    data: { label: "Data", cls: "data" },
    fix: { label: "Fix", cls: "fix" },
  };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

  async function load() {
    const box = document.getElementById("changelog-list");
    if (!box) return;
    try {
      const res = await fetch("data/changelog.json");
      if (!res.ok) throw new Error("changelog.json " + res.status);
      const entries = await res.json();
      if (!Array.isArray(entries) || !entries.length) throw new Error("empty changelog");
      box.innerHTML = entries.map((e) => {
        const tag = TAGS[e.tag] || { label: e.tag || "Update", cls: "" };
        const notes = Array.isArray(e.notes) ? e.notes : [];
        return `
        <div class="cl-item">
          <div class="cl-dot"></div>
          <div class="cl-body">
            <div class="cl-head">
              <span class="cl-date">${esc(e.date || "")}</span>
              <span class="cl-tag ${tag.cls ? "cl-tag-" + tag.cls : ""}">${esc(tag.label)}</span>
            </div>
            <div class="cl-title">${esc(e.title || "")}</div>
            ${notes.length ? `<ul class="cl-notes">${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
          </div>
        </div>`;
      }).join("");
    } catch (e) {
      console.warn("[changelog] unavailable:", e);
      const section = document.getElementById("changelog");
      if (section) section.style.display = "none";
    }
  }

  try {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
    else load();
  } catch (e) { console.warn("[changelog] init failed:", e); }
})();
