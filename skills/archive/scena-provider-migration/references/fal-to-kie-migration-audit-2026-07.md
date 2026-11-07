# Fal.ai → Kie.ai Migration Audit — Scena Worker

**Audit date:** 2026-07-22
**Scope:** `/root/projects/scena-cloudflare/` — read-only, no edits
**Principle:** Ne pas supprimer Fal (fallback/legacy). Faire de Kie le défaut partout où c'est un choix binaire.

---

## 1. Défauts runtime à changer (7 lignes TypeScript)

| File | Line | Current | → New |
|------|------|---------|-------|
| `agent.ts` | 1394 | `route.provider \|\| 'fal'` | `route.provider \|\| 'kie'` |
| `agent.ts` | 1396–1398 | `routeProvider === 'fal' ? ... : (hasRef ? 'fal-ai/nano-banana-2/edit' : 'fal-ai/nano-banana-2')` | Supprimer ce bloc — router vers `submitKieImageGeneration` si `routeProvider !== 'kie'` |
| `agent.ts` | 1912 | `requestedProvider === 'kie' ? 'kie' : 'fal'` | `requestedProvider \|\| 'kie'` |
| `saas_connect.ts` | 47–229 | `provider_hint: 'fal'` (×15 presets) | `'kie'` |
| `saas_connect.ts` | 48–230 | `model_hint: 'veo3'` (×14) / `model_hint: 'nano-banana-2/edit'` (×1) | `'bytedance/seedance-2-fast'` / `'gpt-image-2-image-to-image'` |
| `saas_connect.ts` | 429 | `providerKeys.fal ? 'fal' : 'kie'` | `'kie'` |
| `saas_connect.ts` | 837 | `return submitFalImageJob(...)` (fallback) | `return submitKieImageJob(...)` |

## 2. Pipeline runner fallbacks à changer (1 fichier)

| File | Line | Current | → New |
|------|------|---------|-------|
| `pipeline_runner.ts` | 855–875 | `else { submitFalVideoGeneration(...) }` | `submitKieVideoGeneration(...)` |
| `pipeline_runner.ts` | 173 | `defaultEndpoint = 'fal-ai/veo3'` | `'bytedance/seedance-2-fast'` |
| `pipeline_runner.ts` | 560–700 | `callFalImageGen(...)` sheets/storyboard | `callKieImageGen(...)` (créer si absent) |

## 3. Cron recovery à ajouter

| File | Line | Action |
|------|------|--------|
| `index.ts` | 422 | Ajouter `runKieVideoRecovery(env)` en parallèle de `runFalVideoRecovery` |

## 4. Tests à mettre à jour

| File | Lines | Action |
|------|-------|--------|
| `pipeline-runner.test.mjs` | 50 | `default_provider: 'fal'` → `'kie'` |
| `pipeline-runner.test.mjs` | 140–225 | Dupliquer les tests webhook Fal pour Kie ou élargir les mocks |
| `telegram-ui.test.mjs` | 460–495 | Ajouter test scheduled recovery Kie |
| `worker-regressions.test.mjs` | 417–527 | Élargir les mocks fetch pour accepter les deux providers |
| `orchestration-config.test.mjs` | 87–156 | Ajouter assertion sur l'entrée catalogue Kie |

## 5. Discrepance D1 ↔ TypeScript

**La D1 `scena-saas-db.sql` a déjà `default_provider='kie'` et tous les presets en `'kie'`.**
Le TypeScript `saas_connect.ts` a encore `provider_hint: 'fal'` sur les 15 presets en mémoire.
→ Aligner le TS d'abord, ou le `ON CONFLICT DO UPDATE` dans le seed D1 va ré-écrire `fal` au prochain seed.

## 6. Pièges

- **Colonne `image_jobs.fal_endpoint`** et `image_jobs."***"` sont utilisées même pour les tâches Kie (agent.ts:1346,1462). Ne pas renommer — garder le nom legacy, normaliser dans l'API admin.
- **`pollFalVideoResult` et `pollFalImageResult`** (agent.ts:2292,2647) sont les fonctions de polling primaires. Soit les renommer, soit créer des équivalents `pollKie*` et router dynamiquement.
- **Les branches Fal existantes doivent rester** — elles servent de fallback et de legacy. Le changement est sur les **défauts**, pas sur la suppression.

## 7. Ordre de migration recommandé

1. Changer les 7 défauts TS dans agent.ts + saas_connect.ts
2. Changer le fallback pipeline runner
3. Ajouter le cron recovery Kie dans index.ts
4. Déployer le Worker
5. Mettre à jour les tests (ne bloque pas le déploiement)
6. Vérifier en production que les nouvelles soumissions passent par Kie

## 8. Cartographie complète des emplacements Fal actifs

