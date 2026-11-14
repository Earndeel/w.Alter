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

    const inject = ["slots"];

    function apply(ctx) {
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
