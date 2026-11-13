# core/engine/plugins — stratégies Walter du moteur (accueil, événements)

| | |
|---|---|
| **Rôle** | Les greffons Cordis par lesquels le moteur fait lui-même ce que `walter_hook.py` faisait pour lui (lot E2) : **intake** accueille un tour (texte du propriétaire, run par la passerelle Memory, ContextPlan et pack de contexte par le preflight walter-context, skills, un message `<walter-context>` injecté) ; **events** ferme le run du tour et publie `turn.ended` / `session.ended` sur le bus Walter. |
| **Propriétaire** | walter-core (`core/engine`). Interrupteurs : `[dsh.engine] intake = "hook" \| "shadow" \| "native"` `policy = "off" \| "enforce"` (policy + budget) `api = "off" \| "on"` (Engine API, `core/interfaces/api`, profil web seulement) et `subagents = "off" \| "on"` (sous-agents du noyau, profondeur ≤ 3, lot E5) dans `walter instance config core engine.toml` (défaut neutre `hook`), rendu par `walter harness install dsh`. |
| **État** | **En service depuis le 10/11/2026** sur `dsh-web` : `intake = native`, `policy = enforce`, `api = on`, `subagents = on` (activation E2–E8, `docs/03-MIGRATION.md`). Socle du 12/11 (`/walter/docs/SOCLE.md`) : contexte dégradé déclaré (A2), fenêtre du tour décidée par walter-context avant le premier appel de modèle (A1), issue structurée du run et reprise des runs orphelins après redémarrage (A4), plafonds du tour selon le niveau du plan (A7), porte et identifiant de requête sur le run (A8). |
| **Ne fait pas** | Ne choisit ni modèle (Router), ni intention (preflight), ni contenu de contexte (Context) ; n'écrit aucun run ni événement en mode `shadow` ; n'envoie jamais un message qui contient un secret au preflight ; ne remplace pas `SessionStart` ni `PostToolUse` (restent au hook) ; ne sert ni Claude Code ni Codex (`walter_hook.py` reste leur adaptateur). |
| **Contrats** | Accueil d'un tour v1 (`../contracts/turn-intake.v1.json`, 02-ARCHITECTURE § 4.2) ; ContextPlan v2 (walter-context) inchangé ; routes de la passerelle Memory `POST /v1/runs/start`, `/v1/runs/end`, `/v1/bus/emit`, `/v1/privacy/classify` (Bearer, jamais d'observation sur le bus) ; préflight `POST :8897/preflight[?inject=1]` ; walter-skills `POST :8891/v1/expose` ; fiche du run courant `@instance/state/runs/current/<pid>.json` (format `runctx`). |

## Fichiers

