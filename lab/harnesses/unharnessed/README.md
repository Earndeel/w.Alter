# Unharnessed sur Walter (essai Lab)

| | |
|---|---|
| **Rôle** | Brancher le harness tiers Unharnessed (un seul outil : un REPL Python persistant) sur Walter par ses interfaces publiques, et le comparer au moteur actuel (DSH) sur les mêmes messages. |
| **Propriétaire** | walter-lab ; essai demandé par le propriétaire le 2026-11-16. |
| **État** | essai, hors production. Rien n'est appliqué au moteur ni aux modules. |
| **Ne fait pas** | Servir une porte (Telegram, web, API) ; écrire dans walter_logs ; émettre sur le bus ; remplacer DSH. |
| **Contrats** | CLI `bin/walter-unharnessed` (setup, check, prompt, run) ; banc `bench.py`. Logiciel tiers : `/apps/unharnessed`. |

## Ce que Walter fournit à Unharnessed

| Besoin | Branchement | Interface Walter |
|---|---|---|
| Modèle | fournisseur `walter` de `models.json`, modèle = poste du Router (`auto` par défaut) | walter-llm :8894, agent `unharnessed-lab` (jeton `@instance/bootstrap/lab/unharnessed-llm.env`) |
| Run | un run par message, canal `test` (plafond 2 €/24 h des essais), son id dans l'en-tête `X-Walter-Run-Id` | `walter_memory.runs` |
| Contexte | pack walter-context (comme DSH depuis le 07/11), repli bloc mémoire ; plan de modèle écrit sur le run, lu par `auto` | préflight :8897, passerelle mémoire :8890, `walter_skills.client` |
| Outils | serveur MCP `walter` (tag client `unharnessed`), appelé depuis le noyau : `await mcp.call_tool("walter", …)` | `/opt/walter-core/server.py` |
| Identité | profil walter-soul neutre (rendu `dsh`) + `profile/unharnessed.md`, ajoutés au prompt système | `walter-soul render`, `walter instance render` |

Unharnessed n'a ni hooks ni permissions : l'adaptateur fait ce que `walter_hook.py` fait pour Claude Code et DSH
(ouvrir/fermer le run, préparer le contexte), et l'exécute dans une **bulle systemd** : tout le système en lecture
seule sauf `@instance/state/lab/unharnessed`, `/tmp` privé, ni socket Docker, ni clés SSH, ni bus système (donc pas de
`systemctl start/stop`), plafonds mémoire 6 Go / 512 tâches / 3 cœurs / durée. Même utilisateur (root) : une bulle,
pas une prison ; il lit ce que le serveur MCP doit lire.

## Utilisation

```
walter-unharnessed setup      # models.json, MCP walter, venv du noyau (idempotent)
walter-unharnessed check
walter-unharnessed run [--task auto|general|coding] [--context pack|legacy|off] [--workdir NOM] "message"
bench.py [--only fichiers,web] [--repeats N]   # DSH vs Unharnessed, rapport dans @instance/state/lab/unharnessed/bench/
```

État : `@instance/state/lab/unharnessed/` (`agent/` = sessions et réglages d'Unharnessed, `workspace/`, `cache/` =
venv du noyau et cache uv, `runs/` = flux JSON bruts et `summary.jsonl`).

## Résultats du 2026-11-16 (une passe, rapport `@instance/state/lab/unharnessed/bench/20261116T101421.json`)

Mêmes 5 messages, même pack walter-context, même `auto` : les deux moteurs ont reçu **les mêmes modèles** à chaque
cas (GPT 6.1 Terra ou Sol par abonnement Codex). 0 € dépensé. Réponses vérifiées à la main.

| Cas | DSH (s · outils · tokens entrée) | Unharnessed (s · cellules · tokens entrée) | Exactitude |
|---|---|---|---|
| fichiers | 18,9 · 2 · 10 898 | 9,3 · 1 · 5 537 | les deux justes |
| gros fichier (DECISIONS.md) | 27,9 · 2 · 17 248 | 14,6 · 1 · 5 483 | les deux justes (184 / 17-13-10 / 94) |
| mémoire (Sagora) | 39,8 · 4 · 18 687 | 7,5 · 0 · 5 754 | DSH a cherché et trouvé plus récent (11/11) ; Unharnessed s'est fié au pack (6/11) ; aucun n'a vu le 14-15/11 |
| web (walter_browse) | 20,4 · 2 · 12 648 | 22,9 · 3 · 18 082 | les deux justes (35 THB, même source) |
| code (slugify + tests uv) | 72,7 · 9 · 22 436 | 81,4 · 12 · 18 378 | les deux verts (21 et 14 tests, relancés à la main) |
| **total** | **179,7 s · 19 · 81 917** | **135,7 s · 17 · 53 234** | |

Lecture : le prompt minimal et le MCP hors contexte coûtent ~35 % de tokens d'entrée en moins ; le gain de temps vient
surtout des questions locales (une cellule au lieu de plusieurs outils). Le cas mémoire n'est pas une victoire : plus
rapide parce que moins vérifié. Sur le code, GPT 6.1 Sol n'a pas regroupé ses actions ; avec Opus 5.5 (poste `coding`,
essai isolé du même jour) la même tâche tenait en une cellule (24,7 s, 16 tests verts). Une seule passe : à confirmer
par répétitions avant toute conclusion.

Base de comparaison (vérifiée le 16/11) : le côté DSH est le profil `headless` du foyer de test, qui charge les mêmes
greffons moteur que la production (`intake`, `policy`, `budget`, `events` : `cordis.patch.yml` commun). Il n'a pas ce
que seul le profil `web` de `dsh-web` ajoute : l'Engine API, le préréglage « standard » (sous-agents, délégation,
élagage des résultats d'outils). Le moteur de production présente donc au moins autant d'outils au modèle.

Piste à mesurer : le noyau DSH contient déjà l'appel d'outils par programme (`dsh-ptc-runtime-node`, `preset-ptc`,
`workflow-ptc` : le modèle écrit un programme qui appelle les outils, dans un processus isolé). Walter les a désactivés
dans `profiles/web/cordis.patch.yml`. C'est l'idée d'Unharnessed, en TypeScript et sans état entre deux appels.

## Manques connus (avant toute intégration réelle)

- Journal : les sessions Unharnessed ne vont pas dans walter_logs (pas de connecteur pour leur format JSONL) ; pas
  d'événements bus `turn.ended`/`session.ended`, donc pas d'épisodes Walter Memory.
- Les instructions du serveur MCP `walter` (présentation des modules) ne sont pas injectées par Unharnessed ;
  le modèle découvre les outils par `mcp.list_tools`.
- Pas de politique d'exécution Walter (liste « jamais ») ni de budget de pas : seule la bulle protège.
- `run.routing.applied` reste `false` (seul DSH est observé côté transport).
