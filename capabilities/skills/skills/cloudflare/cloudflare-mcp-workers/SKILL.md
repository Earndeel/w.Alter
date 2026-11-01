---
name: cloudflare-mcp-mastery
category: cloud
description: Complete mastery of Cloudflare via MCP/mcporter -- 89 tools across Workers, KV, R2, D1, AI, Queues, Workflows, Zones, Routes, Cron, Secrets, Analytics, and more. Includes working patterns, auth resolution, and deployment pipelines.
---

# Cloudflare MCP Mastery via mcporter

## Authentification & Configuration

### Comptes
- **Email**: `lucas.jouvencon@gmail.com`
- **Account ID**: `«secret:vault»`
- **Global API Key** (compromis): `<secret retiré — clé globale Cloudflare : walter-cloudflare l'injecte (CLOUDFLARE_API_KEY)>`

### Emplacement config mcporter
**ATTENTION**: mcporter ne lit PAS `~/.hermes/mcp/mcporter.json`. Il cherche UNIQUEMENT dans :
- `/root/.mcporter/mcporter.json` (system config)
- `/root/config/mcporter.json` (project config)

TOUJOURS copier le fichier dans `/root/.mcporter/mcporter.json` apres l'avoir ecrit.

### mcporter.json --- Ecriture manuelle obligatoire
Le fichier `.env` de Hermes et le mcporter.json sont deux configs distinctes. Hermes lit `~/.hermes/.env`, mcporter lit `~/.mcporter/mcporter.json`.

TOUJOURS ecrire le JSON a la main. `mcporter config add` masque le token (`***`) dans le fichier.

```json
{
  "mcpServers": {
    "cloudflare": {
      "command": "npx",
      "args": ["-y", "@cloudflare/mcp-server-cloudflare", "run", "«secret:vault»"],
      "env": {
        "CLOUDFLARE_API_TOKEN": "<TOKEN_ICI>",
        "CLOUDFLARE_ACCOUNT_ID": "«secret:vault»"
      }
    }
  }
}
```

### Auth : Global API Key vs API Token
| Feature | Global API Key (`X-Auth-Key`) | API Token (`Bearer`) |
|---|---|---|
| wrangler CLI | **OUI** | OUI |
| API REST directe | **OUI** | OUI |
| MCP Server officiel | **NON** (error 10000) | **OUI** |
| Porteees | Tout le compte | Scopes restreints |

**Pour mcporter + MCP**: il FAUT un **API Token**. Creer via Dashboard > My Profile > API Tokens > Create Token.
- Template recommande: **"Edit Cloudflare Workers"** puis ajouter `Zone > DNS > Edit` + **All Zones**.
- Token actuel: `<secret retiré — token Cloudflare : walter-cloudflare l'injecte (CLOUDFLARE_API_TOKEN)>` (creer 2026-04-05)

### Fallback: Global Key quand le MCP est bloque
Si le MCP ne repond pas (token expire, revoke, etc.), la Global API Key reste utilisable pour **TOUT faire** via deux methodes equivalents couvrant les 89 outils :

1. **wrangler CLI** -- couvre Workers, KV, R2, D1, Queues, DNS, Routes, Cron, Secrets, Pages. Toutes les commandes `wrangler` fonctionnent avec `CLOUDFLARE_API_KEY` + `CLOUDFLARE_EMAIL`.
2. **API REST Cloudflare v4** -- couvre TOUT le reste (billing, analytics, Zero Trust, WAF, etc.). Headers: `X-Auth-Email` + `X-Auth-Key`. Endpoint base: `https://api.cloudflare.com/client/v4/`

**Strategie agent**: Utiliser le MCP en priorite pour les 89 outils (API Token). Si `isError: true` avec auth error 10000, basculer automatiquement sur wrangler (pour Workers/KV/R2/D1) ou API REST (pour le reste).

## Catalogue complet des 89 outils MCP

### Workers (compute serverless)
| Tool | Description | Params cles |
|---|---|---|
| `worker_list` | Lister tous les Workers | -- |
| `worker_get` | Recuperer le code source d'un Worker | `name` |
| `worker_put` | Creer/mettre a jour un Worker | `name`, `script`, `bindings?`, `compatibility_date?`, `migrations?` |
| `worker_delete` | Supprimer un Worker | `name` |
| `worker_deploy` | Deployer depuis fichier ou contenu | `name`, `filePath?`, `scriptContent?`, `bindings?` |

