# Remote Backend Code Analysis (main.cjs)

Analyse du flux de résolution du backend distant dans l'app Electron Hermes Desktop.

## Flux d'initialisation

```
startHermes()                                    # ligne 5481
  └─ resolveRemoteBackend(primaryProfileKey())   # ligne 5500
       ├─ 1. Per-profile override (connection.json profiles[name])
       ├─ 2. Env vars HERMES_DESKTOP_REMOTE_URL + TOKEN  ← NOTRE CAS
       │     └─ buildRemoteConnection(url, 'token', token, 'env')  # ligne 4967
       └─ 3. Global remote (connection.json mode: "remote")

  Si remote trouvé:
    └─ waitForHermes(baseUrl, token)             # ligne 5503
         └─ fetchJson(`${baseUrl}/api/status`, token) × 45s  # ligne 3887
    └─ Retourne { baseUrl, mode:'remote', token, wsUrl }

  Si remote = null (fallback local):
    └─ resolveHermesBackend(backendArgs)          # ligne 5544
         ├─ HERMES_DESKTOP_HERMES_ROOT (dev override)
         ├─ SOURCE_REPO_ROOT (npm run dev)
         ├─ Bootstrap-complete marker → createActiveBackend()
         ├─ hermes on PATH
         ├─ System Python + hermes_cli
         └─ Bootstrap managed install ⚠️ CECI INSTALLE HERMES EN LOCAL
    └─ spawn('hermes', ['serve', '--host', '127.0.0.1', '--port', '0'])
```

## Fonctions clés

### resolveRemoteBackend(profile) — ligne 4945

```javascript
async function resolveRemoteBackend(profile) {
  const config = readDesktopConnectionConfig()

  // 1. Per-profile override
  const override = profileRemoteOverride(config, profile)
  if (override) { ... }

  // 2. Env override (global, token-auth only)
  const rawEnvUrl = process.env.HERMES_DESKTOP_REMOTE_URL
  const rawEnvToken = process.env.HERMES_DESKTOP_REMOTE_TOKEN
  if (rawEnvUrl) {
    if (!rawEnvToken) {
      throw new Error('HERMES_DESKTOP_REMOTE_URL is set but HERMES_DESKTOP_REMOTE_TOKEN is not.')
    }
    return buildRemoteConnection(rawEnvUrl, 'token', rawEnvToken, 'env')
  }

  // 3. Global remote
  if (config.mode !== 'remote') return null
  ...
}
```

### buildRemoteConnection(rawUrl, authMode, token, source) — ligne 4877

```javascript
async function buildRemoteConnection(rawUrl, authMode, token, source) {
  const baseUrl = normalizeRemoteBaseUrl(rawUrl)

  if (authMode === 'oauth') { ... }  // OAuth flow

  if (!token) throw new Error('Remote Hermes gateway is selected, but no session token is saved.')

  return {
    baseUrl, mode: 'remote', source,
    authMode: 'token', token,
    wsUrl: buildGatewayWsUrl(baseUrl, token)
  }
}
```

### waitForHermes(baseUrl, token) — ligne 3881

```javascript
async function waitForHermes(baseUrl, token) {
  const deadline = Date.now() + 45_000
  while (Date.now() < deadline) {
    try {
      await fetchJson(`${baseUrl}/api/status`, token)
      return   // ← Succès
    } catch (error) {
      lastError = error
      await new Promise(resolve => setTimeout(resolve, 500))
    }
  }
  throw new Error(`Hermes backend did not become ready: ${lastError?.message}`)
}
```

## Piège : `open` sur macOS

`open "$APP"` utilise LaunchServices → l'app hérite de l'environnement de `launchd`, pas du shell.
Les `export` sont ignorés. Solution : lancer le binaire directement.

```bash
# ❌ Ne fonctionne pas
export HERMES_DESKTOP_REMOTE_URL="http://127.0.0.1:9119"
export HERMES_DESKTOP_REMOTE_TOKEN="no-auth"
open "/Applications/Hermes V2.app"

# ✅ Fonctionne
exec env \
  HERMES_DESKTOP_REMOTE_URL="http://127.0.0.1:9119" \
  HERMES_DESKTOP_REMOTE_TOKEN="no-auth" \
  "/Applications/Hermes V2.app/Contents/MacOS/Hermes"
```

## Piège : `auth_required: false` — le token DOIT être un vrai token de session

**Le `/api/status` est un endpoint public** — il répond 200 sans authentification, quelle que soit la
valeur du token. C'est ce que `waitForHermes()` appelle pour vérifier que le backend est prêt.

**Mais tous les autres endpoints API** (`/api/sessions`, `/api/models`, etc.) exigent une vraie
session Hermes. Si le token est une valeur arbitraire (ex: `"no-auth"`), le comportement est :

1. `waitForHermes()` → `/api/status` → **200 OK** ✓ (endpoint public)
2. App entre en mode remote, le renderer tente des appels API → **401 Unauthorized** ✗
3. L'app affiche "Could not connect to Hermes gateway" avec les recovery steps

### Comment obtenir le vrai token

Le gateway avec `auth_required: false` injecte son token de session dans le HTML du dashboard :

```bash
curl -s http://127.0.0.1:9119/ | grep -o '__HERMES_SESSION_TOKEN__="[^"]*"' | sed 's/__HERMES_SESSION_TOKEN__="//;s/"$//'
# Retourne par ex: E4LaPr-p383zUZP-VMCa87ua1FiuTZ24ettGyXp_t8g
```

**Ce token change à chaque redémarrage du gateway.** Le launcher doit donc le récupérer
dynamiquement, pas le hardcoder.

### Comment l'Electron le gère en mode local

En mode local, `dashboard-token.cjs::resolveServedDashboardToken()` lit le token depuis
`window.__HERMES_SESSION_TOKEN__` dans le HTML du dashboard (que l'Electron a spawné lui-même).
En mode remote (`connection.json`), l'Electron utilise le token statique fourni — il ne va pas
le chercher dans le HTML. D'où le besoin de fournir le vrai token.
