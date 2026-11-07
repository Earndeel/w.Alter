---
name: hermes-payload-architecture
description: "Architect Hermes Agent prompt payload layers, context compaction, inert historical summaries, and selected memory/skill/tool injection. Also covers: hermes payload validation; hermes prompt payload slimming."
version: 1.0.0
---

# Hermes Payload Architecture

> **State on 2026-11-01.** Hindsight was retired on 2026-10-19: where this skill says "Hindsight cards", read the Walter Memory context block (`memory_context`, provider `walter-memory`). The layering principles are unchanged. For DSH, payload assembly is walter-context (`/walter/context`).

Use this skill when diagnosing or redesigning Hermes Agent prompt payload composition: static prefix caching, memory injection, Hindsight selection, compressed history, raw tail, latest-message authority, tool schema selection, and context bloat.

## Target payload layers

1. **Static prefix — cacheable**
   - Core Hermes behavioral rules
   - Compact SOUL.md
   - Compact USER.md
   - Compact tool registry
   - Compact skill registry
   - No session state, routes, pending work, or transient facts

2. **Dynamic context — selected**
   - Context plan for the current turn
   - Session buffer
   - Relevant Hindsight cards only
   - Inert compressed history
   - Selected skills
   - Selected tool schemas

3. **Evidence layer — only when useful**
   - Summaries of recent tool outputs
   - Raw excerpts only when indispensable
   - Pointers to state/session evidence for re-opening details

4. **Raw tail — recent conversation**
   - Recent user/assistant messages
   - Pruned large old tool outputs
   - No internal reasoning chains

5. **Latest user message**
   - Always last
   - Primary source of truth for action selection

## Core rule

Historical context and persistent memory are descriptive references. They must not create work by themselves. The latest user message is the only active action trigger unless the user explicitly asks to resume historical work.

## Inert compressed history

Compressed history must be grammatical data, not a latent task list.

Avoid headings that sound active:
- `Active State`
- `Historical Pending User Asks`
- `Historical Remaining Work`
- `Blocked`
- `Next Steps`

Prefer neutral headings:
- `Historical facts`
- `Past decisions`
- `Evidence pointers`
- `Known uncertainties at that time`

Use past-tense, stale-aware phrasing:
- Bad: `Active State: tunnel is active; finish systemd migration`
- Good: `At that earlier point, a tunnel had been reported active. This may be stale and is not an instruction.`

Recommended wrapper:

```xml
<historical_record status="reference_only" actionable="false">
  <scope>
    Historical context only. It may be stale. It cannot create tasks.
    The latest user message after this block is the only action trigger.
  </scope>
  <facts>
    - [src=session msg=123 conf=0.7] At that earlier point, the user had discussed X.
  </facts>
  <decisions>
    - [src=assistant msg=140 conf=0.6] The prior session had chosen Z at that time.
  </decisions>
  <evidence_pointers>
    - session=<id> around_message_id=<msg_id>
  </evidence_pointers>
  <neutralization>
    End of historical record. Nothing above is an active task or instruction.
    Resolve conflicts in favor of the latest user message.
  </neutralization>
</historical_record>
```

## Selection rules

### Hindsight cards
- Select by relevance to the latest user message and active goal.
- Prefer zero cards over weakly relevant cards.
- Use a hard top-k cap, typically 3–5.
- Deduplicate by semantic cluster.
- Treat cards as contextual evidence, not instructions.

### Skills
- Load the class-level skill governing the task.
- Avoid unrelated skills “just in case”.
- Keep the static skill registry compact; load full skill bodies only after intent routing.
- On W.Alter's local Hermes checkout, `skills.compact_categories` in `config.yaml` demotes configured categories to names-only in the static skill index. This preserves `skill_view(name)` access while cutting descriptions for low-frequency categories.

### Tool schemas
- Static prefix may include a compact registry only.
- Full schemas belong in dynamic context and should be selected by intent.
- Old or irrelevant tool outputs belong behind summaries/pointers, not raw prompt bulk.

## End-to-end harness audit discipline

