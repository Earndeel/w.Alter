// Walter face for the DSH web GUI — browser half (hand-written factory bundle, no build step).
// Fills the brand slots (sidebar mark + name, blank-session hero), registers the French language from the
// dictionaries the host half published in window.__WALTER_UI__, and stacks the Walter colour layer over the
// built-in palettes. Defaults (French, dark) are applied once per browser; the Settings choices win afterwards.
window.__ModuleLoader__.load({
  id: "@walter/dsh-web-ui",
  factory: (require) => {
    const React = require("react");
    const h = React.createElement;
    const W = window.__WALTER_UI__ || { name: "Walter", tagline: "", fr: {}, defaultLocale: "fr", defaultTheme: "dark" };
    const ACCENT = "#01B7FF";

    // ── brand ────────────────────────────────────────────────────────────────
    function WalterMark({ size }) {
      const s = size || 22;
      const letter = (W.name.trim()[0] || "W").toUpperCase();
      return h("svg", { width: s, height: s, viewBox: "0 0 32 32", "aria-hidden": "true", className: "walter-mark" },
        h("rect", { x: 1.25, y: 1.25, width: 29.5, height: 29.5, rx: 7, fill: "none", stroke: ACCENT, strokeWidth: 1.5 }),
        h("text", { x: 16, y: 22.5, textAnchor: "middle", fontSize: 19, fontWeight: 700, fill: "currentColor",
          fontFamily: "'Bodoni 72','Didot','Bodoni Moda','Playfair Display',Georgia,serif" }, letter));
    }
    function WalterName() {
      return h("span", { className: "walter-wordmark" }, W.name);
    }
    function WalterHero() {
      return h("span", { className: "walter-hero-mark" }, W.name);
    }
    function SkipStep({ complete }) {
      React.useEffect(() => { if (complete) complete(); }, []);
      return null;
    }

    // ── colour layer (dark = pure black surfaces, neon blue #01B7FF contrast, like Monsieur's Hermes Desktop theme;
    //    light keeps the shipped palette with a darker blue for legibility on white) ──
    const T = (light, dark) => ({ light, dark });
    const BLACK = "#000000";
    const TOKENS = {
      "bg-base": T("var(--dsw-static-neutral-bluish-00)", BLACK),
      "bg-document-preview": T("var(--dsw-static-neutral-bluish-100)", BLACK),
      "label-document-preview": T("var(--dsw-static-neutral-bluish-700)", "#dfe8ee"),
      "bg-layer-1": T("var(--dsw-static-neutral-bluish-00)", BLACK),
      "bg-layer-2": T("var(--dsw-static-neutral-bluish-00)", BLACK),
      "bg-layer-3": T("var(--dsw-static-neutral-bluish-00)", BLACK),
      "bg-module-platform": T("var(--dsw-static-neutral-bluish-60)", BLACK),
      "border-l1": T("#0000000a", "#01b7ff24"),
      "border-l2": T("#0000001a", "#01b7ff40"),
      "border-l3": T("#0000001f", "#01b7ff66"),
      "border-l4": T("#00000029", "#01b7ff99"),
      "brand-primary-new-colorprimary-new-color": T("#0090c8", ACCENT),
      "button-info-fill": T("#0090c8", ACCENT),
      "button-info-hover": T("#007aab", "#4dccff"),
      "interactive-bg-hover": T("#2631480f", "#01b7ff1a"),
      "interactive-bg-active": T("#2631481a", "#01b7ff2e"),
      "interactive-bg-hover-solid": T("var(--dsw-static-neutral-bluish-75)", "#04141c"),
      "label-caption": T("var(--dsw-static-neutral-bluish-400)", "#6f7b85"),
      "label-deep-diving": T("color-mix(in srgb, #0090c8 70%, var(--dsw-static-blue-950))", "color-mix(in srgb, #01b7ff 60%, #9aa6ae)"),
      "label-deep-diving-shimmer": T("color-mix(in srgb, #0090c8 30%, var(--dsw-static-blue-950))", "#8adcff"),
      "label-primary": T("var(--dsw-static-neutral-bluish-1000)", "#eef3f6"),
      "label-primary-bluish": T("var(--dsw-static-blue-900)", "#d6ecf7"),
      "label-secondary": T("var(--dsw-static-neutral-bluish-700)", "#b9c4cc"),
      "label-tertiary": T("var(--dsw-static-neutral-bluish-600)", "#8b96a0"),
      "link": T("#0090c8", ACCENT),
      "markdown-code-block": T("var(--dsw-static-neutral-bluish-50)", BLACK),
      "markdown-code-block-banner": T("var(--dsw-static-neutral-bluish-50)", "#03101a"),
      "markdown-inline-code": T("var(--dsw-static-neutral-50)", "#03141f"),
      "markdown-tag": T("var(--dsw-static-neutral-bluish-75)", "#03141f"),
      "state-business-primary": T("#0090c8", ACCENT),
      "state-business-tertiary": T("#dff3fb", "#002a3d"),
      "tooltip-bg": T("var(--dsw-static-neutral-bluish-850)", "#061823"),
      "toast-bg": T("var(--dsw-static-neutral-bluish-800)", "#061823"),
      "menu-group-header-fill": T("#f8f9faf0", "#000000f0"),
      "button-floating-fill": T("var(--dsw-static-neutral-bluish-00)", BLACK),
      "button-floating-hover": T("var(--dsw-static-neutral-bluish-75)", "#04141c"),
      "button-elevated-fill": T("var(--dsw-static-neutral-bluish-00)", BLACK),
      "bg-document-selection": T("color-mix(in srgb, #01b7ff 30%, transparent)", "color-mix(in srgb, #01b7ff 35%, transparent)"),
    };

    const inject = ["slots", "locale", "theme"];
    // The Host persists Settings choices only for loopback pages; a tailnet page keeps them per process, so the
    // browser remembers its own last choice (default: the instance's) and re-applies it on each load.
    const store = {
      get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
      set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } },
    };

    function apply(ctx) {
      // Brand: sidebar mark + name, and the blank-session hero.
      ctx.slots.inject("sidebar.brand.mark", () => ctx.slots.inject("sidebar.brand.name", function* () {
        yield ctx.slots.register({ name: "sidebar.brand.mark" }, WalterMark);
        yield ctx.slots.register({ name: "sidebar.brand.name" }, WalterName);
      }));
      ctx.slots.inject("conversation.hero.brand.mark", function* () {
        yield ctx.slots.register({ name: "conversation.hero.brand.mark" }, WalterHero);
      });
      // DeepSeek's product "preview notice" is not Walter's: shadow that onboarding step with one that completes
      // at once (a lower priority wins the cell). Tailnet pages keep its acknowledgement per page, so it would
      // otherwise come back on every visit.
      ctx.slots.inject("settings.onboarding", function* () {
        yield ctx.slots.register({ name: "settings.onboarding", id: "welcome-notice", order: -100, priority: -1 }, SkipStep);
      });

      // French: language definition + every published namespace (lazy plugins pick theirs up on load).
      const fr = W.fr || {};
      if (W.tagline) fr.conversation = { ...(fr.conversation || {}), "hero.headline": W.tagline };
      ctx.effect(() => ctx.locale.addLanguage({ id: "fr", label: "Français", fallback: "en" }), "walter-ui: language fr");
      for (const [ns, dict] of Object.entries(fr)) {
        ctx.effect(() => ctx.locale.register(ns, "fr", dict), "walter-ui: fr " + ns);
      }

      // Colours: one override layer over whichever built-in palette is active.
      const tokens = {};
      for (const [k, v] of Object.entries(TOKENS)) tokens["--dsw-alias-" + k] = v;
      ctx.effect(() => ctx.theme.overrideTokens("@walter/dsh-web-ui", tokens), "walter-ui: palette");

      // Language and appearance: this browser's last choice, else the instance default. Applied once the stored
      // Host preference has had time to arrive; from then on every change made in Settings is remembered.
      const timer = setTimeout(() => {
        const locale = store.get("walter-ui.locale") || W.defaultLocale;
        if (locale && ctx.locale.getLocale().active !== locale) {
          try { ctx.locale.setLocale(locale); } catch (e) { /* language no longer registered */ }
        }
        const theme = store.get("walter-ui.theme") || W.defaultTheme;
        if (theme && ctx.theme.getTheme().preference !== theme) {
          try { ctx.theme.setTheme(theme); } catch (e) { /* unknown theme id */ }
        }
        ctx.effect(() => ctx.locale.subscribe(() => store.set("walter-ui.locale", ctx.locale.getLocale().active)),
          "walter-ui: remember language");
        ctx.effect(() => ctx.on("theme/change", (snap) => store.set("walter-ui.theme", snap.preference)),
          "walter-ui: remember appearance");
      }, 1500);
      ctx.effect(() => () => clearTimeout(timer), "walter-ui: defaults");
    }

    return { apply, inject };
  }
});