| Fichier | Contenu |
|---|---|
| `shared.mjs` | Réglages, texte du propriétaire (`source.kind === 'user'`, comme `dsh_owner_prompt`), clé de session `dsh/vm/<id>`, appel HTTP borné, observations privées, run courant par session ; plan du tour par session, dernier échange et statistiques du tour lus dans le journal, runs ouverts persistés |
| `intake/index.mjs` | `agent/pre-step` (en tête) : `shadow` observe à côté du pas sans le retarder ; `native` ouvre le run (clé d'idempotence par session, tour, pas et texte ; le run non terminé de la session est annulé, jamais celui qu'un même tour rejoué retrouve), demande le pack (repli sur le bloc mémoire ancien, filtré des secrets côté passerelle) et les skills en parallèle ; envoie au preflight le dernier échange de la session (`previous`, lu dans le journal) et le délai qu'il attend (`answer_within_ms` = `preflightTimeoutMs`, 7 s : le preflight répond dedans) ; garde le plan du tour (`turnPlans` : fil, acte, niveau, dégradé) ; **fenêtre** : avant le premier appel de modèle du tour, appelle l'entrée en processus de walter-context (`Symbol.for('walter.context.window')`, publiée par son port DSH — le noyau isole le service `compaction` dans un groupe, un greffon extérieur ne peut pas le résoudre) et note une ligne `kind: window` (appliquée ou non, raison, jetons avant/après) ; preflight injoignable → pack ancien **déclaré dégradé** au modèle (`context_source = legacy_degraded`) et événement `context.degraded` |
| `policy/index.mjs` | Lot E3 : la politique unique de Walter (`core/security`) avant chaque appel d'outil de chaque agent — garde monotone pour les refus « jamais », `tools/pre-execute` pour les demandes et le contrôle de divulgation ; le noyau décide encore après |
| `budget/index.mjs` | Lot E3 : plafonds du tour (pas, durée) — au plafond, consigne de conclure une fois ; après la marge, pas suivant refusé ; depuis le 12/11 les plafonds suivent l'effort énoncé par le plan du tour (`decision.effort` de Context : niveau de contexte relevé par la difficulté et par le travail à mener — pas le niveau de contexte seul ; `[dsh.budget.levels]` : point d'étape, pas, minutes), pour les tours du propriétaire seulement ; plan dégradé, tour machine ou sans plan : plafonds généraux |
| `events/index.mjs` | `agent/turn-stopping` → fin du run + `turn.ended` (une fois par run) ; tour fermé sans sa borne d'arrêt (interruption, erreur) → run `cancelled` ou `failed` dès que l'agent est au repos ; archivage d'une session → `session.ended` ; déchargement d'un agent → `session.ended` seulement avec `endOnDispose` (le noyau décharge aussi à chaque redémarrage du service : l'ombre dira quand) ; envoie l'**issue** du run (`outcome` : statut ok / failed / cancelled / interrupted, pas, appels d'outils, outils en erreur, erreur) ; au démarrage ferme les runs qu'un processus précédent a laissés ouverts (`open-runs.json`, issue `interrupted` / `engine_restart`, ligne `kind: recovery`) |

Mesures : `@instance/state/core/engine/intake/observations-<jour>.jsonl` (0600 ; empreintes et nombres, jamais le
texte). Ombre : lignes `observation: true`. Natif : temps par source (`run_ms`, `memory_ms`, `skills_ms`, `native_ms`).

**Refus ou défaut de transmission** (10/11) : la passerelle répond **403** avec un code stable quand elle refuse par
principe (`observation_not_on_production_bus`, `type_not_open`) — un refus d'autorisation attendu, jamais réessayé ;
422 = requête malformée (un défaut du greffon) ; pas de réponse, délai dépassé ou 5xx = **défaut de transmission**,
réessayé une fois (corps idempotents : `turn.ended/<run>`, `session.ended/<session>/<raison>`). Chaque livraison qui
n'a pas simplement réussi laisse une ligne `kind: delivery` (`outcome` refused | invalid | transport, `retried`) ;
l'accueil note `run_outcome` et `context_source` (pack | pack_degraded | legacy_degraded | legacy | none), le niveau du plan et `previous_sent`. `bench/e2_shadow.py` les compte à part.

## Bancs

- `../bench/e2_intake.py` : mêmes messages, foyers de test `hook` et `native` en alternance, DSH réel, canal `test`.
- `../bench/e2_shadow.py` : rapport de l'ombre (lecture seule) — couverture, texte identique, écarts d'intention
  (comptés contre l'accueil seulement si le texte diffère ; sinon bruit d'échantillonnage du modèle de décision),
  latence, `turn.ended` observés contre ceux du bus.

## Tests

`node --test core/engine/tests/plugins.test.mjs` (aussi par `walter-core-test`) ; composition :
`tests/test_composition.py::test_engine_intake_switch_hook_shadow_native_and_back` ; routes :
`/walter/cognition/memory/tests/test_gateway_engine.py`.

## Retour arrière

`intake = "hook"` puis `walter harness install dsh --apply` et redémarrage de `dsh-web` : lignes retirées, crochets
`UserPromptSubmit`/`Stop` et greffon `walter-owner-turn` rétablis (`walter-hooks.json` identique à l'octet, mêmes
lignes dans `cordis.patch.yml`). Sauvegardes : `@instance/backups/changes/2026-11-10-engine-E2/`.

`lineage.mjs` (lot E5) : parent d'un sous-agent lu dans l'en-tête de sa session (`parentSession`), partagé en
processus ; la politique juge un enfant sous la porte de sa racine, l'Engine API envoie ses demandes d'accord au client
de la racine, l'accueil range son run sous celui du parent.
