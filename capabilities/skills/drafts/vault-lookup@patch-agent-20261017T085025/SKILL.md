---
name: vault-lookup
description: "Architecture de sécurité W.Alter — vault, Bitwarden, cookies, SSH Mac, .env. Tous les accès sensibles centralisés."
version: 2.1.0
author: W.Alter
metadata:
  hermes:
    tags: [credentials, vault, security, keys, bitwarden, cookies, ssh]
---

# W.Alter Security Architecture

Tout ce qu'on ne veut pas voir tomber entre de mauvaises mains.

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────┐
│                  SOURCES DE SECRETS                  │
├──────────────┬──────────────┬───────────┬───────────┤
│  vault.json  │  Bitwarden   │  .env     │  Cookies  │
│  (age enc.)  │  (bw CLI)    │  (plain)  │  (Mac)    │
├──────────────┼──────────────┼───────────┼───────────┤
│  API keys    │  ~1 040 items│  Runtime  │  Sessions │
│  Tokens      │  Passwords   │  env vars │  browser  │
│  Secrets     │  Logins      │           │  auth     │
├──────────────┴──────────────┴───────────┴───────────┤
│              Mac SSH (Tailscale)                     │
│              Keychain → Cookies decrypt              │
└─────────────────────────────────────────────────────┘
```

Ordre de priorité quand on cherche un secret :
1. vault get service/field — toujours en premier
2. Bitwarden — via les outils `walter-secrets` (skill `bitwarden-logins`) ; `bw` à la main seulement en maintenance
3. .env / env vars — runtime
4. Cookies Mac Brave — sessions browser authentifiées

---

## 1. Vault W.Alter (vault.json.age)

Fichier chiffré : ~/.hermes/vault/vault.json.age
Clé age : ~/.hermes/vault/age-key.txt
CLI : vault (alias pour le script interne)

### Commandes

```bash
vault get <service>/<field>        # Lire une valeur
vault list                         # Lister les services (masqué)
vault list --secrets               # Lister avec valeurs partielles
vault add <service> <field> <val>  # Ajouter/modifier
vault remove <service> <field>     # Supprimer
vault search <query>               # Rechercher
vault export                       # Exporter vers .env
vault export --mcporter            # Exporter vers mcporter.json
vault decrypt                      # Debug: déchiffrer vault.json
vault encrypt                      # Re-chiffrer après édition manuelle
```

### Services actuels (juin 2026)

| Service | Catégorie | Champs |
|---------|-----------|--------|
| agentmail | custom | api_key |
| artificial-analysis | custom | api_key |
| atlas | custom | api_key |
| beeper | messaging | api_url, platforms, token, username |
| bitwarden | custom | email, master_password, server_url |
| brave | search | api_key |
| cloudflare | infrastructure | account_id, api_token, global_api_key |
| fal | ai_gen | api_key |
| gemini | llm | api_key |
| github | devtools | token |
| gitlawb | custom | api_key |
| groq | llm | api_key |
| hindsight | memory | api_key |
| huggingface | llm | token |
| kaggle | custom | password, username |
| kie | custom | api_key |
| macos | custom | brave_keychain_key, lucas_password |
| notion | productivity | api_key, token |
| openai | custom | api_key |
| openai_vault | llm | api_key |
| opencode_zen | llm | api_key, base_url |
| openrouter | llm | api_key |
| scena_connect | custom | sandbox_api_key, sandbox_webhook_secret |
| smmflare | custom | api_key |
| ssh | custom | backup_passphrase, backup_private_key |
| stripe | billing | rk_live, sk_live_mcp, sk_live_vaf, webhook_secret |
| telegram | messaging | allowed_users, bot_token, home_channel |
| tinder | custom | api_token |
| vastai | custom | api_key, card_cvv, card_expiry, card_number |
| vercel | infrastructure | token |
| xiaomi | llm | api_key, base_url |

### Providers LLM configurés

gemini, nous, openai-codex, opencode-zen, openrouter, xiaomi

### MCP Servers

cloudflare

---

## 2. Bitwarden (Personal Vault — bw CLI)

**Priority: the `walter-secrets` tools.** For logins, passwords, TOTP and codes received by e-mail / message, use
`secret_search` / `secret_fill` / `secret_otp` (skill `bitwarden-logins`): the value is filled where it is needed and
never shows in the conversation. Module reference: `~/.hermes/plugins/walter-secrets/README.md`. The vault (~1 040
entries, 14 thematic folders + « W.Alter – Clés API ») is filed and backed up automatically by `walter-secrets-sync`.

**Manual `bw` (maintenance only, below)**: never let a secret reach the tool output. To pass a value to a command, use
a placeholder `{{bw:<item id>:<field>}}` or `$(walter-secret get <item id> <field>)` inside the command; to check that
an entry exists, list metadata only (name, username, URI) — never run `bw get password` / `bw get item` bare.

Instance auto-hébergée : lucas-bitwarden.duckdns.org (HTTPS)
Compte : lucas.jouvencon@gmail.com
Mot de passe maître : stocké dans le coffre age W.Alter, entrée `bitwarden/master_password` (lire avec `vault get`)
950+ items : passwords, logins, notes, API keys

### Accès manuel — helper bw-unlock (maintenance)

Le helper `~/.hermes/bin/bw-unlock` gère tout : login auto, unlock depuis le vault, cache de session valide. À utiliser en priorité.

```bash
# Déverrouiller + exporter BW_SESSION dans le shell courant
source ~/.hermes/bin/bw-unlock

