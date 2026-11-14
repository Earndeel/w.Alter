---
name: flask-dashboard-tailscale
category: devops
description: Deploy real-time Flask dashboards on Oracle Cloud ARM via Tailscale + systemd, with SQLite backend and auto-restart.
tags: [flask, tailscale, systemd, dashboard, sqlite, real-time]
---

# Flask Dashboard avec Tailscale + systemd

Expose une application Flask (lecture SQLite temps reel) via Tailscale avec un service systemd permanent.

## Quand utiliser

- Dashboard qui doit lire la DB en temps reel (pas statique)
- Acces via Tailscale existant (IP stable, pas de DNS a configurer)
- Cloudflare Pages ne marche PAS (c'est du statique uniquement)
- Cloudflare tunnel quick NE PAS utiliser (DNS unreliable, URL change a chaque reboot)

## Architecture

```
Flask (localhost:5001) → Tailscale IP → Dashboard sur tous les devices
                              ↓
                        SQLite DB (lecture directe)
                              ↓
                        polling JS toutes les 10s
```

## Etapes

### 1. Creer le serveur Flask

**IMPORTANT : Architecture statique obligatoire.** Ne JAMAIS embedder du HTML/JS inline dans du Python via `render_template_string` ou des chaines `"""..."""`. Les sequences d'echappement JS (`\n`, `\\`, guillemets imbriques) sont systematiquement corrompues par l'echappement Python. Toujours separer frontend et backend :

```python
# dashboard.py
#!/usr/bin/env python3
import sqlite3, json
from flask import Flask, jsonify, send_file
import os

app = Flask(__name__, static_folder='.')  # dossier contenant index.html
DB_PATH = '/chemin/vers/pipeline.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/cards')
def api_cards():
    conn = get_db()
    cards = [dict(c) for c in conn.execute('SELECT * FROM cards ORDER BY id').fetchall()]
    conn.close()
    return jsonify(cards)

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]
    conn.close()
    return jsonify({'total': total})

@app.route('/')
def dashboard():
    return send_file('index.html')  # dossier statique, pas inline

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
```

Structure de fichiers :
```
/chemin/vers/dashboard/
├── dashboard.py          # Backend Flask pur (APIs uniquement)
├── index.html            # Frontend statique complet (HTML + CSS + JS)
└── pipeline.db           # SQLite (ou chemin externe)
```

Endpoints recommandes :
- `GET /api/cards` — toutes les cartes avec analyses
- `GET /api/stats` — compteurs agreges
- `GET /api/analysis/<id>` — analyse detaillee d'une carte
- `GET /api/kling/<id>` — payload Kling V3 pour une carte
- `GET /` — dashboard HTML (via `send_file`)

### 2. Frontend statique — Pattern de filtres exclusifs

**CRITIQUE :** Les filtres doivent etre MUTUELLEMENT EXCLUSIFS. Quand l'utilisateur clique sur un filtre, il remplace le filtre precedent — il ne s'ajoute PAS.

Pattern JavaScript valide :
```javascript
var currentFilter = 'all';

function setFilter(type) {
    currentFilter = type;
    // Desactiver TOUS les boutons
    var ids = ['fb-all', 'fb-ok', 'fb-wait', 'fb-sc', 'fb-com'];
    for (var i = 0; i < ids.length; i++) {
        var el = document.getElementById(ids[i]);
        if (el) el.classList.remove('a');
    }
    // Activer SEULEMENT le bouton clique
    var activeId = 'fb-all';
    if (type === 'ok') activeId = 'fb-ok';
    else if (type === 'wait') activeId = 'fb-wait';
    else if (type === 'sc') activeId = 'fb-sc';
    else if (type === 'com') activeId = 'fb-com';
    document.getElementById(activeId).classList.add('a');
    applyFilter();
}

function applyFilter() {
    var searchVal = (document.getElementById('searchIn')?.value || '').toLowerCase();
    var cards = document.querySelectorAll('.card');
    for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        var show = true;
        
        // Filtre exclusif (un seul a la fois)
        if (currentFilter === 'ok') show = (card.dataset.analyzed === '1');
        else if (currentFilter === 'wait') show = (card.dataset.analyzed === '0');
        else if (currentFilter === 'sc') show = (card.dataset.scored === '1');
        else if (currentFilter === 'com') show = (card.dataset.commented === '1');
        
        // La recherche affime le filtre (AND logique)
        if (show && searchVal) {
            show = (card.dataset.text || '').toLowerCase().indexOf(searchVal) !== -1;
        }
        
        card.style.display = show ? '' : 'none';
    }
}
```

Data attributes requis sur les cartes HTML :
```html
<div class="card" data-analyzed="1" data-scored="1" data-commented="1" data-text="W14 V1 GRAVEYARD UGC">
```

### 3. Parsing securise de JSON imbrique (comments_json)

Les commentaires Notion sont stockes en JSON double-echappe dans la DB. Le parsing JS doit etre defensif :

```javascript
function parseComments(raw) {
    var result = [];
    if (!raw || raw.length < 4) return result;
    try {
        var arr = JSON.parse(raw);
        if (Array.isArray(arr)) {
            for (var i = 0; i < arr.length; i++) {
                var txt = arr[i];
                if (typeof txt !== 'string') txt = JSON.stringify(txt);
                txt = txt.replace(/^["']*/, '').replace(/["']*$/, '');
                txt = txt.replace(/\\"/g, '"');
                if (txt.length > 0) result.push(txt);
            }
        }
    } catch(e) {}
    return result;
}
```

### 4. Verifier Tailscale

```bash
tailscale ip
# Note l'IPv4 (ex: 100.91.35.121)
```

### 5. Creer le service systemd

```bash
cat << 'EOF' > /etc/systemd/system/mon-dashboard.service
[Unit]
Description=Mon Dashboard Flask
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/chemin/vers/app
ExecStart=/usr/bin/python3 /chemin/vers/app/dashboard.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now mon-dashboard.service
systemctl status mon-dashboard.service
```

Verifier :
```bash
curl http://<tailscale-ip>:5001/api/stats
```

### 6. Acces

Le dashboard est accessible sur tous les appareils Tailscale :
```
http://<tailscale-ip>:5001
```

### 6. Display total duration in stats

Dans `updateStats()`, la duree totale est calculee mais DOIT etre injectee dans le HTML :

```javascript
function formatDur(s){
  s=Math.round(s);
  if(s>=3600){var h=Math.floor(s/3600);var m=Math.floor((s%3600)/60);return h+'h '+m+'m'}
  if(s>=60){var m=Math.floor(s/60);var sc=s%60;return m+'m '+sc+'s'}
  return s+'s';
}

var items=[
  {v:s.with_video,l:'Videos',hl:false,sub:formatDur(s.total_duration||0)},
  {v:s.total_shots,l:'Shots',hl:false},
  {v:s.analyzed,l:'Ok',hl:true},
  {v:s.pending,l:'Todo',hl:false}
];
var h='';
for(var i=0;i<items.length;i++){
  var it=items[i];
  var subH=it.sub?'<div class="stat-sub">'+it.sub+'</div>':'';
  h+='<div class="stat'+(it.hl?' highlight':'')+'"><div class="stat-body"><div class="stat-val">'+it.v+'</div>'+subH+'</div><div class="stat-label">'+it.l+'</div></div>';
}
document.getElementById('stats').innerHTML=h;
```

CSS associe : `.stat-sub{font-size:.62em;color:#22c55e;margin-top:1px;font-weight:500}`

### 7. Rendering des commentaires en blocs numerotes

Chaque commentaire doit etre dans un bloc avec numero et bordure coloree, PAS un simple `<p>` :

```javascript
if(coms.length>0){
  html+='<div class="comments-section">';
  html+='<div class="comments-section-header"><h4>Comments Notion</h4><span style="font-size:.7em;color:#444">'+coms.length+' commentaires</span></div>';
  for(var k=0;k<coms.length;k++){
    html+='<div class="comment-block"><div class="comment-num">'+(k+1)+'</div><div class="comment-text">'+esc(coms[k])+'</div></div>';
  }
  html+='</div>';
}
```

CSS associe :
```css
.comment-block{display:flex;gap:10px;padding:10px 12px;margin-bottom:6px;background:#0a0a0a;border:1px solid #1a1a1a;border-radius:8px;border-left:3px solid #22c55e}
.comment-num{font-size:.75em;font-weight:700;color:#22c55e;min-width:20px;flex-shrink:0;margin-top:1px}
.comment-text{font-size:.8em;color:#bbb;line-height:1.5;white-space:pre-wrap}
```

### 8. Helper modal reutilisable

```javascript
function modalOpen(title,body){
  document.getElementById('modalTitle').textContent=title;
  document.getElementById('modalBody').innerHTML=body;
  document.getElementById('modal').classList.add('open');
}
```

### 9. CRITIQUE: JAMAIS de polling auto sur connexion remote

**PROBLEME RECURRENT :** Les `setInterval` qui font `loadCards()` ou `showDetail()` toutes les N secondes rendent le dashboard IMPOSSIBLE a utiliser sur Tailscale/Selkies :
- Re-render complet du DOM a chaque iteration = scroll lag insupportable
- `showDetail()` dans un polling interval re-construit TOUTE la vue detail, empeche la navigation
- Deux navigateurs pollent en simultane → double charge serveur
- L'utilisateur ne peut pas naviguer sans que la page se reinitialise

**SOLUTION : Zero auto-polling. Toujours.**
```javascript
// ❌ NE JAMAIS FAIRE
setInterval(function(){ loadStats(); if(!curCard) loadCards(); }, 15000);

// Polling Kling qui reload toute la page
setInterval(function(){ loadCards(); showDetail(id); }, 12000);

// ✅ FAIRE A LA PLACE : bouton refresh manuel
// Boot sans polling
loadStats(); loadCards();
// Un bouton dans le header :
// <button onclick="loadStats();loadCards();toast('Mise a jour','ok')">Refresh</button>
```

Si un polling est absolument necessaire (ex: job Kling en cours), NE JAMAIS appeler `loadCards()` ou `showDetail()`. Mettre a jour UNIQUEMENT le badge/status :
```javascript
setInterval(function(){
    fetch('/api/cards').then(...).then(function(cards){
        // Mettre a jour uniquement le texte du badge, pas le DOM entier
        var badge = document.getElementById('klingBadge');
        if(badge) badge.textContent = 'Kling: ' + status;
    });
}, 30000);
```

### 10. Verification post-deploiement

Boucle de verification obligatoire apres chaque deploiement :
1. Screenshot de la page → verifier que le contenu s'affiche (pas de spinner infini)
2. Cliquer chaque filtre → verifier qu'un seul est actif a la fois
3. Taper dans la recherche → verifier que les resultats correspondent
4. Cliquer un bouton "Analyse" ou "Comments" → verifier que la modale s'ouvre sans erreur JS
5. Ouvrir la console browser (`browser_console`) → verifier aucune erreur JS

### 11. Architecture frontend : recommandations

**Evite le monolithe ES5 inline.** Un `index.html` de 1400+ lignes avec tout le JS inline devient impossible a maintenir et provoque des bugs de re-render.

**Approches preferables (par ordre de preference) :**

1. **HTMX + Jinja2** : Flask render partiel cote serveur, HTMX fait les fetch. Zero JS complexe, pas de re-render complet, navigation fluide.
2. **Streamlit** : Zero JS a ecrire. Dashboard 100% Python. Parfait pour les dashboards data/DB. Rechargement auto, tables editables.
3. **SPA minimaliste + fetch()** : Si SPA necessaire, garder le JS separe du HTML, utiliser `documentFragment` pour les insertions, et JAMAIS re-render le DOM entier.

**Regles d'or pour tout dashboard Flask remote :**
- Le dashboard ne se refresh JAMAIS automatiquement
- Un bouton refresh manuel si necessaire
- Pas de flash quand on navigue entre les vues
- Pas de lag au scroll (eviter `innerHTML` sur des containers larges)
- La taille du fichier HTML+JS doit rester sous 30KB

## Pitfalls : Les chaines Python `"""..."""` corrompent systematiquement les sequences d'echappement JS (`\n`, `\\`, guillemets imbriques). Decision irreversible : separer frontend et backend via `static_folder` + `send_file`.
- **Filtres qui s'ajoutent au lieu de remplacer** : Si `filtrer()` est appele avec un bouton sans desactiver les autres, les filtres deviennent cumulatifs (ex: "Analysées" + "En attente" = tout afficher). La solution est un etat global `currentFilter` + desactivation explicite de tous les boutons avant activation du clique.
- **Cloudflare Pages = statique uniquement** : ne peut PAS lire une DB ou exposer une API dynamique.
- **Cloudflare tunnel quick** : `*.trycloudflare.com` DNS unreliable, URL change a chaque lancement. NE PAS utiliser.
- **systemd ExecStart** : chemin absolu vers python3 obligatoire (`which python3`).
- **Restart=always** : essentiel pour resister aux crashes Flask.
- **Flask debug=False** : jamais `debug=True` en prod — le reloader casse le service.
- **Port** : Flask doit ecouter sur `0.0.0.0`, pas `127.0.0.1` — sinon seul localhost peut acceder.
- **sqlite3.Row** : n'a PAS de methode `.get()` — utiliser `row['col'] or 'default'`.
- **Modal Escape key** : toujours ecouter `keydown` pour `Escape` et `Esc` (les deux codes existent selon le navigateur).