### agent.ts — Chat Agent (flux Telegram)
| Ligne | Élément | Problème |
|-------|---------|----------|
| 15 | `FAL_API_KEY: string` dans `Env` | À conserver (backward compat) |
| 3 | Commentaire `Fal.ai + Telegram` | Cosmétique |
| 416 | Prompt système mentionne `Fal` | Texte hard-codé |
| 421 | `"erreur Fal.ai"` dans prompt | Idem |
| 1394 | `route.provider \|\| 'fal'` | **DÉFAUT IMAGE = FAL** |
| 1403–1405 | `if (routeProvider === 'kie')` → gate Kie | Kie conditionnel |
| 1407–1423 | `falParams`, `falPayload`, POST `fal.run` | Génération Fal |
| 1463 | `pollFalImageResult(...)` | Polling image Fal |
| 1634 | `"Erreur de génération Fal.ai"` | Message Telegram |
| 1912 | `requestedProvider === 'kie' ? 'kie' : 'fal'` | **DÉFAUT VIDÉO = FAL** |
| 1921–1977 | Branche vidéo Fal Grok | |
| 1931 | Default endpoint Grok T2V/I2V | Hard-coded |
| 1963 | `pollFalVideoResult(...)` | Polling vidéo Fal |
| 2292–2410 | `pollFalVideoResult()` — 60×4s | Fonction entière |
| 2647–2719 | `pollFalImageResult()` | Fonction entière |
| 1091–1125 | `resizeImage()` → `fal-ai/flux/dev/image-to-image` | Fallback resize |

### index.ts — Router principal
| Ligne | Élément |
|-------|---------|
| 52 | `FAL_API_KEY` dans `Env` |
| 307–309 | Route `/webhook/fal-image` |
| 320–322 | Route `/webhook/saas/fal` |
| 325–327 | Route `/webhook/pipeline/fal-video` |
| 422 | `scheduled()` → `runFalVideoRecovery()` |
| 1579–1650 | `runFalVideoRecovery()` |
| 2136–2210 | `handleFalImageWebhook()` |

### saas_connect.ts — SaaS Connect
| Ligne | Élément |
|-------|---------|
| 14 | `FAL_API_KEY` dans `SaasConnectEnv` |
| 47–229 | 15 presets avec `provider_hint: 'fal'` |
| 429 | `createConnection` défaut Fal |
| 828–837 | `submitJob` branche Fal |
| 889–931 | `submitFalVideoJob()` |
| 980–1030 | `submitFalImageJob()` |
| 1372–1373 | `defaultModelForProvider()` → Fal |
| 1379–1385 | `normalizeFalVideoEndpoint()` |
| 1567 | `handlePipelineFalWebhook()` |

### pipeline_runner.ts — Pipeline autonome
| Ligne | Élément |
|-------|---------|
| 59 | `FAL_API_KEY` dans `PipelineEnv` |
| 161–215 | `submitFalVideoGeneration()` |
| 173 | `defaultEndpoint = 'fal-ai/veo3'` |
| 855–875 | Fallback `submitFalVideoGeneration` |
| 560–700 | `callFalImageGen` sheets/storyboard |
| 1395–1424 | `callFalImageGen()` |

### orchestration_config.ts — Catalogue
| Ligne | ID |
|-------|-----|
| 140–159 | `video-fal-grok-imagine-text` |
| 161–178 | `video-fal-grok-imagine-image` |
| 214–231 | `image-fal-nano-banana-2` |
| 233–250 | `image-fal-flux-dev-image-to-image` |
| 258 | `listFalEndpointCatalog()` |

### provider_payloads.ts — Contrats
| Ligne | Contrat |
|-------|---------|
| 110–121 | `fal:xai/grok-imagine-video/text-to-video` |
| 124–135 | `fal:xai/grok-imagine-video/image-to-video` |
| 139–157 | `fal:fal-ai/nano-banana-2` |
| 160–178 | `fal:fal-ai/nano-banana-2/edit` |
| 180–193 | `fal:fal-ai/veo3` |
| 194–207 | `fal:fal-ai/veo3/image-to-video` |
| 21–28 | Constantes `FAL_GROK_*` / `FAL_NANO_BANANA_*` |
| 400 | `normalizeFalNanoBananaParams()` |
| 428 | `buildFalImagePayload()` |
| 547 | `normalizeFalGrokVideoSettings()` |

### D1 Schemas
| File | Line | Description |
|------|------|-------------|
| `schema.sql` | 70 | `fal_endpoint TEXT DEFAULT ''` |
| `schema.sql` | 332 | `idx_image_jobs_fal_request` sur `"***"` |
| `scena-ops-db.sql` | 204 | Ligne système `provider.fal` |
| `scena-ops-db.sql` | 212 | Source recherche `source.fal-models` |

### Ops / Sentinel
| File | Line | Description |
|------|------|-------------|
| `ops_checks.ts` | 16 | `checkBinding('provider.fal', ...)` |
| `ops_research.ts` | 30–35 | `source.fal-models` monitoring |
