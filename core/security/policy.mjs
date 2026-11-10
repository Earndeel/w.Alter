// Walter's one execution policy — JS twin of walter_security/policy.py (lot E3). Same policy.json, same decisions:
// both are run against tests/vectors.json. Used by the engine's policy plugin (core/engine/plugins/policy).
import { readFileSync, realpathSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const POLICY = join(dirname(fileURLToPath(import.meta.url)), 'policy.json');
export const ORDER = ['allow', 'check', 'ask', 'deny'];
export const strictest = (...ds) => ds.reduce((a, b) => (ORDER.indexOf(b) > ORDER.indexOf(a) ? b : a), 'allow');

const esc = (s) => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
function globRe(pattern) {
  let out = '', i = 0;
  if (pattern.startsWith('**/')) { out = '(?:^|.*/)'; i = 3; }
  while (i < pattern.length) {
    if (pattern.startsWith('**', i)) { out += '.*'; i += 2; }
    else if (pattern[i] === '*') { out += '[^/]*'; i += 1; }
    else { out += esc(pattern[i]); i += 1; }
  }
  return new RegExp(`${out}$`);
}
const nameRe = (p) => new RegExp(`^${p.split('*').map(esc).join('.*')}$`);

function instanceRoot() {
  if (process.env.WALTER_INSTANCE_ROOT) return process.env.WALTER_INSTANCE_ROOT;
  try { return readFileSync('/etc/walter/instance', 'utf8').trim(); } catch { return ''; }
}

export function load(path = POLICY, root = instanceRoot()) {
  const p = JSON.parse(readFileSync(path, 'utf8'));
  const sub = (g) => (root ? g.replace('@instance', root.replace(/\/$/, '')) : g);
  const never = p.never;
  p._neverPaths = never.paths.filter((g) => root || !g.includes('@instance')).map((g) => [g, globRe(sub(g))]);
  p._pathAllow = (never.path_allow || []).map(globRe);
  p._neverCmds = (never.commands || []).map((c) => [c, new RegExp(c)]);
  p._classes = Object.entries(p.classes).map(([cls, names]) => [cls, names.map(nameRe)]);
  return p;
}

const strings = (v) => (typeof v === 'string' ? [v] : Array.isArray(v) ? v.flatMap(strings)
  : v && typeof v === 'object' ? Object.values(v).flatMap(strings) : []);
const TOKEN = /[\s'"`;|&<>()=,]+/;

function candidates(text, home) {
  const out = [];
  for (let tok of text.split(TOKEN)) {
    if (!tok || (!tok.includes('/') && !tok.startsWith('.'))) continue;
    if (tok.startsWith('~/')) tok = home.replace(/\/$/, '') + tok.slice(1);
    out.push(tok);
    if (tok.startsWith('/')) {
      try { const real = realpathSync(tok); if (real !== tok) out.push(real); } catch { /* not there: the literal path is judged */ }
    }
  }
  return out;
}

function prot(p, path) {
  if (p._pathAllow.some((r) => r.test(path))) return null;
  const hit = p._neverPaths.find(([, r]) => r.test(path));
  return hit ? hit[0] : null;
}

export function classify(p, tool) {
  const hit = p._classes.find(([, pats]) => pats.some((r) => r.test(tool)));
  return hit ? hit[0] : 'unknown';
}

const REASONS = { allow: '', check: "contrôle de divulgation avant l'envoi",
  ask: 'action sensible : accord de Monsieur requis', deny: 'refusé par la politique de cette porte' };

export function decide(p, { tool, args, iface = 'api', depth = 0, home = '/root' }) {
  args = args && typeof args === 'object' && !Array.isArray(args) ? args : {};
  if (tool === 'mcp__walter__walter_call' && args.tool) { tool = `mcp__walter__${args.tool}`; args = args.arguments || {}; }
  const cls = classify(p, tool);
  const base = { class: cls, tool };
  const maxDepth = Number(p.never.max_depth ?? 3);
  if (cls === 'delegate' && depth >= maxDepth) {
    return { ...base, decision: 'deny', rule: 'never.max_depth', reason: `délégation refusée : profondeur maximale (${maxDepth}) atteinte` };
  }
  const texts = cls === 'shell' ? strings(args) : (p.path_keys || []).flatMap((k) => strings(args[k]));
  for (const text of texts) {
    for (const cand of candidates(text, home)) {
      const g = prot(p, cand);
      if (g) return { ...base, decision: 'deny', rule: `never.paths:${g}`,
        reason: "refusé : fichier de secrets ou d'accès (jamais lu ni écrit par un agent ; passer par walter-secret exec)" };
    }
  }
  if (cls === 'shell') {
    for (const text of (p.shell_text_keys || []).flatMap((k) => strings(args[k]))) {
      const hit = p._neverCmds.find(([, r]) => r.test(text));
      if (hit) return { ...base, decision: 'deny', rule: `never.commands:${hit[0]}`,
        reason: 'refusé : commande qui révèle un secret (utiliser walter-secret exec --bind, valeurs jamais dans le modèle)' };
    }
  }
  const presetName = p.interfaces[iface] || 'api';
  const preset = p.presets[presetName];
  let decision = preset[cls] ?? preset.unknown ?? 'ask';
  let rule = `preset.${presetName}.${cls}`;
  if (depth > 0) {
    const child = p.presets.child[cls] ?? p.presets.child.unknown ?? 'ask';
    if (ORDER.indexOf(child) > ORDER.indexOf(decision)) { decision = child; rule = `preset.child.${cls}`; }
  }
  return { ...base, decision, rule, reason: REASONS[decision] };
}