### KV (key-value store)
| Tool | Description |
|---|---|
| `get_kvs` | Lister les namespaces KV |
| `kv_get` | Lire une valeur (`namespaceId`, `key`) |
| `kv_put` | Ecrire une valeur (`namespaceId`, `key`, `value`, `expirationTtl?`) |
| `kv_delete` | Supprimer une cle (`namespaceId`, `key`) |
| `kv_list` | Lister les cles avec prefixe (`namespaceId`, `prefix?`, `limit?`) |

### R2 (object storage S3-like)
| Tool | Description |
|---|---|
| `r2_list_buckets` | Lister les buckets |
| `r2_create_bucket` | Creer un bucket (`name`) |
| `r2_delete_bucket` | Supprimer un bucket (`name`) |
| `r2_list_objects` | Lister les objets (`bucket`, `prefix?`, `delimiter?`, `limit?`) |
| `r2_get_object` | Telecharger un objet (`bucket`, `key`) |
| `r2_put_object` | Uploader un objet (`bucket`, `key`, `content`) |
| `r2_delete_object` | Supprimer un objet (`bucket`, `key`) |

### D1 (database SQL edge)
| Tool | Description |
|---|---|
| `d1_list_databases` | Lister les bases D1 |
| `d1_create_database` | Creer une base (`name`) |
| `d1_delete_database` | Supprimer une base (`databaseId`) |
| `d1_query` | Executer du SQL (`databaseId`, `query`, `params?`) |

### Durable Objects (state persistant)
| Tool | Description |
|---|---|
| `do_list_namespaces` | Lister les namespaces DO |
| `do_get_object` | Recuperer un objet DO (`namespaceId`, `objectId`) |
| `do_list_objects` | Lister les objets DO (`namespaceId`, `limit?`) |
| `do_delete_object` | Supprimer un objet DO (`namespaceId`, `objectId`) |

### Queues (messagerie asynchrone)
| Tool | Description |
|---|---|
| `queue_list` | Lister les queues |
| `queue_create` | Creer une queue |
| `queue_delete` | Supprimer une queue |
| `queue_send` | Envoyer un message (`queueId`, `message`) |
| `queue_send_batch` | Envoyer des messages en lot |
| `queue_get_message` | Recuperer un message |
| `queue_get_messages` | Recuperer plusieurs messages |
| `queue_delete_message` | Supprimer un message (`queueId`, `messageId`, `receiptHandle`) |
| `queue_update_visibility` | Changer la visibilite d'un message |

### AI (Workers AI inference)
| Tool | Description |
|---|---|
| `ai_inference` | Inference generique (`model`, `input`, `options?`) |
| `ai_list_models` | Lister les modeles disponibles |
| `ai_get_model` | Details d'un modele (`model`) |
| `ai_embeddings` | Embeddings (`model`, `text`) |
| `ai_text_generation` | Generation de texte (`model`, `prompt`, `options?`) |
| `ai_image_generation` | Generation d'image (`model`, `prompt`, `options?`) |

### Workflows (orchestration etape par etape)
| Tool | Description |
|---|---|
| `workflow_list` | Lister les workflows |
| `workflow_get` | Details d'un workflow (`workflowId`) |
| `workflow_create` | Creer un workflow (`name`, `content`) |
| `workflow_update` | Mettre a jour un workflow (`workflowId`, `content`) |
| `workflow_delete` | Supprimer un workflow (`workflowId`) |
| `workflow_execute` | Executer un workflow (`workflowId`, `input?`) |

### Templates
| Tool | Description |
|---|---|
| `template_list` | Lister les templates disponibles |
| `template_get` | Details d'un template (`templateId`) |
| `template_create_worker` | Creer un Worker depuis un template (`templateId`, `name`, `config?`) |

### Zones & DNS
| Tool | Description |
|---|---|
| `zones_list` | Lister toutes les zones |
| `zones_get` | Details d'une zone (`zoneId`) |

### Routes & Domaines
| Tool | Description |
|---|---|
| `route_create` | Mapper une URL a un Worker (`zoneId`, `pattern`, `scriptName`) |
| `route_delete` | Supprimer une route (`zoneId`, `routeId`) |
| `route_list` | Lister les routes d'une zone (`zoneId`) |
| `route_update` | Mettre a jour une route |
| `domain_list` | Lister les domaines custom sur Workers |

