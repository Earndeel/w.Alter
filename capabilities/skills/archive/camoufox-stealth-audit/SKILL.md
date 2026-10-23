---
name: camoufox-stealth-audit
category: devops
description: Audit systematic stealth/fingerprinting anti-detect browser Camoufox Max — test endpoints, screenshot analysis, WebGL/canvas/TLS/WebRTC verification
---

## When to Use

- Auditing Camoufox Max anti-detect browser stealth level
- Testing fingerprint resistance against bot detection sites
- Verifying WebGL/canvas/TLS/WebRTC leak protection on headless servers

## Pitfalls

- Camoufox stock server has NO `/evaluate` endpoint — cannot execute arbitrary JS in page context, use `/snapshot` and `/screenshot` instead
- **camoufox-max variant** (`/root/.hermes/camoufox-max/server-max.js`) DOES have `/tab/evaluate` — use it for SPA automation where a11y trees are empty (AWS Console, React apps). See `hermes-camoufox-setup/references/camoufox-max-variant.md`
- WebGL context returns `null` on ARM servers (no real GPU) — spoof via `getParameter()` works for 80% of anti-bot sites but fails BrowserLeaks/Sannysoft
- Timezone mismatch between Playwright config (`America/Los_Angeles`) and system timezone can leak via `Intl.DateTimeFormat`
- Screen resolution 15360x8640 is non-standard for desktop — may trigger detection
- EGL (`MOZ_X11_EGL=1`) causes total hang on ARM aarch64 — avoid

# Camoufox Stealth Audit Methodology

Procédure d'audit systematic du niveau de camouflage anti-detect de Camoufox Max.

## Prérequis
- Camoufox Max actif sur port 9377
- Endpoints API connus (pas de `/evaluate` — orienté navigation/contrôle)
- Python avec `http.client`, `vision_analyze` pour l'analyse visuelle

## Step 1: Vérif API Endpoints

```python
def camoufox_json(method, path, body=None):
    conn = http.client.HTTPConnection("localhost", 9377)
    if body:
        headers = {"Content-Type": "application/json"}
        conn.request(method, path, json.dumps(body), headers)
    else:
        conn.request(method, path)
    resp = conn.getresponse()
    raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else {}
```

### Endpoints disponibles
| Endpoint | Usage |
|---|---|
| `GET /health` | Health check |
| `POST /tabs` | Créer un nouveau tab |
| `POST /tabs/:id/navigate` | Naviguer à une URL |
| `GET /tabs/:id/snapshot` | Arbre d'accessibilité |
| `GET /tabs/:id/screenshot` | PNG screenshot |
| `GET /tabs/:id/links` | Liens sur la page |
| `GET /tabs/:id/stats` | Stats/flags navigateur |
| `POST /tabs/:id/{wait,click,type,press,scroll}` | Contrôles UI |
| `POST /act` | Agent action |

### ⚠️ Limite critique
- **Pas d'endpoint `/evaluate`** — impossible d'exécuter du JS arbitraire dans la page
- Contournement : utiliser `/snapshot` (arbre DOM textuel) et `/screenshot` (visuel)

## Step 2: Test Pages (Screenshots)

Naviguer sur chaque site de test, attendre 5s, screenshot, analyser avec vision :

```python
import time, base64

def camoufox_img(method, path, save_as=None):
    conn = http.client.HTTPConnection("localhost", 9377)
    conn.request(method, path)
    resp = conn.getresponse()
    data = resp.read()
    if save_as:
        with open(save_as, "wb") as f:
            f.write(data)
    return data

test_pages = [
    ("bot.sannysoft.com",     "Détection bot/headless/automation"),
    ("browserleaks.com/canvas",   "Fingerprint canvas"),
    ("browserleaks.com/javascript", "Info JavaScript"),
    ("browserleaks.com/tls",      "TLS fingerprint JA3/JA4"),
    ("browserleaks.com/webrtc",   "WebRTC leak test"),
    ("browserleaks.com/ip",       "IP & geolocation"),
]

tabId = "<tab-id>"
for name, _ in test_pages:
    url = f"https://{name}"
    camoufox_json("POST", f"/tabs/{tabId}/navigate",
        {"userId": "audit", "listItemId": "audit", "url": url})
    time.sleep(5)
    camoufox_img("GET", f"/tabs/{tabId}/screenshot?userId=audit&listItemId=audit",
        save_as=f"/tmp/audit_{name.replace('.','_')}.png")
```

Puis analyser chaque screenshot avec `vision_analyze`.

## Step 3: Points de Validation

### bot.sannysoft.com — Score global anti-bot
| Test | Attendu | Critique |
|---|---|---|
| WebDriver flag | missing/undefined | 🔴 CRITIQUE |
| WebDriver advanced | passed | 🔴 CRITIQUE |
| User Agent cohérent | match avec la UA | 🔴 CRITIQUE |
| Plugins length | > 0 (idéalement 5+) | 🟡 Important |
| Languages | cohérent avec le profil | 🟡 Important |
| WebGL vendor/renderer | NON vide | 🟡 Important (échoue souvent sur serveur) |
| Chrome runtime | present si UA Chrome | 🟢 Normal si Firefox |

### browserleaks.com/canvas
- Canvas fingerprint avec noise/noise absent = bien
- 925+ couleurs = rendu normal
- Pas de détection "headless" ou "automated"

### browserleaks.com/tls
- JA3 hash doit correspondre au navigateur déclaré (Firefox)
- TLS 1.2 et 1.3 activés
- Pas d'incohérence UA/TLS