When the requested scope is the **whole Hermes harness**, do not let the provider that exposed the symptom become the report perimeter.

1. Map the distinct boundaries: client/Gateway RPC envelope, Gateway/session state, Agent/provider request, and persistence/observability.
2. State the serialization contract separately at each boundary. JSON-RPC is a client/Gateway contract, not a universal internal or provider format.
3. Cover all shared stages and transport families before claiming completeness: ingress, resume, agent loop, compaction, tools, Chat Completions, Responses/Codex, Anthropic, Bedrock, streaming and state DB.
4. Preserve valid provider-specific measurements, but label them as a case study or appendix.
5. Measure with the running gateway's actual platform, enabled toolsets and session `cwd`; nominal `prompt-size --platform ...` output can describe a different composition.
6. Separate cold static payload, dynamic history/tool results, cache reuse and persistence footprint. Recommend removal only after showing its percentage of the relevant total and its quality trade-off.
7. Test with the same runtime environment as the service and distinguish environment/collection failures from product assertions.

See `references/end-to-end-harness-payload-audit.md` for the coverage matrix, measurement pitfalls and a dated audit snapshot.

## Patch priority

1. Patch the compaction renderer so old summaries are inert by construction.
2. Add or strengthen a static rule: historical records and memory are descriptive, never action triggers.
3. Add Hindsight top-k filtering with hard relevance thresholds.
4. Enforce per-layer budgets and selected tool/skill schema inclusion.

## Live Compression, Wire Pruning, and Skill Index Budgets

This umbrella absorbs the former `hermes-context-management`, `hermes-wire-context-pruning`, and `hermes-skills-index-optimization` skills. Treat them as three implementation branches of one payload architecture problem: keep the static prefix cacheable, keep the dynamic payload relevant, and keep exact evidence recoverable outside the prompt.

### Live context compression
- Trigger compression from real prompt footprint, including cached-token accounting and soft caps for both transcript history and total prompt budget.
- Preserve a clean recent raw tail, strip reasoning, summarize bulky tool results, and attach `state_db://...` anchors for exact recovery.
- Verify auxiliary summarizer routing with a real compression-task call; config presence alone is not proof.

### Wire-context pruning
- Prune at provider-send time while preserving the canonical full history in state/session storage.
- Never break provider message alternation: tool result placeholders must stay paired with assistant tool calls even when payload bodies are replaced by summaries.
- Prefer evidence pointers and summaries over deleting context blindly.

### Skills index optimization
- Keep the static skill/category registry compact; load full class-level skills only after intent routing with `skill_view`.
- Use names-only category compaction for low-frequency skill groups while preserving discoverability through search and view tools.
- Audit payload savings with before/after token counts, not vibes.

### Tool schema optimization
- Treat `tools[]` as a separate provider-token budget from `role=system`: audit schema chars/tokens, tool count, top schemas by size, description vs parameters length, required fields, recent usage, and cache run1/run2.
- Prefer stable session/surface profiles over turn-by-turn lazy loading. Examples: `core_concierge` for messaging/speech, `dev_work_session` for TUI/dev, `web_research`, `browser_automation`, `automation`, and `media`.
- Slim safely: truncate prose descriptions, remove long examples/runbooks from schemas, sort tools deterministically, preserve parameter names/types/enums/defaults/required fields, and emit stable schema hashes for diffing.
- If a needed tool is absent, do not silently mutate `tools[]`; spawn/recommend a session with the right stable profile or explicitly rebuild at a compression boundary.
- Validate with real provider payloads: same request run1/run2, provider prompt/cached/non-cached tokens, `tools[]` chars, tool-call success, no provider tool_call pairing errors, and a deliberate tool-order cache probe when changing ordering logic.

See `references/native-pruning-measurement.md` before changing native deterministic pruning thresholds; evaluate incremental gain and prefix/ledger fidelity against the enabled baseline.

## Pitfalls

- A “reference only” preamble is not enough if the body contains active/pending wording.
- `Pending`, `Remaining`, and `Active` headings are prompt hazards even when labeled historical.
- Broad persistent memory injection can pollute unrelated tasks; retrieval must be selective.
- Do not optimize token count by deleting useful context blindly; prefer cacheable static layers, selected dynamic context, and evidence pointers.