# Juste le status
~/.hermes/bin/bw-unlock --check

# Récupérer la session pour une commande one-shot
BW_SESSION=$(~/.hermes/bin/bw-unlock --print)

# Puis utiliser bw normalement
bw list items --session "$BW_SESSION"
walter-secret get "<item id>" password | wc -c   # vérifier sans afficher ; pour l'utiliser : $(walter-secret get …) dans la commande
```

Le helper réutilise la session cachée (`~/.hermes/vault/.bw_session_key`, mode 600) si elle est encore valide → déverrouillage instantané. Sinon il re-déverrouille depuis `vault get bitwarden/master_password`.

### Accès — méthode manuelle (si le helper indisponible)

```bash
# Vérifier l'état
bw status
# → "unauthenticated" = besoin de login | "locked" = besoin de unlock | "unlocked" = prêt

# Login (première fois)
bw config server https://lucas-bitwarden.duckdns.org
bw login lucas.jouvencon@gmail.com "$(vault get bitwarden/master_password)"

# Unlock (session expirée) — le --raw final appartient à bw, PAS à vault
BW_SESSION=$(bw unlock "$(vault get bitwarden/master_password)" --raw)
export BW_SESSION

# Chercher un item par nom
bw list items --session "$BW_SESSION" | python3 -c "
import json, sys
items = json.loads(sys.stdin.read())
for i in items:
    if 'mot-clef' in i['name'].lower():
        print(f\"{i['name']}: {i.get('login',{}).get('username','')}\")
"

# Items d'identité (type 4) et cartes (type 3)
bw list items --session \"$BW_SESSION\" | python3 -c \"
import json, sys
for i in json.loads(sys.stdin.read()):
    if i.get('type') == 4: print('IDENTITE:', i['name'])
    if i.get('type') == 3: print('CARTE:', i['name'])
\"
```

### BWS vs bw — NE PAS CONFONDRE

| | Personal Vault (bw) | Secrets Manager (bws) |
|---|---|---|
| Usage | Passwords humains | Machine-to-machine |
| Notre setup | Actif | Non activé |
| Auth | Master password | Service account token |
| Hermes | Via vault-lookup | hermes secrets bitwarden setup |

---

## 3. Kardex perso (profil de Monsieur — ID 0)

Le Kardex est le système de contact intelligence (PostgreSQL `hindsight-pg`, schema `kardex`, table `contacts`). Monsieur est **l'ID 0, `relationship_type = self`**. Raccourci CLI `kardex`.

```bash
kardex                  # Profil complet de Monsieur (ID 0)
kardex <field>          # Un champ précis (ex: kardex phone_numbers, kardex emails, kardex occupation)
kardex set <field> <v>  # Met à jour un champ du profil ID 0
kardex contact <query>  # Cherche un contact par nom/alias
kardex who <id>         # Affiche le profil d'un contact par ID
```

Profil ID 0 (juin 2026) :

| Champ | Valeur |
|-------|--------|
| canonical_name | Lucas |
| aliases | Monsieur, boss, patron, earndeel |
| location_current | Bangkok, Thailand (UTC+7) |
| languages | fr, en |
| occupation | entrepreneur tech / AI |
| handles | x: @earndeel, sip: earndeel@sip.linphone.org, telegram: owner |
| phone_numbers / emails | (vides — à compléter si besoin) |

Accès direct SQL si besoin :
```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -x -c \
  "SELECT * FROM kardex.contacts WHERE id = 0;"
```

Base : Postgres `hindsight-pg` sur 127.0.0.1:5433, base `hindsight` ; identifiants uniquement dans `/root/.pgpass` (jamais dans une fiche).

NE PAS confondre avec un service vault — le Kardex vit dans PostgreSQL, pas dans vault.json.age. Pour les infos perso de Monsieur (téléphone, adresse, etc.), c'est le Kardex ID 0 la source de vérité, complétée par l'item Bitwarden "Lucas" (type 4, identité).

---

## 4. Fichier .env (runtime)

Emplacement : ~/.hermes/.env
Usage : variables d'environnement chargées au démarrage d'Hermes
Ne pas éditer manuellement — utiliser vault add puis vault export

```bash
# Exporter le vault vers .env
vault export > ~/.hermes/.env.new
# Fusionner prudemment avec .env existant

# Importer des clés depuis .env vers le vault
vault import-env
```

---

## 5. Accès Mac Brave (cookies + SSH)

### Connexion SSH

Méthode principale : Tailscale direct
ssh lucasjouvencon@100.127.150.1

Config SSH dans ~/.ssh/config — pointe actuellement sur localhost:2222 (tunnel inverse). BUG connu : utiliser l'IP Tailscale directe 100.127.150.1 quand le tunnel ne marche pas.

Clé SSH : ~/.ssh/id_ed25519

Le Mac est actif sur Tailscale (lucass-macbook-pro-15, 100.127.150.1, exit node actif).

### Extraction cookies Brave

Les cookies Brave sont chiffrés AES-128-CBC. La clé de déchiffrement est dans le Keychain macOS, sauvegardée dans le vault.

Pipeline complet :

```python
import hashlib, json, subprocess
from Crypto.Cipher import AES

# 1. Récupérer les cookies chiffrés depuis le Mac
result = subprocess.run(
    ["ssh", "lucasjouvencon@100.127.150.1",
     'sqlite3 ~/Library/Application\\ Support/BraveSoftware/'
     'Brave-Browser/Default/Cookies '
     '"SELECT host_key, name, hex(encrypted_value), path, '
     'is_secure, is_httponly, expires_utc '
     'FROM cookies WHERE host_key LIKE \'%domaine%\'"'],
    capture_output=True, text=True
)

# 2. Clé de déchiffrement (Keychain → vault)
key = subprocess.run(
    ["vault", "get", "macos/brave_keychain_key"],
    capture_output=True, text=True
).stdout.strip().encode()
derived_key = hashlib.pbkdf2_hmac('sha1', key, b'saltysalt', 1003, dklen=16)

# 3. Déchiffrer
def decrypt(hex_str):
    enc = bytes.fromhex(hex_str)
    if enc[:3] == b'v10': enc = enc[3:]
    elif enc[:4] == b'v11': enc = enc[4:]
    iv, data = enc[:16], enc[16:]
    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
    dec = cipher.decrypt(data)
    pad = dec[-1]
    if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]):
        dec = dec[:-pad]
    clean = dec[16:] if len(dec) > 16 else dec  # skip garbled first block
    return bytes(b for b in clean if 32 <= b <= 126).decode('ascii')

