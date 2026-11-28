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


/* Barre d'icônes du cadre extérieur : Conversations, puis un bouton par panneau et par lien.
   Elle ne fait que relayer les éléments déjà rendus par app.js (aucune seconde liste). */
const ICON = {
  panel: '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/></svg>',
  link: '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4.5h4.5a2.5 2.5 0 0 1 2.5 2.5v12.5a2 2 0 0 0-2-2H5zM19 4.5h-4.5A2.5 2.5 0 0 0 12 7v12.5a2 2 0 0 1 2-2h5z"/></svg>',
};
function railButton(label, html, onClick) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'rail-btn'; b.title = label; b.setAttribute('aria-label', label);
  b.innerHTML = html; b.addEventListener('click', onClick);
  return b;
}
function reflectRail() {
  const panels = [...$('panels').children];
  $('rail-panels').replaceChildren(...panels.map((li) => {
    const b = railButton(li.textContent.trim(), ICON.panel, () => li.click());
    b.classList.toggle('active', li.classList.contains('active') && !$('panel-view').hidden);
    return b;
  }));
  const links = [...$('links').querySelectorAll('a.link')];
  $('rail-links').replaceChildren(...links.map((a) => {
    const label = a.firstChild ? a.firstChild.textContent.trim() : a.textContent.trim();
    const b = railButton(label + ' ↗', ICON.link, () => window.open(a.href, '_blank', 'noopener'));
    return b;
  }));
  $('rail-chat').classList.toggle('active', $('panel-view').hidden);
}
$('rail-chat').addEventListener('click', () => {
  if ($('panel-view').hidden) { $('input').focus(); return; }
  let last = null; try { last = localStorage.getItem('walter.last'); } catch (_) { /* ok */ }
  if (last && document.querySelector('#sessions li .t')) location.hash = '#/c/' + last; else $('new-chat').click();
});

/* Masquer / afficher la barre latérale (ordinateur) ; sur téléphone, ouvre le tiroir. */
function side(open) {
  document.body.classList.toggle('side-closed', !open);
  const t = $('portal-toggle-side');
  t.setAttribute('aria-expanded', String(open));
  t.title = open ? 'Masquer la barre latérale' : 'Afficher la barre latérale';
  t.setAttribute('aria-label', t.title);
  try { localStorage.setItem('walter.side', open ? '1' : '0'); } catch (_) { /* ok */ }
}
$('portal-toggle-side').addEventListener('click', () => side(document.body.classList.contains('side-closed')));
let sideOpen = true; try { sideOpen = localStorage.getItem('walter.side') !== '0'; } catch (_) { /* ok */ }
side(sideOpen);

/* Observateurs (un seul passage par image) */
let queued = false;
function refresh() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    reflectActiveTab(); filterSessions(); reflectConfiguration(); reflectRail(); tidyTools(thread); reflectDocuments();
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
/* Bouton d'envoi rond : app.js y écrit « Envoyer » ou « Ajouter » (pendant un tour) ; on le reflète en infobulle. */
const send = $('send');
const label = () => { send.setAttribute('aria-label', send.textContent); send.title = send.textContent; send.classList.toggle('steer', send.textContent !== 'Envoyer'); };
new MutationObserver(label).observe(send, { childList: true, characterData: true, subtree: true });
label();
/* Le nom affiché par app.js (#brand, cadre extérieur) est recopié dans le tiroir du téléphone. */
const brandDrawer = () => { $('brand-drawer').textContent = $('brand').textContent; };
new MutationObserver(brandDrawer).observe($('brand'), { childList: true, characterData: true, subtree: true });
brandDrawer();
document.body.dataset.walterPortal = 'v7';
