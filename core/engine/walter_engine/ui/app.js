// W.Alter — interface web du Walter Engine. JS pur, sans dépendance.

/* ───────── Markdown sûr ───────── */
export function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function emph(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    .replace(/~~(.+?)~~/g, '<del>$1</del>')
    .replace(/(^|[^*\w])\*([^*\s](?:[^*]*?[^*\s])?)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/(^|[^_\w])_([^_\s](?:[^_]*?[^_\s])?)_(?![_\w])/g, '$1<em>$2</em>');
}

export function inline(src) {
  const stash = [];
  const put = (h) => '\u0000' + (stash.push(h) - 1) + '\u0000';
  let s = String(src).replace(/`([^`\n]+)`/g, (m, c) => put('<code>' + esc(c) + '</code>'));
  s = esc(s);
  s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, label, url) =>
    put('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + emph(label) + '</a>'));
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<]*[^\s<.,;:!?)\]])/g, (m, pre, url) =>
    pre + put('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + '</a>'));
  s = emph(s);
  for (let i = 0; i < 5 && s.indexOf('\u0000') >= 0; i++)
    s = s.replace(/\u0000(\d+)\u0000/g, (m, n) => stash[+n]);
  return s;
}

const RE = {
  fence: /^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]*)\s*$/,
  head: /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/,
  hr: /^\s{0,3}([-*_])(\s*\1){2,}\s*$/,
  quote: /^\s{0,3}>\s?(.*)$/,
  li: /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/,
  tsep: /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/,
};

function cells(line) {
  let t = line.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|')) t = t.slice(0, -1);
  return t.split('|').map((c) => c.trim());
}

function codeBlock(lang, lines) {
  return '<div class="codeblock"><div class="codehead"><span>' + esc(lang || 'code') +
    '</span><button type="button" class="copy">Copier</button></div><pre><code>' +
    esc(lines.join('\n')) + '</code></pre></div>';
}

function renderList(items, i, base) {
  // items: [{indent, ordered, text}] ; renvoie [html, nextIndex]
  const ordered = items[i].ordered;
  const tag = ordered ? 'ol' : 'ul';
  let html = '<' + tag + '>';
  while (i < items.length && items[i].indent >= base) {
    if (items[i].indent > base) {
      const [sub, ni] = renderList(items, i, items[i].indent);
      html = html.replace(/<\/li>$/, sub + '</li>');
      i = ni;
      continue;
    }
    if (items[i].ordered !== ordered) break;
    html += '<li>' + inline(items[i].text) + '</li>';
    i++;
  }
  return [html + '</' + tag + '>', i];
}

export function renderMarkdown(text) {
  const lines = String(text == null ? '' : text).replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    let m;
    if (!line.trim()) { i++; continue; }
    if ((m = RE.fence.exec(line))) {
      const mark = m[1], lang = m[2], buf = [];
      i++;
      while (i < lines.length && !(lines[i].trim().startsWith(mark[0].repeat(mark.length)) && /^\s*[`~]+\s*$/.test(lines[i]))) buf.push(lines[i++]);
      i++;
      out.push(codeBlock(lang, buf));
      continue;
    }
    if ((m = RE.head.exec(line))) { const n = m[1].length; out.push('<h' + n + '>' + inline(m[2]) + '</h' + n + '>'); i++; continue; }
    if (RE.hr.test(line)) { out.push('<hr>'); i++; continue; }
    if (RE.quote.test(line)) {
      const buf = [];
      while (i < lines.length && (m = RE.quote.exec(lines[i]))) { buf.push(m[1]); i++; }
      out.push('<blockquote>' + renderMarkdown(buf.join('\n')) + '</blockquote>');
      continue;
    }
    if (line.includes('|') && i + 1 < lines.length && RE.tsep.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const head = cells(line);
      i += 2;
      let h = '<div class="tablewrap"><table><thead><tr>' + head.map((c) => '<th>' + inline(c) + '</th>').join('') + '</tr></thead><tbody>';
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        h += '<tr>' + cells(lines[i]).map((c) => '<td>' + inline(c) + '</td>').join('') + '</tr>';
        i++;
      }
      out.push(h + '</tbody></table></div>');
      continue;
    }
    if (RE.li.test(line)) {
      const items = [];
      while (i < lines.length) {
        const mm = RE.li.exec(lines[i]);
        if (mm) { items.push({ indent: mm[1].replace(/\t/g, '    ').length, ordered: /\d/.test(mm[2]), text: mm[3] }); i++; }
        else if (lines[i].trim() && /^\s{2,}\S/.test(lines[i]) && items.length) { items[items.length - 1].text += ' ' + lines[i].trim(); i++; }
        else break;
      }
      const base = Math.min(...items.map((x) => x.indent));
      let k = 0;
      while (k < items.length) { const [h, nk] = renderList(items, k, base); out.push(h); k = nk > k ? nk : k + 1; }
      continue;
    }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !RE.fence.test(lines[i]) && !RE.head.test(lines[i]) &&
      !RE.quote.test(lines[i]) && !RE.hr.test(lines[i]) && !(RE.li.test(lines[i]) && buf.length)) buf.push(lines[i++]);
    if (!buf.length) { buf.push(lines[i++]); }
    out.push('<p>' + buf.map(inline).join('<br>') + '</p>');
  }
  return out.join('');
}