### browserleaks.com/webrtc
- Pas de fuite d'IP locale (pas de 192.168.x.x ni 10.x.x.x)
- IP WebRTC == IP HTTP distante
- SDP log montre `IN IP4 0.0.0.0` = bloqué ok

### browserleaks.com/ip
- IP publique cohérente avec la config geoip
- Pas de proxy/VPN flag

## Step 4: Vérification Config

### Fichiers clés
- `/root/.hermes/hermes-agent/node_modules/@askjo/camoufox-browser/server-camoufox.js` — Server API
- `/root/.hermes/hermes-agent/node_modules/camoufox-js/dist/utils.js` — Function `launchOptions()`
- `/root/.hermes/hermes-agent/node_modules/camoufox-js/dist/data-files/webgl_data.db` — WebGL fingerprints

### Config actuelle (server-camoufox.js)
```javascript
const options = await launchOptions({
  headless: true,
  os: hostOS,        // 'linux' détecté via os.platform()
  humanize: 2.0,
  enable_cache: true,
  geoip: true,
});
// firefox.launch(options)
```

### Contexte Playwright (getSession)
```javascript
const context = await b.newContext({
  viewport: { width: 1280, height: 720 },
  locale: 'en-US',
  timezoneId: 'America/Los_Angeles',
  geolocation: { latitude: 37.7749, longitude: -122.4194 },
  permissions: ['geolocation'],
});
```

### ⚠️ Mismatch timezone connu
- Timezone Playwright : `America/Los_Angeles`
- Timezone système : Europe/Paris ou Indochina (Oracle Cloud)
- **Risque** : JavaScript `Intl.DateTimeFormat` peut leak timezone système

## Step 5: WebGL — Problème serveur ARM (résolu partiellement)

### Symptôme
- Sannysoft : "Canvas has no webgl context"
- BrowserLeaks : "Supported, but disabled or unavailable"
- `canvas.getContext('webgl')` retourne `null`

### Diagnostic complet (2026-04-05)
- **Pas de `llvmpipe_dri.so` sur ARM aarch64**, seulement `swrast_dri.so` et `kms_swrast_dri.so`
- EGL (`MOZ_X11_EGL=1`) **cause un hang total** du process Firefox sur ARM — à éviter
- Variables qui **stabilisent sans hang** : `LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=softpipe`, `__GLX_VENDOR_LIBRARY_NAME=mesa`
- Prefs Firefox : `webgl.force-enabled: true`, `webgl.enable-webgl2: true`
- Résultat : **amélioration logicielle mais contexte GL toujours manquant** sur Xvfb aarch64

### ✅ Spoof WebGL fonctionnel (suffisant pour anti-bot passif)
Camoufox injecte un fingerprint NVIDIA GTX 980 complet via `sampleWebGL()`. Les détecteurs passifs voient :
- `getParameter(7936)` = "Mozilla"
- `getParameter(7937)` = "NVIDIA GeForce GTX 980, or similar"
- `getParameter(37445/37446)` = "NVIDIA Corporation" / "NVIDIA GeForce GTX 980, or similar"
- Extensions WebGL/2 complètes (40+ extensions WebGL1, 16 WebGL2)
- Shader precision formats corrects

⚠️ **Limite** : `canvas.getContext('webgl')` retourne `null` — les tests qui créent un vrai contexte (BrowserLeaks, Sannysoft) détectent l'absence de GPU réel. Score max : 8/11 sur ces sites.

### Score réel
- Sites anti-bot passifs : **suffisant** (fingerprint NVIDIA crédible)
- BrowserLeaks/Sannysoft : **8/11** (3 échecs attendus : WebGL contexte, Chrome runtime, timezone)

## Results Types

### Score final
- **0-1 points faibles** : Stealth excellent ✅
- **2-3 points faibles (mineurs)** : Acceptable pour scraping standard ⚠️
- **4+ points faibles (ou 1 critique)** : Pas prêt pour anti-bot sérieux ❌

### Points faibles courants serveurs ARM
1. **WebGL contexte manquant** (`getContext('webgl')` = null) — spoof actif `getParameter()` suffit pour 80% des cas
2. **Timezone mismatch** (système vs Playwright config `America/Los_Angeles`)
3. **Resolution écran** (15360x8640 — non standard pour un desktop)
4. **Pas de webcam/microphone** (normal sur serveur)

### Anti-CAPTCHA (CapSolver) — Architecture d'intégration
Quand un CAPTCHA est détecté (reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile), le workflow optimal est :

1. **Détection** : Screenshot `/tabs/:id/screenshot` ou snapshot `/tabs/:id/snapshot` révèle CAPTCHA
2. **Extraction** : Parser le `siteKey` depuis le DOM (snapshot ou snapshot HTML)
3. **Résolution** : POST à `https://api.capsolver.com/createTask` avec siteKey → attendre ~10s → `getTaskResult`
4. **Injection** : Exécuter JS pour placer le token dans le hidden field du formulaire
   - Via CDP (Webtop Chromium) : `CDP.Runtime.evaluate` avec expression JS
   - Via Camoufox : `/act` endpoint avec `text` + `press: Enter` si le token s'injecte dans un champ visible
5. **Coût** : ~$0.001-0.003 par reCAPTCHA résolu

⚠️ Camoufox n'a pas d'endpoint `/evaluate` — injection JS directe impossible. Utiliser Webtop CDP comme fallback pour CAPTCHA.
