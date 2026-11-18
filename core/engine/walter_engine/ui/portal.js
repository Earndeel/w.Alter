// Présentation seulement. app.js (le moteur) possède sessions, messages et autorisations ;
// ce fichier ne fait que refléter son état dans la barre d'onglets et le volet Documents.
const $ = (id) => document.getElementById(id);
const thread = $('thread');

/* Onglet ouvert : il y en a toujours exactement un raccordé au cadre.
   Brouillon (aucune conversation, aucun panneau) → l'onglet « Nouvelle conversation ». */
function reflectActiveTab() {
  const open = document.querySelector('#sessions li.active, #panels li.active');
  $('new-chat').classList.toggle('active', !open);
  if (open) open.setAttribute('aria-current', 'page');
  for (const li of document.querySelectorAll('#sessions li, #panels li')) if (li !== open) li.removeAttribute('aria-current');
}

/* Recherche dans les conversations */
function filterSessions() {
  const q = $('portal-search').value.trim().toLocaleLowerCase('fr');
  let shown = 0;
  for (const li of $('sessions').children) {
    const t = li.querySelector('.t');
    if (!t) continue;
    li.hidden = !!q && !t.textContent.toLocaleLowerCase('fr').includes(q);
    if (!li.hidden) shown++;
  }
  let none = $('portal-no-match');
  if (q && !shown) {
    if (!none) { none = document.createElement('li'); none.id = 'portal-no-match'; none.className = 'empty'; $('sessions').append(none); }
    none.textContent = 'Aucune conversation ne correspond';
  } else if (none) none.remove();
}
$('portal-search').addEventListener('input', filterSessions);
$('portal-search').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.currentTarget.value = ''; filterSessions(); }
  if (e.key === 'Enter') { const first = [...$('sessions').children].find((li) => !li.hidden && li.querySelector('.t')); if (first) first.click(); }
});
$('new-chat').addEventListener('click', () => { $('portal-search').value = ''; filterSessions(); });

/* Panneaux et liens : visibles seulement s'il y en a. Description des liens en infobulle. */
function reflectConfiguration() {
  $('panels-wrap').hidden = !$('panels').children.length;
  $('links-wrap').hidden = !$('links').children.length;
  for (const a of $('links').querySelectorAll('a.link')) {
    const small = a.querySelector('small');
    if (small && !a.title) a.title = small.textContent;
  }
}

/* Noms d'outils lisibles : « mcp__walter__walter_browse » → « walter_browse » */
function tidyTools(root) {
  for (const nm of root.querySelectorAll('.card.tool .nm:not([data-tidy])')) {
    nm.dataset.tidy = '1';
    const full = nm.textContent;
    const short = full.replace(/^mcp__.+?__/, '');
    if (short !== full) { nm.textContent = short; nm.title = full; }
  }
}

/* Volet Documents : livrables et liens cités, lus dans ce que le moteur a déjà affiché. */
const inspector = $('portal-inspector');
const toggle = $('portal-toggle-documents');
function documents(open, focus = false) {
  inspector.hidden = !open;
  toggle.setAttribute('aria-expanded', String(open));
  if (open && focus) $('portal-close-documents').focus();
  try { localStorage.setItem('walter.docs', open ? '1' : '0'); } catch (_) { /* ok */ }
}
toggle.addEventListener('click', () => documents(inspector.hidden, true));
$('portal-close-documents').addEventListener('click', () => { documents(false); toggle.focus(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !inspector.hidden) { documents(false); toggle.focus(); } });
let wasOpen = false; try { wasOpen = localStorage.getItem('walter.docs') === '1'; } catch (_) { /* ok */ }
documents(wasOpen && window.innerWidth > 1180);

function renderLinks(container, empty, anchors) {
  const seen = new Set();
  const frag = document.createDocumentFragment();
  for (const original of anchors) {
    let url; try { url = new URL(original.href, location.href); } catch (_) { continue; }
    if (!['http:', 'https:'].includes(url.protocol) || seen.has(url.href)) continue;
    seen.add(url.href);
    const a = document.createElement('a');
    a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.textContent = original.textContent.trim() || url.hostname;
    a.title = url.href;
    frag.append(a);
  }
  container.replaceChildren(frag);
  empty.hidden = seen.size > 0;
  return seen.size;
}
function reflectDocuments() {
  const n = renderLinks($('portal-deliverables'), $('portal-deliverables-empty'), thread.querySelectorAll('.card.deliv a'))
    + renderLinks($('portal-sources'), $('portal-sources-empty'), thread.querySelectorAll('.msg.assistant .bubble a'));
  const c = $('portal-doc-count');
  c.hidden = !n; c.textContent = String(n);
  const inPanel = !$('panel-view').hidden;
  toggle.hidden = inPanel;
  if (inPanel && !inspector.hidden) inspector.hidden = true;
}

/* Observateurs (un seul passage par image) */
let queued = false;
function refresh() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    reflectActiveTab(); filterSessions(); reflectConfiguration(); tidyTools(thread); reflectDocuments();
  });
}
const mo = new MutationObserver(refresh);
mo.observe($('sessions'), { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
mo.observe($('panels'), { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
mo.observe($('links'), { childList: true });
mo.observe(thread, { childList: true, subtree: true, characterData: true });
mo.observe($('panel-view'), { attributes: true, attributeFilter: ['hidden'] });
window.addEventListener('hashchange', refresh);
refresh();

/* Raccourci : ⌘K / Ctrl+K → recherche */
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    if (window.innerWidth <= 760) $('menu-btn').click();
    $('portal-search').focus();
  }
});
document.body.dataset.walterPortal = 'v4';
