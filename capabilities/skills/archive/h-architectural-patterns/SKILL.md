---
name: h-architectural-patterns
description: Architectural patterns extracted from external codebases (Paperclip, etc.) and adapted for Hermes orchestration. Session compaction, wakeup systems, concurrent locks, plugin contexts, and cost attribution patterns.
version: 1.0.0
author: W.Alter
---

# Hermes Architectural Patterns (extracted & adapted)

## When to Use

- Extracting reusable architectural patterns from external codebases for Hermes
- Implementing session compaction, wakeup systems, or concurrent locks
- Designing plugin contexts or cost attribution for Hermes orchestration
- Adapting patterns from Paperclip or similar agent frameworks

Patterns réutilisables extraits de codebases externes, analysés et adaptés pour l'orchestration Hermes/W.Alter.

## Workflow d'extraction

1. Cloner le repo cible dans `/tmp/<name>`
2. Scanner la structure : `find . -name "*.ts" -o -name "*.js" | head -100`
3. grep les mots-clés architecturaux : `session`, `compaction`, `heartbeat`, `plugin`, `lifecycle`, `wakeup`, `orchestrat`, `agent`
4. Lire les fichiers clés identifiés avec `read_file`
5. Extraire les patterns réutilisables, ignorer ce qui est redondant avec la stack native Hermes
6. Sauvegarder dans ce skill avec adaptations concrètes

## Patterns Paperclip extraits

### 1. Session Compaction Policy

**Source:** `packages/adapter-utils/src/session-compaction.ts`

**Pattern:** Système de politiques avec seuils déclenchant une rotation ou compaction de session :

```
SessionCompactionPolicy:
  enabled: bool
  maxSessionRuns: 200          # nb runs avant rotation
  maxRawInputTokens: 2_000_000 # tokens avant compaction
  maxSessionAgeHours: 72       # age max en heures
```

**Distinction clé:** Adapters avec `nativeContextManagement: "confirmed"` (Claude, Codex, Hermes) n'ont PAS besoin de rotation forcée -- ils gèrent leur propre contexte. Les autres (`unknown`) utilisent la politique par défaut.

**Adaptation Hermes:**
- Hermes gère son propre contexte (`confirmed`) mais peut utiliser les seuils comme **signaux** pour :
  - Déclencher un résumé/compactage du contexte quand on approche 2M tokens
  - Restart un subagent avec contexte pur si `maxSessionAgeHours` dépassé
  - Créer un handoff markdown pour transférer le contexte à un nouveau subagent
- Pour `delegate_task`: passer un `max_tokens` implicite dans le `context` quand la tâche est connue comme lourde

### 2. Heartbeat / Wakeup System

**Source:** `server/src/services/heartbeat.ts` (4234 lignes)

**Patterns clés:**

**a) Start Lock par Agent:**
```typescript
const startLocksByAgent = new Map<string, Promise<void>>();
// Serialise les démarrages concurrents pour un même agent
// Évite les race conditions quand 2+ triggers arrivent simultanément
```

**Adaptation Hermes:** Quand plusieurs events/tâches ciblent le même subagent ou la même session Hermes, utiliser un verrou implicite : ne pas lancer 2 `delegate_task` pour le même sujet en parallèle. Détecter les doublons via session_search avant de déléguer.

**b) Wakeup avec contexte:**
```
wakeup(agentId, {
  source: "timer" | "assignment" | "on_demand" | "automation",
  triggerDetail: "manual" | "ping" | "callback" | "system",
  reason: str,
  payload: { issueId, mutation, ... },
  requestedByActorType: "user" | "agent" | "system",
  contextSnapshot: { issueId, source, ... }
})
```

**Adaptation Hermes:** Pattern pour orchestrer les subagents asynchrones :
- Une cron détecte un changement → wakeup l'agent spécialisé avec un snapshot du contexte
- Le subagent reçoit TOUT le contexte dans son prompt (self-contained)
- Les sources : `timer` (cron), `user` (commande directe), `automation` (event webhook)

**c) Concurrent Runs Limit:**
Configurable (1-10 par defaut) avec file d'attente. Pour Hermes : limiter le nombre de subagents parallèles actifs sur un domaine pour éviter la saturation de contexte.