### Cron Triggers (scheduled Workers)
| Tool | Description |
|---|---|
| `cron_create` | Creer un trigger cron (`scriptName`, `cronExpression`) |
| `cron_delete` | Supprimer un trigger cron (`scriptName`) |
| `cron_list` | Lister les triggers cron d'un Worker (`scriptName`) |
| `cron_update` | Mettre a jour un trigger cron |

### Secrets & Env Vars
| Tool | Description |
|---|---|
| `secret_put` | Ajouter un secret chiffre (`scriptName`, `secretName`, `secretValue`) |
| `secret_delete` | Supprimer un secret (`scriptName`, `secretName`) |
| `secret_list` | Lister les secrets d'un Worker (`scriptName`) |
| `env_var_set` | Définir une variable d'env (`scriptName`, `key`, `value`) |
| `env_var_delete` | Supprimer une var d'env |
| `env_var_list` | Lister les vars d'env |
| `env_var_bulk_set` | Set multiple vars d'un coup (`scriptName`, `vars`) |

### Service Bindings (Worker-to-Worker)
| Tool | Description |
|---|---|
| `service_binding_create` | Lier deux Workers (`scriptName`, `bindingName`, `service`) |
| `service_binding_delete` | Supprimer un binding |
| `service_binding_list` | Lister les bindings d'un Worker |
| `service_binding_update` | Mettre a jour un binding |

### Analytics
| Tool | Description |
|---|---|
| `analytics_get` | Analytics d'une zone (`zoneId`, `since?`, `until?`) |
| `workers_analytics_search` | Analytics des Workers (`accountId`, `scriptName?`, `startTime?`, `endTime?`, `limit?`, `status?`) |

### Worker Patterns Factory (custom domains)
| Tool | Description |
|---|---|
| `wfp_create_dispatch_namespace` | Creer un namespace de dispatch (`name`) |
| `wfp_delete_dispatch_namespace` | Supprimer un namespace |
| `wfp_list_dispatch_namespaces` | Lister les namespaces |
| `wfp_add_custom_domain` | Ajouter un domaine custom |
| `wfp_remove_custom_domain` | Retirer un domaine custom |
| `wfp_list_custom_domains` | Lister les domaines custom |

### Versions & Rollback
| Tool | Description |
|---|---|
| `version_list` | Lister les versions d'un Worker (`scriptName`) |
| `version_get` | Recuperer une version (`scriptName`, `versionId`) |
| `version_rollback` | Rollback vers une version (`scriptName`, `versionId`) |

### Wrangler Config
| Tool | Description |
|---|---|
| `wrangler_config_get` | Lire le wrangler.toml distant (`scriptName`) |
| `wrangler_config_update` | Mettre a jour le wrangler.toml distant |

## Workflows de deploiement

### Pattern 1: worker_put via MCP (API Token requis)
```bash
mcporter call cloudflare.worker_put \
  name=mon-worker \
  scriptContent="export default { async fetch(request) { return new Response('Hello'); } }" \
  compatibility_date="2024-01-01"
```

### Pattern 2: worker_deploy via MCP (depuis fichier)
```bash
mcporter call cloudflare.worker_deploy \
  name=mon-worker \
  filePath=/chemin/vers/index.js \
  compatibility_date="2024-01-01"
```

### Pattern 3: wrangler CLI (Global Key OK)
```bash
# Dans un dossier PROPRE et vide
cd /tmp/deploy-xyz
cat > index.js << 'EOF'
export default {
  async fetch(request) {
    return new Response("Hello", { headers: {"content-type": "text/html"} });
  }
}
EOF
cat > wrangler.toml << 'EOF'
name = "mon-worker"
main = "index.js"
compatibility_date = "2024-01-01"
EOF
CLOUDFLARE_API_KEY="cfk_..." CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" wrangler deploy --no-bundle
```

### Pattern 4: API REST directe (Global Key OK, pour automation Python)
```python
import urllib.request, json

CF_KEY = "cfk_..."
CF_EMAIL = "lucas.jouvencon@gmail.com"
CF_ACCOUNT = "«secret:vault»"

with open("/path/to/worker.js") as f:
    script = f.read()

req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/workers/scripts/mon-worker",
    data=script.encode("utf-8"),
    headers={"X-Auth-Email": CF_EMAIL, "X-Auth-Key": CF_KEY, "Content-Type": "application/javascript"},
    method="PUT"
)
resp = urllib.request.urlopen(req)
```