# 4. Parser et convertir au format Playwright
cookies = []
for line in result.stdout.strip().split('\n'):
    parts = line.split('|')
    if len(parts) < 7: continue
    host, name, enc_hex, path, secure, httponly, expires = parts
    val = decrypt(enc_hex)
    c = {"name": name, "value": val, "domain": host, "path": path,
         "secure": secure=='1', "httpOnly": httponly=='1'}
    if expires and int(expires) > 0:
        c["expires"] = int((int(expires)/1000000) - 11644473600)
    cookies.append(c)
```

### Injection dans Camoufox

```python
from camoufox.sync_api import Camoufox

with Camoufox(headless=True, humanize=True) as browser:
    page = browser.new_page()
    page.goto("https://target.com", wait_until="domcontentloaded", timeout=30000)
    context = browser.contexts[0]
    context.add_cookies(cookies)
    page.goto("https://target.com/protected", wait_until="domcontentloaded")
```

### Clés dans le vault

| Clé | Usage |
|-----|-------|
| macos/brave_keychain_key | Clé PBKDF2 pour déchiffrer les cookies Brave |
| macos/lucas_password | Mot de passe macOS (pour Keychain si besoin) |

### Pitfalls cookies

- Chrome epoch : expires_utc est en microsecondes depuis 1601-01-01. Convertir : unix = int((chrome_us / 1000000) - 11644473600)
- Premier bloc : les 16 premiers octets déchiffrés sont toujours du bruit (nonce partagé par domaine). Skip.
- cf_clearance : N'JAMAIS injecter d'un navigateur à l'autre — Cloudflare le lie au fingerprint. Laisser Camoufox obtenir le sien.
- Payload limit : max 512KB / 500 cookies par injection Camoufox.
- Keychain via SSH : find-generic-password -w échoue avec error 36 (ACL non-interactif). La clé doit être dans le vault.

---

## 6. Sécurité — Règles absolues

1. JAMAIS afficher un secret en clair dans les réponses Telegram/chat — toujours masquer
2. JAMAIS commit de secrets dans Git
3. JAMAIS stocker le master password Bitwarden dans .env — uniquement dans le vault chiffré
4. Toujours vérifier le vault AVANT de demander un credential à l'utilisateur
5. Session Bitwarden : sauvegarder dans ~/.hermes/vault/.bw_session_key, pas dans la mémoire
6. Cookies Mac : extraire uniquement sur demande, ne pas stocker en clair sur le VPS
7. SSH Mac : utiliser Tailscale (100.127.150.1), pas le tunnel inverse localhost:2222 (fragile)

### Fluidité vs sécurité — le bon compromis

La récupération de données sensibles doit être RAPIDE pour ne pas bloquer le travail, sans sacrifier la sécurité :

| Source | Latence | Mécanisme |
|--------|---------|-----------|
| vault get | ~50ms | déchiffrement age local, pas de réseau |
| kardex (PG) | ~80ms | requête PostgreSQL locale (conteneur) |
| bw-unlock (cache) | ~8ms | session cachée < 8h, pas de validation réseau |
| bw-unlock (froid) | ~3s | unlock + appel serveur Bitwarden |

Clé de la fluidité Bitwarden : `bw-unlock` fait confiance au cache de session s'il a moins de 8h (mtime du fichier `.bw_session_key`), évitant l'appel réseau de validation (3s) à chaque accès. Au-delà de 8h, il valide par réseau puis re-déverrouille si besoin. La sécurité est préservée : le fichier cache est en 600, et le master password reste uniquement dans le vault chiffré.

Permissions strictes (vérifier régulièrement) :
- vault.json.age : 600
- .bw_session_key, age-key.txt : 600
- ~/.hermes/bin/{bw-unlock,kardex} : 700
- ~/.ssh/id_ed25519, config : 600

---

## 7. Deep Search Procedure

Quand un secret n'est pas trouvé immédiatement :

```bash
# 1. Vault exact
vault get <service>/<field>