### 3. Plugin Context Pattern

**Source:** `packages/plugins/sdk/src/define-plugin.ts` + `server/src/adapters/plugin-loader.ts`

**Pattern:** Au lieu de passer N paramètres aux handlers, fournir un contexte unifié :

```
PluginContext {
  logger: Logger          // logging structuré
  events: EventSystem     // on("event", handler) / emit("event", data)
  jobs: JobQueue          // register("job-name", handler)
  config: ConfigStore     // get() / set() / onChange()
  secrets: SecretStore    // resolve(ref) → value
  http: HttpClient        // fetch avec auth injectée
  state: StateStore       // get/set par scope (company/user/plugin)
  data: DataRegistry      // register(query-handler) pour UI
}
```

**Adaptation Hermes:** Pour les subagents complexes, standardiser le template de contexte passé :
```
HermesContext:
  - task_description: str
  - working_directory: str
  - api_keys: {service: key, ...}
  - previous_results: [file_paths or summaries]
  - toolsets: [terminal, file, web]
  - max_iterations: int
  - session_notes: str  # contexte accumulé des subagents précédents
```

### 4. Cost Attribution per Task

**Source:** `server/src/services/costs.ts` + heartbeat.ts

**Pattern:** Chaque run est tracé avec coûts liés à `issueId` ET `projectId`, pas un compteur global. Les tokens (input/cached/output) sont normalisés et agrégés par scope.

**Adaptation Hermes:**
- Tagger les `delegate_task` avec un identifiant de tâche pour suivre les coûts
- Session Hermes : les coûts sont déjà trackés par run, mais on peut les corréler avec les tasks via cron jobs et subagent goals

### 5. Issue Assignment → Agent Wakeup

**Source:** `server/src/services/issue-assignment-wakeup.ts`

**Pattern:** Évent-driven simple -- quand une ressource est assignée à un agent, on envoie un wakeup avec le contexte de la ressource.

**Adaptation Hermes:** Quand Walter identifie une nouvelle tâche, il peut :
1. Assigner à un subagent spécialisé via `delegate_task`
2. Passer le contexte snapshot complet dans le prompt
3. Le subagent retourne son résultat → Walter synthétise

### 6. Execution Workspaces

**Source:** `server/src/services/execution-workspaces.ts`

**Pattern:** Espaces de travail isolés par tâche avec :
- Mode `shared` (projet) vs `isolated` (task session)
- Stratégie `git_worktree` pour isolation propre sans cloner
- Provision/teardown commands
- Runtime services (DB, cache) provisionnés automatiquement

**Adaptation Hermes:**
- Chaque subagent travaille dans son propre contexte isolé
- Utiliser `/tmp/task-<uuid>` pour les tasks nécessitant un filesystem propre
- Nettoyage automatique après completion
- Pour les tasks multi-étapes : partager un répertoire via `context`

## Patterns à ne PAS extraire (redondants avec Hermes)

| Paperclip Feature | Hermes Equivalent | Décision |
|---|---|---|
| Embedded PostgreSQL | SQLite state.db | Pas besoin |
| Paperclip Routines (cron) | Hermes cronjob tool | Natif |
| UI Parser per adapter | Vision / browser_snapshot | Natif |
| Company/Skill management | Hermes skills system | Natif |
| Live events / SSE | Telegram delivery | Pas pertinent |
| Budget tracking | OpenRouter cost tracking | Suffisant |
| Agent JWT auth | Internal orchestration | Pas besoin |

## Lessons apprises

1. **Paperclip est un orchestrateur d'agents coding** → Walter est un orchestrateur de tâches personnelles. Les patterns architecturaux sont transférables mais pas les fonctionnalités métier.
2. **Les adapters Paperclip reconnaissent Hermes** comme `nativeContextManagement: "confirmed"` → Notre gestion de contexte native est solide, pas besoin de rotation forcée.
3. **Le plugin system Paperclip est propre** mais trop lourd pour nos besoins. Garder les patterns de contexte unifié et de lifecycle, ignorer la machinerie.
4. **Session compaction est le pattern le plus précieux** pour les subagents de longue durée : seuils → handoff markdown → rotation propre.
