# core/engine/plugins — stratégies Walter du moteur (accueil, événements)

| | |
|---|---|
| **Rôle** | Les greffons Cordis par lesquels le moteur fait lui-même ce que `walter_hook.py` faisait pour lui (lot E2) : **intake** accueille un tour (texte du propriétaire, run par la passerelle Memory, ContextPlan et pack de contexte par le preflight walter-context, skills, un message `<walter-context>` injecté) ; **events** ferme le run du tour et publie `turn.ended` / `session.ended` sur le bus Walter. |
| **Propriétaire** | walter-core (`core/engine`). Interrupteurs : `[dsh.engine] intake = "hook" \| "shadow" \| "native"` `policy = "off" \| "enforce"` (policy + budget) et `api = "off" \| "on"` (Engine API, `core/interfaces/api`, profil web seulement) dans `walter instance config core engine.toml` (défaut neutre `hook`), rendu par `walter harness install dsh`. |
| **État** | Implémentés et testés le 10/11/2026 ; **en service : `hook`** (état d'E1, rien de monté). Essai réel en mode `native` dans un foyer DSH de test (`/opt/dsh/e2-home`), comparé au mode `hook` (`/opt/dsh/e2-hook-home`). L'ombre d'une semaine sur le service se met en route après l'adoption d'E1 (11/11 au soir). |
| **Ne fait pas** | Ne choisit ni modèle (Router), ni intention (preflight), ni contenu de contexte (Context) ; n'écrit aucun run ni événement en mode `shadow` ; n'envoie jamais un message qui contient un secret au preflight ; ne remplace pas `SessionStart` ni `PostToolUse` (restent au hook) ; ne sert ni Claude Code ni Codex (`walter_hook.py` reste leur adaptateur). |
| **Contrats** | Accueil d'un tour v1 (`../contracts/turn-intake.v1.json`, 02-ARCHITECTURE § 4.2) ; ContextPlan v2 (walter-context) inchangé ; routes de la passerelle Memory `POST /v1/runs/start`, `/v1/runs/end`, `/v1/bus/emit`, `/v1/privacy/classify` (Bearer, jamais d'observation sur le bus) ; préflight `POST :8897/preflight[?inject=1]` ; walter-skills `POST :8891/v1/expose` ; fiche du run courant `@instance/state/runs/current/<pid>.json` (format `runctx`). |

## Fichiers

| Fichier | Contenu |
|---|---|
| `shared.mjs` | Réglages, texte du propriétaire (`source.kind === 'user'`, comme `dsh_owner_prompt`), clé de session `dsh/vm/<id>`, appel HTTP borné, observations privées, run courant par session |
| `intake/index.mjs` | `agent/pre-step` (en tête) : `shadow` observe à côté du pas sans le retarder ; `native` ouvre le run (clé d'idempotence par session, tour, pas et texte ; le run non terminé de la session est annulé, jamais celui qu'un même tour rejoué retrouve), demande le pack (repli sur le bloc mémoire ancien, filtré des secrets côté passerelle) et les skills en parallèle |
| `policy/index.mjs` | Lot E3 : la politique unique de Walter (`core/security`) avant chaque appel d'outil de chaque agent — garde monotone pour les refus « jamais », `tools/pre-execute` pour les demandes et le contrôle de divulgation ; le noyau décide encore après |
| `budget/index.mjs` | Lot E3 : plafonds du tour (pas, durée) — au plafond, consigne de conclure une fois ; après la marge, pas suivant refusé |
| `events/index.mjs` | `agent/turn-stopping` → fin du run + `turn.ended` (une fois par run) ; tour fermé sans sa borne d'arrêt (interruption, erreur) → run `cancelled` ou `failed` dès que l'agent est au repos ; archivage d'une session → `session.ended` ; déchargement d'un agent → `session.ended` seulement avec `endOnDispose` (le noyau décharge aussi à chaque redémarrage du service : l'ombre dira quand) |

Mesures : `@instance/state/core/engine/intake/observations-<jour>.jsonl` (0600 ; empreintes et nombres, jamais le
texte). Ombre : lignes `observation: true`. Natif : temps par source (`run_ms`, `memory_ms`, `skills_ms`, `native_ms`).

**Refus ou défaut de transmission** (10/11) : la passerelle répond **403** avec un code stable quand elle refuse par
principe (`observation_not_on_production_bus`, `type_not_open`) — un refus d'autorisation attendu, jamais réessayé ;
422 = requête malformée (un défaut du greffon) ; pas de réponse, délai dépassé ou 5xx = **défaut de transmission**,
réessayé une fois (corps idempotents : `turn.ended/<run>`, `session.ended/<session>/<raison>`). Chaque livraison qui
n'a pas simplement réussi laisse une ligne `kind: delivery` (`outcome` refused | invalid | transport, `retried`) ;
l'accueil note `run_outcome` et `context_source` (pack | legacy | none). `bench/e2_shadow.py` les compte à part.

## Bancs

- `../bench/e2_intake.py` : mêmes messages, foyers de test `hook` et `native` en alternance, DSH réel, canal `test`.
- `../bench/e2_shadow.py` : rapport de l'ombre (lecture seule) — couverture, texte identique, écarts d'intention
  (comptés contre l'accueil seulement si le texte diffère ; sinon bruit d'échantillonnage du modèle de décision),
  latence, `turn.ended` observés contre ceux du bus.

## Tests

`node --test core/engine/tests/plugins.test.mjs` (aussi par `walter-core-test`) ; composition :
`tests/test_composition.py::test_engine_intake_switch_hook_shadow_native_and_back` ; routes :
`/walter/memory/tests/test_gateway_engine.py`.

## Retour arrière

`intake = "hook"` puis `walter harness install dsh --apply` et redémarrage de `dsh-web` : lignes retirées, crochets
`UserPromptSubmit`/`Stop` et greffon `walter-owner-turn` rétablis (`walter-hooks.json` identique à l'octet, mêmes
lignes dans `cordis.patch.yml`). Sauvegardes : `@instance/backups/changes/2026-11-10-engine-E2/`.