## Combinaisons puissantes (exemples d'usage)

### Worker + KV (cache/clef-valeur)
```json
// worker_put avec binding KV
{
  "name": "mon-app",
  "script": "...",
  "bindings": [
    {"type": "kv_namespace", "name": "MY_KV", "namespace_id": "abc123"}
  ],
  "compatibility_date": "2024-01-01"
}
```
Le Worker accede via `env.MY_KV.get()` et `env.MY_KV.put()`.

### Worker + R2 (site statique / CDN)
1. `r2_create_bucket` name=mon-site
2. `r2_put_object` bucket=mon-site key=index.html content="..." 
3. `worker_put` avec binding R2 pour servir les fichiers

### Worker + D1 (API avec base SQL)
1. `d1_create_database` name=mon-app-db
2. `d1_query` databaseId=xyz query="CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT)"
3. `worker_put` avec binding D1 + code qui fait des requetes SQL

### Worker + AI (inference edge)
Worker qui appelle `@cloudflare/ai` ou le MCP `ai_text_generation` directement pour du chat/streaming depuis le edge.

### Worker + Queue (traitement asynchrone)
1. `queue_create` pour creer une file d'attente
2. Worker productor qui envoie des messages via `queue_send`
3. Worker consumer branche sur la queue pour traiter en arriere-plan

### Worker + Cron (tasks schedulees)
1. Deploier un Worker avec la logique
2. `cron_create` scriptName=mon-worker cronExpression="0 */6 * * *" (toutes les 6h)

### Worker + Secrets (API keys securisees)
1. `secret_put` scriptName=mon-api secretName=STRIPE_KEY secretValue="sk_live_..."
2. Le Worker y accede via `env.STRIPE_KEY` -- jamais en clair dans le code

## Pipelines d'automatisation

### Pipeline: heberger un site HTML statique sur R2 + Worker
1. Creer le bucket R2
2. Uploader les fichiers HTML/CSS/JS avec `r2_put_object`
3. Creer un Worker qui fait proxy vers le bucket R2
4. Optionnel: ajouter un domaine custom avec `wfp_add_custom_domain`

### Pipeline: API REST complete
1. `d1_create_database` pour la persistance
2. `secret_put` pour les cles API externes
3. `worker_put` avec bindings D1 + secrets
4. `route_create` pour mapper un domaine custom
5. `cron_create` pour les taches de maintenance

### Pipeline: agent AI autonome
1. Worker avec binding AI
2. `kv_put` pour stocker l'historique de conversation
3. Worker accessible en HTTP pour recevoir/servir des prompts

## Pitfalls & Solutions

1. **MCP + Global API Key = Authentication error 10000**
   - Le MCP envoie `Authorization: Bearer`, la Global Key attend `X-Auth-Key`
   - Solution: creer un API Token OU utiliser wrangler/API REST en fallback

2. **wrangler embarque TOUT le repertoire courant**
   - TOUJOURS creer un dossier propre et vide avant de deployer
   - Utiliser `--no-bundle` pour eviter l'inclusion de node_modules

3. **JS inline dans Python/JSON = SyntaxError 10021**
   - Les backticks et caracteres speciaux cassent le parsing
   - TOUJOURS ecrire le JS sur disque puis passer le chemin

4. **mcporter call syntax pour les objets complexes**
   - `mcporter call cloudflare.worker_put name=foo script="..."` fonctionne
   - Pour les bindings JSON complexes, utiliser `--args '{"name":"...", "script":"...", "bindings":[...]}'`

5. **Durable Objects necessitent des migrations**
   - La premiere deploy d'un DO requiere `migrations` avec `new_sqlite_classes` ou `new_classes`
   - Sans migration, erreur 10061 au deploy

6. **Compatibility date**
   - TOUJOURS specifier une `compatibility_date` recente (ex: "2024-01-01" ou plus)
   - Sans date, le Worker utilise une date par defaut qui peut etre obsolete

7. **Nettoyage post-deploy**
   - Supprimer les dossiers temporaires apres deployment
   - Ne pas laisser trainer de fichiers `.jsonl.deleted` contenant des credentials