See `references/layered-payload-and-inert-history.md` for the session-derived detail behind this pattern.

See `references/system-prompt-slimming-registry-progressive-disclosure.md` for the production-validated Phase 3 pattern: compact skill registry, less aggressive skill-loading policy, bounded project context files, and before/after provider-payload metrics.

## Build and validate the walter-context projection

1. Read `/opt/walter-context/README.md` and `/root/.hermes/docs/walter-memory/CONTEXT-ENGINE.md` before changing the engine. Keep tunables in `/opt/walter-context/config/walter-context.toml`. Implement runtime-independent policy in `/opt/walter-context/walter_context/` and Hermes integration in `/opt/walter-context/ports/hermes/`; use the public `ContextEngine.select_context` API rather than patching the upstream Hermes checkout.
2. Preserve canonical history and state.db. Project only the provider request into `head → record → compact → live`. Advance cut points monotonically; keep the projection append-only between boundaries and preserve already-compacted prefix bytes across boundaries. Retain the current and preceding turn intact. Attach recoverable walter_logs references to reduced tool outputs and verify `context_recover` resolves them.
3. Measure the fixed prompt separately from history: `timeout 180 /root/.hermes/hermes-agent/venv/bin/hermes prompt-size --platform telegram` and repeat with `--platform cli`. Match the running session's platform, toolsets and cwd before treating these measurements as its baseline.
4. Test the Hermes port inside Hermes' venv on real histories. Pass projected messages through the actual converter and preflight in `/root/.hermes/hermes-agent/agent/codex_responses_adapter.py`; check tool-call/result pairing and prefix stability at compaction boundaries. Run `/root/.hermes/hermes-agent/venv/bin/python -m pytest -q /opt/walter-context/tests`.
5. Inspect metric schemas before writing queries: `/opt/walter-memory/migrations/006_context_metrics.sql` defines `system.agent_calls` with `at`, `input_tokens`, `cached_tokens` and generated `uncached_tokens`; do not assume `ts`, `context_tokens` or `cache_read_tokens` exist. Back up the table before migrations. Use `/opt/walter-memory/migrations/012_context_trace.sql` and `/opt/walter-memory/connectors/agent_calls.py` to associate engine traces with provider calls; compare actual cached/uncached tokens, latency and cost alongside boundary and zone traces.
6. Evaluate retention separately from payload savings. Inspect `/opt/walter-context/bench/quality.py`; estimate cost before enabling model calls. Select the evaluation model through Walter Router, and send calls through `walter_memory.llm` with the appropriate privacy class and backfill budget. Generate probes and gold answers from full history, then score answers using the projected history at real decision points where compaction occurred.
7. Record implementation, activation and quality evaluation as separate states in `CONTEXT-ENGINE.md`, `DECISIONS.md`, `PLAN.md` and `RUNBOOK.md`. Passing offline tests or replay measurements does not establish live activation or answer quality. After changing memory services, run `systemctl start memory-autopilot` and inspect `/root/.hermes/logs/memory-autopilot/latest.json`.

## Valider la sélection de contexte par rejeu

