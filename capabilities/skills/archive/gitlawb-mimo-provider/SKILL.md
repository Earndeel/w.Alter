---
name: gitlawb-mimo-provider
description: Xiaomi MiMo 2.5 Pro endpoint via GitLawb OpenGateway — OpenAI-compatible, API key required.
version: 1.0.0
metadata:
  hermes:
    tags: [provider, free, mimo, gitlawb, openclaude]
---

## When to Use

- Need a free LLM provider for non-critical tasks
- OpenRouter credits exhausted or rate-limited
- Want to use Xiaomi MiMo models (mimo-v2.5-pro, mimo-v2-flash, etc.)
- Looking for an OpenAI-compatible endpoint as fallback

## Pitfalls

- **402 errors (cycliques)** : GitLawb proxies through OpenRouter — `Insufficient credits` means GitLawb's account is out of funds, not a config issue. **Récurrent** : les crédits s'épuisent et sont rechargés périodiquement. Vérifier l'état avec un ping avant usage critique.
- **Rate limits** : Unknown — watch for 429 responses
- **Regional latency**: Endpoint is Fly.io hosted, may have variable latency
- **Free period ended**: Auth required since May 22, 2026 — ensure GITLAWB_API_KEY is set

---

# GitLawb MiMo Provider

GitLawb (@gitlawb) partnered with Xiaomi MiMo to provide free access to MiMo models through OpenGateway. OpenClaude v0.11.0 ships with this built-in.

**Endpoint:** `https://opengateway.gitlawb.com/v1/xiaomi-mimo`
**Auth:** `Authorization: Bearer <API_KEY>` (required since ~May 22, 2026)
**Key stored in:** Vault (`gitlawb/api_key`), Hermes `.env` (`GITLAWB_API_KEY`)
**Format:** OpenAI-compatible chat completions

## Models Available

| Model | Notes |
|-------|-------|
| `mimo-v2.5-pro` | Best, 53.8 intel on AA, ~Kimi K2.6 level |
| `mimo-v2.5` | |
| `mimo-v2-pro` | |
| `mimo-v2-flash` | Fast/cheap |
| `mimo-v2-omni` | Multimodal |

### NOT available via GitLawb

- **mimo-v2.5-pro-ultraspeed** : ~1000 tokens/s, 1T params. Application-only via `platform.xiaomimimo.com/ultraspeed` (compte Xiaomi requis). Trial limitée 9-23 juin 2026. Prix API = 3× mimo-v2.5-pro standard. Chat gratuit sur `ultraspeed.xiaomimimo.com` pendant l'essai. Contact business: `business-mimo@xiaomi.com`. Formulaire : nom, téléphone (code pays modifiable, +86 par défaut), email, entreprise, industrie (dropdown), use case (dropdown), commentaires (500 car. max). Capacité limitée, approbation quotidienne, priorité aux organisations pro. Détails formulaire et flow dans `references/ultraspeed-application.md`.

## Hermes Config

Example config (providers section):

```yaml
providers:
  gitlawb:
    api: https://opengateway.gitlawb.com/v1/xiaomi-mimo
    key_env: GITLAWB_API_KEY
    default_model: mimo-v2.5-pro
    models:
    - mimo-v2.5-pro
    - mimo-v2.5
    - mimo-v2-pro
    - mimo-v2-flash
    - mimo-v2-omni
    name: GitLawb (MiMo)
```

## Usage

```bash
# One-shot
hermes chat --provider gitlawb --model mimo-v2.5-pro -q "question"

# Set as default
hermes config set model.provider gitlawb
hermes config set model.default mimo-v2.5-pro

# Revert to previous
hermes config set model.provider openai-codex
hermes config set model.default gpt-5.5
```

## Status: AUTHENTICATED — crédits cycliques (10 juin 2026)

**402 phase (récurrente) :** GitLawb's OpenRouter credits s'épuisent et se rechargent cycliquement. Observations :
- ~22 mai 2026 : première exhaustion → 402
- ~10 juin 2026 : retour en 402 (crédits épuisés à nouveau)
L'état 402 est donc **récurrent** et non un événement ponctuel. Vérifier avant utilisation critique.

**401 phase:** Endpoint required API key (`"API key required"`). Free period ended.
**Now authenticated** with API key `ogw_live_...` — stored in vault (`gitlawb/api_key`) and `.env` (`GITLAWB_API_KEY`). Config uses `key_env: GITLAWB_API_KEY`.

### Alternatives si GitLawb est en 402

**OpenRouter** — MiMo 2.5 Pro disponible à ~$0.000000435/K tokens prompt (quasi gratuit) :
```bash
# Config Hermes
hermes config set model.provider openrouter
hermes config set model.default xiaomi/mimo-v2.5-pro
```
Le modèle sur OpenRouter a 1M de contexte et ne nécessite pas de clé dédiée.

**Xiaomi direct (token-plan-sgp.xiaomimimo.com)** — nécessite `XIAOMI_API_KEY` dans l'environnement. La clé vault n'est plus valide (401) — à régénérer depuis le console Xiaomi si besoin.

## Endpoint & Auth

**Endpoint:** `https://opengateway.gitlawb.com/v1/xiaomi-mimo`
**Auth:** `Authorization: Bearer <API_KEY>`
**Key stored in:** Vault (`gitlawb/api_key`), Hermes `.env` (`GITLAWB_API_KEY`)

## Sources

- Free period (May 13-22, 2026) ended. Endpoint now requires API key.
- **Credit exhaustion (402) — RÉCURRENT**: GitLawb proxies through OpenRouter. Error `"Insufficient credits."` means GitLawb's OpenRouter account is out of funds, not a Hermes config issue. `/models` still works but `/chat/completions` returns 402. Première occurrence : 2026-05-22. Récurrence : 2026-06-10. Ce n'est pas un état stable — les crédits sont probablement rechargés manuellement par GitLawb selon leur budget.
- **API key required (401)**: Happened ~May 22. Endpoint now requires `Authorization: Bearer <key>` header.
- Rate limits unknown — monitor for 429s
- Reasoning tokens are included in response (mimo-v2.5-pro)
- Endpoint is Fly.io hosted, may have regional latency

## Watchdog Cron (auto-detection)

The watchdog cron was removed on 2026-05-22 since the endpoint is now authenticated and stable. If monitoring is needed again, recreate with the same pattern but add `Authorization: Bearer *** header to the test curl.

## Source

Twitter announcement by @kevincodex (GitLawb co-founder) on May 13, 2026.
OpenClaude v0.11.0 released May 15 with built-in integration.
