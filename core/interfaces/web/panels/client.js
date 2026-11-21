// Panels of the W.Alter web interface — browser half (hand-written factory bundle, no build step).
// For each panel the host half published in window.__WALTER_PANELS__: one sidebar entry (root `sidebar.panellist`)
// and, under the same id, the main-area page (root `main` keyed slot) = the module's page framed at `<path>/`.
// The frame is mounted once and kept, so returning to the panel keeps its place.
window.__ModuleLoader__.load({
  id: "@walter/web-panels",
  factory: (require) => {
    const React = require("react");
    const h = React.createElement;
    const PANELS = Array.isArray(window.__WALTER_PANELS__) ? window.__WALTER_PANELS__ : [];

    function BoardIcon({ size }) {
      const s = size || 20;
      return h("svg", { width: s, height: s, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
          strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true" },
        h("rect", { x: 3, y: 4, width: 5, height: 16, rx: 1.5 }),
        h("rect", { x: 9.5, y: 4, width: 5, height: 10, rx: 1.5 }),
        h("rect", { x: 16, y: 4, width: 5, height: 13, rx: 1.5 }));
    }

    function framed(panel) {
      return function PanelPage() {
        return h("div", { className: "walter-panel", style: { position: "relative", width: "100%", height: "100%",
            minHeight: 0, background: "#000" } },
          h("iframe", { src: panel.path + "/", title: panel.label,
            style: { position: "absolute", inset: 0, width: "100%", height: "100%", border: 0, background: "#000" } }));
      };
    }

    // Settings links (window.__WALTER_LINKS__): a page opened in a new tab. Without `section`, one Settings › General
    // row (title, description, « Ouvrir » button — a row draws its own internals, the section passes no props); with
    // `section`, a whole Settings page under that nav id (the shell picks the nav glyph by id, e.g. `models`).
    const LINKS = Array.isArray(window.__WALTER_LINKS__) ? window.__WALTER_LINKS__ : [];

    function linkPage(link) {
      return function LinkPage() {
        return h("div", { style: { padding: "8px 0" } },
          h("div", { style: { fontSize: 16, lineHeight: "24px", fontWeight: 500 } }, link.label),
          link.description ? h("div", { style: { color: "var(--dsw-alias-label-secondary)", marginTop: 6,
            fontSize: 13, lineHeight: "20px" } }, link.description) : null,
          h("a", { href: link.url, target: "_blank", rel: "noopener noreferrer",
              style: { display: "block", marginTop: 20, padding: "12px 16px", border: "2px solid #01B7FF",
                borderRadius: 10, color: "#01B7FF", fontSize: 14, lineHeight: "20px", textAlign: "center",
                textDecoration: "none" } },
            "Ouvrir ↗"));
      };
    }

    function linkRow(link) {
      return function LinkRow() {
        return h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24,
            padding: "16px 0", borderBottom: ".5px solid var(--dsw-alias-border-l2)" } },
          h("div", null,
            h("div", { style: { fontSize: 14, lineHeight: "20px" } }, link.label),
            link.description ? h("div", { style: { color: "var(--dsw-alias-label-secondary)", marginTop: 4,
              fontSize: 12, lineHeight: "18px" } }, link.description) : null),
          h("a", { href: link.url, target: "_blank", rel: "noopener noreferrer", "aria-label": link.label,
              style: { flex: "none", padding: "6px 14px", border: "1px solid #01B7FF", borderRadius: 8,
                color: "#01B7FF", fontSize: 13, lineHeight: "18px", textDecoration: "none", whiteSpace: "nowrap" } },
            "Ouvrir ↗"));
      };
    }

    // A section link opens its page straight from the nav: a click on its nav entry (Settings dialog, nav button whose
    // label is the section label — the shell gives the button no id) opens the page in a new tab inside the same user
    // gesture and stops there, before the shell's own listener (window, capture phase). If the browser refuses the new
    // tab, the click goes on and the section page (with its button) shows instead.
    const DIRECT = new Map(LINKS.filter((l) => l.section).map((l) => [l.section_label || l.label, l.url]));
    if (DIRECT.size) {
      window.addEventListener("click", (ev) => {
        const button = ev.target instanceof Element
          && ev.target.closest('[data-shortcut-modal="settings"] nav button');
        const url = button && DIRECT.get(button.textContent.trim());
        if (!url) return;
        const tab = window.open(url, "_blank");
        if (!tab) return;
        try { tab.opener = null; } catch { /* cross-origin already */ }
        ev.preventDefault();
        ev.stopPropagation();
      }, true);
    }

    const inject = ["slots"];

    function apply(ctx) {
      LINKS.forEach((link, i) => {
        if (link.section) {
          ctx.slots.inject("settings.section", () => ctx.slots.register({
            name: "settings.section", id: link.section, order: 10 + i, label: link.section_label || link.label },
            linkPage(link)));
          return;
        }
        ctx.slots.inject("settings.general.item", () => ctx.slots.register({
          name: "settings.general.item", id: "walter-link-" + link.id, order: 90 + i }, linkRow(link)));  // above the version line (100)
      });
      PANELS.forEach((panel, i) => {
        const Page = framed(panel);
        ctx.slots.inject("main", function* () {
          yield ctx.slots.register({ name: "main", key: panel.id }, Page);
        });
        ctx.slots.inject("sidebar.panellist", () => ctx.slots.register({
          name: "sidebar.panellist", id: panel.id, order: 10 + i, label: panel.label }, BoardIcon));
      });
    }

    return { apply, inject };
  }
});