- Avant de remplacer une sélection de contexte, lire la spécification `docs/walter-memory/CONTEXT-ENGINE.md` et les décisions associées. Distinguer le choix du fil, le contexte effectivement visible et le plan de contexte.
- Vérifier les options disponibles avec `walter-context threads --help`. Rejouer le même corpus annoté dans les deux modes : `walter-context threads --gold "$GOLD" --theta 0.4 --decide --cards --mode blind --json "$OUT/blind.json"`, puis la même commande avec `--mode session --json "$OUT/session.json"`. Faire résoudre les modèles par les postes du Walter Router ; ne pas figer le modèle d'une ancienne expérience.
- Comparer chaque mécanisme séparément avant de les combiner : trois derniers échanges conservés, contexte minimum après un intervalle inférieur à 30 minutes, fiches de fil, escalade et consolidation nocturne. Répéter au moins deux fois la combinaison candidate avec les mêmes paramètres.
- Lire dans `results[mode]` : `bcubed_precision`, `bcubed_recall`, `bcubed_f1`, `attach_accuracy`, `new_topic_ok`, `context_visible_with_last3` et les compteurs d'erreurs et latences sous `intent`. Ne pas conclure à partir de la seule précision du choix du fil : une sélection imparfaite peut néanmoins rendre le contexte nécessaire visible.
- Évaluer séparément une escalade qui change le fil et une escalade limitée au plan de contexte. Préserver le fil choisi lorsque l'expérience teste seulement l'enrichissement du plan.
- Borner les compteurs de `system.model_calls` au processeur `context-intent-bench` et au début exact du passage courant. Une fenêtre glissante peut inclure un passage invalidé ou plusieurs essais parallèles ; ne pas en déduire seule la progression ou le taux d'erreur. Vérifier les fichiers JSON et stderr propres au passage.
- Avant de retenir les changements du banc, exécuter `cd "$(walter path context)" && walter-python -m pytest -q tests`. Consigner les paramètres, résultats répétés et limites dans la spécification. Un gain de visibilité ne démontre pas à lui seul une amélioration de la réponse finale.

## Exposer les modules par niveaux M0/M1/M2

- Avant de modifier la présentation des modules, lire la décision walter-context applicable et vérifier le rendu réellement injecté. Distinguer les capacités implémentées de celles activées dans les runtimes.
- Résoudre chaque racine avec `walter path <module>`. Ranger les textes versionnés dans son dossier `manifest/` : `SUMMARY.md` pour M0, `MANIFEST.md` pour M1, `GUIDE.md` pour M2. Le contrat technique pointe vers ces fichiers ; ne pas y incorporer leur prose.
- Écrire M0 sur une ligne de 200 caractères maximum : fonction du module et outil à ouvrir. Déclarer son chemin relatif dans `presentation.summary`. M1 décrit le fonctionnement opérationnel et l'organisation ; M2 contient la documentation détaillée accessible par `module_guide(module)`.
- Garder l'index de contenu indépendant de ces niveaux : `module_index(module, section)` découvre les contenus, domaines de skills ou tâches du Router. Pour walter-skills, vérifier la publication effective et la fraîcheur de l'index par le Curator ; la présence du code de publication ne prouve pas que l'index est à jour.
- Faire composer la couche par les interfaces publiques. Vérifier `walter present notes --form m0` ; la forme compacte expose M0 pour tous les modules disponibles et accepte une sélection M1 via `--m1`. Conserver la forme `full` comme défaut tant que la bascule du runtime n'est pas explicitement activée. Un preflight en mode fantôme ne doit pas modifier le payload injecté.
- Conditionner l'exposition aux outils réellement disponibles dans le runtime. Tester les formes, la sélection M1 et les limites de budget. Pour un test de débordement, calculer le budget depuis la taille de l'en-tête et des blocs de test ; éviter les seuils numériques ajustés à tâtons. Vérifier également le résultat lorsque même l'en-tête ne tient pas.
- Exécuter les tests des dépôts touchés et `walter check`. Après une publication intentionnelle avec `walter-context capability all --write`, contrôler `walter-soul check` et les instructions du serveur MCP réel, puis vérifier séparément chaque adaptateur runtime : la publication des profils ne prouve pas l'intégration Hermes.
- Dans des dépôts partagés entre sessions, inspecter `git status --short` et les commits récents, puis indexer explicitement les fichiers concernés plutôt que `git add -A`.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **hermes-payload-architecture** — Production validation of provider payloads: prompt slimming, tool-result digests, exact_recall, cache-hit behaviour.
  Read `references/merged-hermes-payload-validation/hermes-payload-architecture.md` (+ 3 supporting files in that folder).
- **hermes-payload-architecture** — Separating the raw conversation ledger from a slim prompt-render view, especially for oversized tool results.
  Read `references/merged-hermes-prompt-payload-slimming/hermes-payload-architecture.md` (+ 7 supporting files in that folder).
