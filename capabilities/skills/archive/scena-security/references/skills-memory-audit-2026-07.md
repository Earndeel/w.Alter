# Audit Skills + Mémoire Scena — Juillet 2026

Audit read-only du sous-système skills procéduraux + mémoire tenant dans le harness conversationnel Scena.

## Tables D1 et leur scoping tenant

| Table | Tenant-scoped ? | Colonne de scoping |
|-------|-----------------|---------------------|
| `agent_skills` | **NON (global)** | — |
| `workflow_step_skills` | **NON (global, lié au workflow)** | — |
| `workflow_packs` | NON | — |
| `workflow_steps` | NON | — |
| `client_workflow_prefs` | **OUI** | `client_id` |
| `tenant_agent_config` | **OUI** | `client_id` PK |
| `tenant_memory_entries` | **OUI** | `client_id` |
| `tenant_memory_events` | **OUI** | `client_id` |
| `tenant_projects` | **OUI** | `client_id` |
| `clients.context/summary/state` | **OUI** | `id` |

## Fichiers clés

- `workers/api/src/agent_context.ts` — Assemblage contexte (user.md, memory.md, project brief)
- `workers/api/src/agent.ts` — ReAct loop, `compactContext()`, `updateClientState()`
- `workers/api/src/workflow_library.ts` — CRUD `agent_skills`, `workflow_packs`, bindings, `getWorkflowPromptBundle`
- `workers/api/src/workflow_runner.ts` — `buildWorkflowExecutionMd` (skills dans exécution), `prepareWorkflowExecution`
- `workers/api/src/index.ts` — `resetClientMemory()` (l.1459), routes admin skills
- `d1/schema.sql` / `d1/schema-v2.sql` — Schémas D1
- `d1/workflow-skills.sql` — Tables skills autonomes

## 🔴 CRITIQUE — agent_skills global sans tenant_id

**Fichier** : `workflow_library.ts:100-102`, `d1/workflow-skills.sql:3-17`

La table `agent_skills` n'a **aucune colonne `client_id`**. Tous les tenants voient exactement le même catalogue.
- `listAgentSkills()` → `SELECT * FROM agent_skills` sans filtre
- `getAgentSkill()` → par `id` ou `slug` uniquement
- `upsertAgentSkill()` → écriture globale

**Remédiation** : Ajouter `tenant_id TEXT` (nullable, null = global/admin), filtrer `WHERE tenant_id IS NULL OR tenant_id = ?`.

## 🟡 MODÉRÉ — Chargement skills via workflow sans vérification tenant

**Fichier** : `workflow_library.ts:158-167`

`getWorkflowPackDetails()` charge les skills via `workflow_step_skills JOIN agent_skills` sans vérifier que le workflow est assigné au tenant appelant. Le filtrage est indirect (via `client_workflow_prefs` retournant les `workflow_id` assignés), mais si un `workflow_run_id` est passé directement (webhook), aucune vérification n'est faite.

## 🟡 MODÉRÉ — Contexte conversationnel non segmenté par projet

**Fichier** : `agent.ts:116-117, 594-596`

`clients.context` est un seul JSON array partagé entre tous les projets d'un client. Pas de tag `project_id` sur les messages. Si le client change de projet, le contexte contamine.

## 🟡 MODÉRÉ — resetClientMemory incomplet

**Fichier** : `index.ts:1459-1477`

`/reset` nettoie `clients`, `tenant_agent_config`, `tenant_memory_*`, `agent_log` mais **ne nettoie pas** :
- `workflow_runs` (restent en `waiting_async`)
- `workflow_step_runs`
- `workflow_artifacts`
- `video_jobs` / `image_jobs`

## 🟢 FAIBLE — Double écriture memory_summary_md

`compactContext()` (agent.ts:605-607) écrit `memory_summary_md` dans `tenant_agent_config` en plus de `clients.summary`. Risque de divergence.

## Tests existants couvrant le sous-système

| Test | Couvre |
|------|--------|
| `conversational-harness.test.mjs:563-580` | `partitionConversationContext()` |
| `conversational-harness.test.mjs:582-645` | `compactContext()` + persistance |
| `workflow-runner.test.mjs:285-308` | Skills dans `buildWorkflowExecutionMd()` |
| `workflow-library.test.mjs:94-140` | Isolation `client_workflow_prefs` |
| `telegram-ui.test.mjs:1634-1681` | `/reset` |

## Tests manquants

1. **Isolation agent_skills par tenant** — skills privés non visibles par autre tenant
2. **getWorkflowPackDetails() vérification d'accès** — refus workflow non assigné
3. **Contexte isolé par projet** — changement de projet vide/reconstruit le contexte
4. **active_project_id validation croisée** — `ensureProject()` vérifie `AND client_id = ?`
5. **resetClientMemory cleanup complet** — workflow_runs/artifacts orphelins nettoyés
6. **Compaction concurrente** — deux `updateClientState` ne s'écrasent pas