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

    // Settings links: one Settings › General row per entry of window.__WALTER_LINKS__ (title, description and an
    // « Ouvrir » button opening the page in a new tab — a row draws its own internals, the section passes no props).
    const LINKS = Array.isArray(window.__WALTER_LINKS__) ? window.__WALTER_LINKS__ : [];

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

    const inject = ["slots"];

    function apply(ctx) {
      LINKS.forEach((link, i) => {
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