# 2. Vault search
vault search <keyword>

# 3. Vault list avec valeurs
vault list --secrets

# 4. Bitwarden (si session active)
source ~/.hermes/vault/.bw_session_key 2>/dev/null
walter-secret search "<item>"   # métadonnées seulement ; valeur via {{bw:<id>:<champ>}}

# 5. Variables d'environnement
grep -ri "<keyword>" ~/.hermes/.env 2>/dev/null

# 6. Fichiers projet (fallback)
grep -ri "<keyword>" ~/projects/ 2>/dev/null | grep -v node_modules | head -10

# 7. Demander à l'utilisateur (dernier recours)
```

---

## 8. Ajouter un nouveau service

```bash
# Ajouter au vault
vault add mon_service api_key "sk-..."
vault add mon_service secret "whsec_..."

# Vérifier
vault get mon_service/api_key

# Exporter si besoin runtime
vault export >> ~/.hermes/.env
```

---

## 9. Walter Vault Broker (walter-vault)

Projet local à ~/projects/walter-vault — broker de credentials qui résout les secrets dans l'ordre de priorité :

1. Environment variables
2. Hermes auth.json (credential_pool)
3. Git credentials (~/.git-credentials)
4. Mcporter configs
5. Bitwarden CLI (si déverrouillé)

```bash
cd ~/projects/walter-vault
uv run python -m walter_vault.cli status
uv run python -m walter_vault.cli services
uv run python -m walter_vault.cli lookup github
uv run python -m walter_vault.cli lookup github --first --raw --secret-only
```