/* ───────── Application ───────── */
if (typeof document !== 'undefined') main();

function main() {
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  const S = {
    config: { name: 'W.Alter', tagline: 'Bonjour Monsieur. Que puis-je faire pour vous ?', panels: [], links: [] },
    sessions: [], sid: null, busy: false, lastSeq: 0, firstSeq: 0,
    es: null, esTries: 0, esTimer: null,
    tools: new Map(), approvals: new Map(), pending: new Map(), // request_id -> session_id
    live: null, liveText: '', liveRaf: 0, panel: null, opening: 0,
  };
  const EVENT_TYPES = ['turn.started', 'turn.ended', 'message.user', 'message.delta', 'message.assistant',
    'tool.called', 'tool.result', 'notice', 'approval.requested', 'approval.answered', 'deliverable', 'session.title'];

  /* API */
  class ApiError extends Error { constructor(status, code, msg) { super(msg); this.status = status; this.code = code; } }
  async function api(body) {
    let r;
    try {
      r = await fetch('/v1', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: 1, ...body }) });
    } catch (e) { throw new ApiError(0, 'network', 'Connexion impossible'); }
    let data = null;
    try { data = await r.json(); } catch (e) { /* vide */ }
    if (!r.ok) {
      const err = new ApiError(r.status, data?.error?.code, data?.error?.message || ('Erreur ' + r.status));
      if (r.status === 401) showBanner('Session expirée — rechargez la page', true);
      throw err;
    }
    return data || {};
  }
  let bannerTimer = 0;
  function showBanner(msg, sticky) {
    const b = $('banner'); b.textContent = msg; b.hidden = false;
    clearTimeout(bannerTimer);
    if (!sticky) bannerTimer = setTimeout(() => { b.hidden = true; }, 8000);
  }
  const fail = (e) => { if (e.status !== 401) showBanner(e.status === 0 ? 'Connexion perdue — nouvelle tentative…' : 'Erreur : ' + e.message); };

  /* Scroll */
  const msgs = $('messages'), thread = $('thread');
  const nearBottom = () => msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 120;
  const toBottom = () => { msgs.scrollTop = msgs.scrollHeight; };
  function withScroll(fn) { const stick = nearBottom(); fn(); if (stick) toBottom(); }

  /* Rendu des événements */
  function bubble(role, html, cls) {
    const m = el('div', 'msg ' + role + (cls ? ' ' + cls : ''));
    const b = el('div', 'bubble');
    if (html != null) b.innerHTML = html; // html toujours issu de renderMarkdown/esc
    m.appendChild(b);
    return [m, b];
  }
  function shorten(v, n) {
    let s = typeof v === 'string' ? v : JSON.stringify(v);
    if (s == null) s = '';
    s = s.replace(/\s+/g, ' ');
    return s.length > n ? s.slice(0, n) + '…' : s;
  }
  function toolCard(ev) {
    const d = el('details', 'card tool');
    const sum = el('summary');
    sum.append(el('span', 'nm', ev.name || 'outil'), el('span', 'ar', shorten(ev.args_preview, 160)));
    const st = el('span', 'st'); st.appendChild(el('span', 'spinner'));
    sum.appendChild(st);
    d.appendChild(sum);
    const pre = el('pre', null, '(en cours…)');
    d.appendChild(pre);
    return { d, st, pre, done: false, args: ev.args_preview };
  }
  function finishTool(t, ok, preview) {
    t.done = true; t.st.textContent = ok ? '✓' : '✗'; t.st.className = 'st ' + (ok ? 'ok' : 'ko');
    t.pre.textContent = (preview == null || preview === '') ? '(vide)' : (typeof preview === 'string' ? preview : JSON.stringify(preview, null, 2));
  }
  function approvalCard(ev) {
    const c = el('div', 'card approval');
    const body = el('div', 'body');
    body.append(el('div', null, 'Autorisation demandée'), el('div', 'nm', ev.tool || ''), el('div', null, ev.summary || ''));
    const acts = el('div', 'acts');
    const ok = el('button', 'btn primary sm', 'Autoriser une fois'); ok.type = 'button';
    const no = el('button', 'btn danger sm', 'Refuser'); no.type = 'button';
    const answer = async (dec) => {
      ok.disabled = no.disabled = true;
      try { await api({ op: 'approval.answer', request_id: ev.request_id, decision: dec }); }
      catch (e) { ok.disabled = no.disabled = false; fail(e); }
    };
    ok.onclick = () => answer('allow_once'); no.onclick = () => answer('deny');
    acts.append(ok, no); body.appendChild(acts); c.appendChild(body);
    return { c, acts, body };
  }
  function safeUrl(u) {
    try { const x = new URL(u, location.href); return (x.origin === location.origin || /^https?:$/.test(x.protocol)) ? x.href : '#'; } catch (e) { return '#'; }
  }

  function dropLive() {
    if (S.live) { S.live.remove(); S.live = null; S.liveText = ''; }
  }
  function setBusy(b) {
    S.busy = b;
    $('working').hidden = !b; $('stop').hidden = !b; $('busy-dot').hidden = !b;
    $('send').textContent = b ? 'Ajouter' : 'Envoyer';
    if (!b) {
      dropLive();
      for (const t of S.tools.values()) if (!t.done) { t.done = true; t.st.textContent = '–'; t.pre.textContent = '(interrompu)'; }
    }
    const s = S.sessions.find((x) => x.session_id === S.sid); if (s) { s.busy = b; renderSessions(); }
  }

  const ENDLABEL = { cancelled: 'Tour arrêté', budget_exhausted: 'Budget épuisé', error: 'Erreur pendant le tour', interrupted: 'Tour interrompu' };

  // live=true : événement en direct (pilote busy), false : relecture de l'historique
  function renderEvent(ev, parent, live) {
    switch (ev.type) {
      case 'turn.started': if (live) setBusy(true); break;
      case 'turn.ended': {
        if (live) setBusy(false);
        if (ENDLABEL[ev.status]) parent.appendChild(el('div', 'endnote', ENDLABEL[ev.status] + (ev.reason ? ' (' + ev.reason + ')' : '')));
        break;
      }
      case 'message.user': {
        const [m, b] = bubble('user', null, ev.source === 'steer' ? 'steer' : '');
        b.textContent = ev.text || '';
        parent.appendChild(m); break;
      }
      case 'message.delta': {
        if (!live || !S.busy) break; // deltas rejoués hors tour : ignorés
        if (!S.live) { const [m, b] = bubble('assistant', ''); b.classList.add('live'); parent.appendChild(m); S.live = m; S.liveText = ''; }
        S.liveText += ev.text || '';
        if (!S.liveRaf) S.liveRaf = requestAnimationFrame(() => {
          S.liveRaf = 0;
          if (S.live) withScroll(() => { S.live.firstChild.innerHTML = renderMarkdown(S.liveText); });
        });
        break;
      }
      case 'message.assistant': {
        if (live) dropLive();
        if (ev.text && ev.text.trim()) {
          const [m, b] = bubble('assistant', renderMarkdown(ev.text));
          if (ev.model) b.title = ev.model;
          parent.appendChild(m);
        }
        break;
      }
      case 'tool.called': {
        const t = toolCard(ev); S.tools.set(ev.call_id, t); parent.appendChild(t.d); break;
      }
      case 'tool.result': {
        const t = S.tools.get(ev.call_id);
        if (t) finishTool(t, ev.ok !== false, ev.preview);
        else { const t2 = toolCard({ name: 'outil', args_preview: '' }); finishTool(t2, ev.ok !== false, ev.preview); S.tools.set(ev.call_id, t2); parent.appendChild(t2.d); }
        break;
      }
      case 'notice': parent.appendChild(el('div', 'notice', ev.text || '')); break;
      case 'approval.requested': {
        const a = approvalCard(ev); S.approvals.set(ev.request_id, a); parent.appendChild(a.c);
        S.pending.set(ev.request_id, S.sid); renderSessions(); break;
      }
      case 'approval.answered': {
        const a = S.approvals.get(ev.request_id);
        if (a) { a.acts.remove(); a.body.appendChild(el('div', 'res', ev.decision === 'allow_once' || ev.decision === 'allow' ? 'Autorisé' : 'Refusé')); a.c.style.borderColor = 'var(--blue)'; }
        S.pending.delete(ev.request_id); renderSessions(); break;
      }
      case 'deliverable': {
        const c = el('div', 'card deliv'); const a = el('a');
        a.href = safeUrl(ev.url || '#'); a.target = '_blank'; a.rel = 'noopener noreferrer';
        a.append(el('span', null, '📎'), el('span', null, ev.title || ev.path || 'Livrable'));
        c.appendChild(a); parent.appendChild(c); break;
      }
      case 'session.title': {
        const s = S.sessions.find((x) => x.session_id === S.sid);
        if (s) { s.title = ev.title; renderSessions(); }
        $('title').textContent = ev.title || 'Conversation'; break;
      }
      default: break;
    }
  }

  function handleLive(ev) {
    if (ev.seq != null) { if (ev.seq <= S.lastSeq) return; S.lastSeq = ev.seq; }
    $('welcome').hidden = true;
    withScroll(() => renderEvent(ev, thread, true));
  }

  /* SSE */
  function closeEs() { if (S.es) { S.es.close(); S.es = null; } clearTimeout(S.esTimer); }
  function openEs(sid) {
    closeEs();
    const es = new EventSource('/v1/events?session_id=' + encodeURIComponent(sid) + '&since_seq=' + S.lastSeq, { withCredentials: true });
    S.es = es;
    const onmsg = (m) => {
      S.esTries = 0;
      let ev; try { ev = JSON.parse(m.data); } catch (e) { return; }
      if (sid === S.sid) handleLive(ev);
    };
    for (const t of EVENT_TYPES) es.addEventListener(t, onmsg);
    es.onmessage = onmsg;
    es.onopen = () => { S.esTries = 0; if (document.getElementById('banner').textContent.startsWith('Connexion perdue')) $('banner').hidden = true; };
    es.onerror = async () => {
      es.close(); if (S.es === es) S.es = null;
      S.esTries++;
      if (S.esTries >= 2) { try { await api({ op: 'session.list', interface: 'web' }); showBanner('Connexion perdue — nouvelle tentative…', true); } catch (e) { fail(e); } }
      if (sid !== S.sid) return;
      S.esTimer = setTimeout(() => { if (sid === S.sid) openEs(sid); }, Math.min(15000, 500 * 2 ** Math.min(S.esTries, 5)));
    };
  }

  /* Sessions */
  function renderSessions() {
    const ul = $('sessions'); ul.textContent = '';
    if (!S.sessions.length) ul.appendChild(el('li', 'empty', 'Aucune conversation'));
    const withAppr = new Set(S.pending.values());
    for (const s of S.sessions) {
      const li = el('li', s.session_id === S.sid && !S.panel ? 'active' : '');
      if (withAppr.has(s.session_id)) li.appendChild(el('span', 'd appr'));
      else if (s.busy) li.appendChild(el('span', 'd busy'));
      li.appendChild(el('span', 't', s.title || 'Nouvelle conversation'));
      const r = el('button', 'ren', '✎'); r.type = 'button'; r.title = 'Renommer'; r.setAttribute('aria-label', 'Renommer');
      r.onclick = (e) => { e.stopPropagation(); rename(s); };
      li.appendChild(r);
      li.onclick = () => { go('#/c/' + s.session_id); closeDrawer(); };
      ul.appendChild(li);
    }
  }
  async function rename(s) {
    const t = prompt('Nom de la conversation', s.title || '');
    if (t == null || !t.trim()) return;
    try { await api({ op: 'session.rename', session_id: s.session_id, title: t.trim() }); s.title = t.trim(); renderSessions(); if (s.session_id === S.sid) $('title').textContent = s.title; }
    catch (e) { fail(e); }
  }
  async function refreshSessions() {
    try {
      const r = await api({ op: 'session.list', interface: 'web' });
      S.sessions = r.sessions || [];
      const cur = S.sessions.find((x) => x.session_id === S.sid);
      if (cur) $('title').textContent = cur.title || 'Conversation';
      renderSessions();
    } catch (e) { fail(e); }
  }
  async function refreshApprovals() {
    try {
      const r = await api({ op: 'approval.list' });
      S.pending = new Map((r.approvals || []).map((a) => [a.request_id, a.session_id]));
      renderSessions();
    } catch (e) { /* silencieux */ }
  }

  function resetThread() {
    thread.textContent = ''; S.tools.clear(); S.approvals.clear(); S.live = null; S.liveText = '';
    S.lastSeq = 0; S.firstSeq = 0; const old = $('more'); if (old) old.remove();
  }
  function addMore() {
    const old = $('more'); if (old) old.remove();
    if (S.firstSeq > 1) {
      const b = el('button', 'btn sm', 'Charger les messages précédents'); b.id = 'more'; b.type = 'button';
      b.onclick = loadOlder; msgs.insertBefore(b, thread);
    }
  }
  async function loadOlder() {
    const sid = S.sid;
    try {
      const r = await api({ op: 'session.history', session_id: sid, limit: 200, before_seq: S.firstSeq });
      if (sid !== S.sid) return;
      const frag = document.createDocumentFragment();
      for (const ev of r.events || []) renderEvent(ev, frag, false);
      const h = msgs.scrollHeight, top = msgs.scrollTop;
      thread.insertBefore(frag, thread.firstChild);
      msgs.scrollTop = top + (msgs.scrollHeight - h);
      S.firstSeq = r.first_seq || 0; addMore();
    } catch (e) { fail(e); }
  }

  async function openSession(sid) {
    const token = ++S.opening;
    closeEs(); resetThread(); S.sid = sid; S.panel = null; showChat();
    $('welcome').hidden = true; setBusy(false);
    try { localStorage.setItem('walter.last', sid); } catch (e) { /* ok */ }
    const cur = S.sessions.find((x) => x.session_id === sid);
    $('title').textContent = cur?.title || 'Conversation'; renderSessions();
    try {
      const r = await api({ op: 'session.history', session_id: sid, limit: 200 });
      if (token !== S.opening) return;
      const evs = r.events || [];
      for (const ev of evs) { renderEvent(ev, thread, false); if (ev.seq != null && ev.seq > S.lastSeq) S.lastSeq = ev.seq; }
      S.lastSeq = Math.max(S.lastSeq, r.last_seq || 0); S.firstSeq = r.first_seq || 0;
      addMore();
      if (!evs.length) $('welcome').hidden = false;
      setBusy(!!r.busy);
      toBottom();
      openEs(sid);
    } catch (e) {
      if (token !== S.opening) return;
      fail(e);
      if (e.status === 404) { try { localStorage.removeItem('walter.last'); } catch (x) { /* ok */ } newDraft(); }
    }
  }
  function newDraft() {
    ++S.opening; closeEs(); resetThread(); S.sid = null; S.panel = null; showChat(); setBusy(false);
    $('welcome').hidden = false; $('title').textContent = 'Nouvelle conversation'; renderSessions();
    if (location.hash) history.replaceState(null, '', location.pathname + location.search);
    $('input').focus();
  }
  const rid = () => { const a = 'abcdefghijklmnopqrstuvwxyz0123456789'; const b = crypto.getRandomValues(new Uint8Array(6)); return Array.from(b, (x) => a[x % 36]).join(''); };
  const convId = () => { const d = new Date(); const p = (n) => String(n).padStart(2, '0'); return 'c-' + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '-' + rid(); };
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : 'k-' + Date.now() + '-' + rid());

  /* Envoi */
  const input = $('input');
  function autogrow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, window.innerHeight * 0.4) + 'px'; }
  input.addEventListener('input', autogrow);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('composer').requestSubmit(); }
  });
  let sending = false;
  $('composer').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || sending) return;
    sending = true; $('send').disabled = true;
    try {
      let created = false;
      if (!S.sid) {
        const r = await api({ op: 'session.open', interface: 'web', conversation: convId(), principal: { kind: 'owner', id: 'owner' } });
        S.sid = r.session_id; created = true;
        S.sessions.unshift({ session_id: r.session_id, title: r.title || '', busy: false });
        try { localStorage.setItem('walter.last', S.sid); } catch (x) { /* ok */ }
        history.replaceState(null, '', '#/c/' + S.sid);
        $('welcome').hidden = true; renderSessions(); openEs(S.sid);
      }
      const op = S.busy && !created ? 'turn.steer' : 'turn.submit';
      await api({ op, session_id: S.sid, message: { text }, idempotency_key: uuid() });
      input.value = ''; autogrow();
      if (op === 'turn.submit') setBusy(true);
    } catch (err) { fail(err); }
    finally { sending = false; $('send').disabled = false; input.focus(); }
  });
  $('stop').onclick = async () => {
    try { await api({ op: 'turn.cancel', session_id: S.sid, reason: 'owner' }); } catch (e) { fail(e); }
  };

  /* Code : copier */
  thread.addEventListener('click', async (e) => {
    const b = e.target.closest('button.copy'); if (!b) return;
    const code = b.closest('.codeblock').querySelector('code').textContent;
    try { await navigator.clipboard.writeText(code); b.textContent = 'Copié'; }
    catch (x) {
      const ta = el('textarea'); ta.value = code; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); b.textContent = 'Copié'; } catch (y) { b.textContent = 'Échec'; }
      ta.remove();
    }
    setTimeout(() => { b.textContent = 'Copier'; }, 1500);
  });

  /* Navigation */
  function showChat() { $('chat').hidden = false; $('panel-view').hidden = true; $('panel-frame').removeAttribute('src'); renderPanels(); }
  function openPanel(p) {
    ++S.opening; closeEs(); S.panel = p.id; S.sid = null;
    $('chat').hidden = true; $('panel-view').hidden = false; $('panel-frame').src = p.path;
    $('title').textContent = p.label; $('busy-dot').hidden = true; renderSessions(); renderPanels();
  }
  function renderPanels() {
    const ul = $('panels'); ul.textContent = '';
    for (const p of S.config.panels || []) {
      const li = el('li', S.panel === p.id ? 'active' : ''); li.appendChild(el('span', 't', p.label));
      li.onclick = () => { go('#/p/' + p.id); closeDrawer(); }; ul.appendChild(li);
    }
  }
  function renderLinks() {
    const box = $('links'); box.textContent = ''; let sec = null;
    for (const l of S.config.links || []) {
      if (l.section !== sec) { sec = l.section; if (l.section_label) box.appendChild(el('div', 'link-sec', l.section_label)); }
      const a = el('a', 'link'); a.href = safeUrl(l.url); a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.appendChild(document.createTextNode(l.label || l.id));
      if (l.description) a.appendChild(el('small', null, l.description));
      box.appendChild(a);
    }
  }
  const go = (h) => { if (location.hash === h) route(); else location.hash = h; };
  function route() {
    const h = location.hash;
    let m;
    if ((m = /^#\/c\/(.+)$/.exec(h))) { const sid = decodeURIComponent(m[1]); if (sid !== S.sid || S.panel) openSession(sid); }
    else if ((m = /^#\/p\/(.+)$/.exec(h))) { const p = (S.config.panels || []).find((x) => x.id === decodeURIComponent(m[1])); if (p) openPanel(p); else newDraft(); }
    else if (S.sid || S.panel) newDraft();
  }
  window.addEventListener('hashchange', route);
  $('new-chat').onclick = () => { newDraft(); closeDrawer(); };
  const closeDrawer = () => { document.body.classList.remove('drawer'); $('scrim').hidden = true; };
  $('menu-btn').onclick = () => { document.body.classList.add('drawer'); $('scrim').hidden = false; };
  $('scrim').onclick = closeDrawer;

  /* Démarrage */
  (async function init() {
    try {
      const r = await fetch('/ui/config', { credentials: 'same-origin' });
      if (r.status === 401) showBanner('Session expirée — rechargez la page', true);
      else if (r.ok) Object.assign(S.config, await r.json());
    } catch (e) { /* valeurs par défaut */ }
    const c = S.config;
    document.title = c.name || 'W.Alter';
    $('brand').textContent = c.name || 'W.Alter'; $('welcome-name').textContent = c.name || 'W.Alter';
    $('welcome-tag').textContent = c.tagline || 'Bonjour Monsieur. Que puis-je faire pour vous ?';
    renderPanels(); renderLinks();
    await refreshSessions(); refreshApprovals();
    if (!/^#\/[cp]\//.test(location.hash)) {
      let last = null; try { last = localStorage.getItem('walter.last'); } catch (e) { /* ok */ }
      if (last && S.sessions.some((s) => s.session_id === last)) { history.replaceState(null, '', '#/c/' + last); }
    }
    if (location.hash) route(); else newDraft();
    setInterval(() => { if (!document.hidden) { refreshSessions(); refreshApprovals(); } }, 15000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && S.sid && !S.es) openEs(S.sid); });
  })();
}
