// Walter face for the DSH web GUI — host half.
// Publishes the instance's display settings and the French dictionaries to the page, the palette/typography
// stylesheet before first paint, and a tiny script that renames the tab and its icon. The browser half
// (client.js) fills the brand slots, registers the French language and the colour layer.
// Neutral software: the name, greeting and default language come from the Loader config (instance patch).
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const read = (name) => readFileSync(join(here, name), 'utf8')

const DEFAULTS = { name: 'Walter', tagline: '', defaultLocale: 'fr', defaultTheme: 'dark' }

function favicon(name) {
  const letter = (name.trim()[0] || 'W').toUpperCase().replace(/[<>&"']/g, '')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#000000"/>`
    + `<rect x="3" y="3" width="58" height="58" rx="12" fill="none" stroke="#01B7FF" stroke-width="3"/>`
    + `<text x="32" y="45" text-anchor="middle" font-family="Didot,Bodoni 72,Georgia,serif" font-weight="700" font-size="38" fill="#e6edf2">${letter}</text></svg>`
  return 'data:image/svg+xml,' + encodeURIComponent(svg)
}

export const inject = []

export function apply(ctx, config = {}) {
  const cfg = { ...DEFAULTS, ...(config || {}) }
  const brand = String(cfg.name)
  // Dictionaries are stored with a %BRAND% marker so the software stays neutral; the instance names itself.
  const fr = JSON.parse(read('locales/fr.json').replaceAll('%BRAND%', brand.replace(/["\\]/g, '')))
  const css = read('style.css')
  if (css.includes('</style')) throw new Error('dsh-web-ui: style.css must not contain </style')
  const state = { name: brand, tagline: String(cfg.tagline || ''), defaultLocale: cfg.defaultLocale,
    defaultTheme: cfg.defaultTheme, icon: favicon(brand), fr }
  const boot = `(function(){var w=window.__WALTER_UI__;if(!w)return;`
    + `var fix=function(){var t=document.title;if(t.indexOf('DeepSeek Harness')>=0)document.title=t.split('DeepSeek Harness').join(w.name);};`
    + `var el=document.querySelector('title');if(el){new MutationObserver(fix).observe(el,{childList:true,characterData:true,subtree:true});}`
    + `document.title=w.name;fix();`
    + `document.querySelectorAll('link[rel~="icon"]').forEach(function(l){l.href=w.icon;l.removeAttribute('media');});`
    + `if(w.defaultLocale)document.documentElement.lang=w.defaultLocale;})();`
  ctx.on('webserver/index-inject', (table) => {
    table.push({ kind: 'global', name: '__WALTER_UI__', value: state })
    table.push({ kind: 'style', text: css })
    table.push({ kind: 'script', placement: 'body', text: boot })
  })
}
