# Computer Use V2 — Audit factuel du V1 CLOSED

Date de l'audit : 2026-08-13

## Périmètre immuable

- Release active auditée : `~/.hermes/releases/hermes-agent-lot11-20260813T074855Z`
- HEAD vérifié : `c00089cd6113bdc039abccd9c4fb21243a81904d`
- Tree vérifié : `cf12115dd9a2502065b59431d0a8245e96320228`
- État Git : propre, 0 ligne de status et 0 ligne de diff pendant l'audit.
- Plugin actif auditée : `~/.hermes/plugins/walter-computer-use`
- Hash tar déterministe observé avant le chantier V2 : `903c93ba7a1ed6b98d642be9c4426b40f1d1892f56b706aeaca55eb1ad5b1c3b`

Le chantier V2 vit exclusivement dans (ancien dossier de travail, retiré le 2026-11-09). Aucun fichier de la release ni du plugin V1 n'est importé, copié par référence mutable ou modifié.

## Carte V1 actuelle

```text
LLM
 └─ computer_use
     ├─ 23 actions core model-facing
     └─ action plugin `goal`
          └─ WalterComputerRouter (parse + recette bornée)
               └─ WalterCuaBackend
                    └─ CuaDriverBackend
                         └─ walter-cua-remote → SSH/Tailscale → cua-driver macOS

Device-operation plane séparé
 └─ walter-device-node
      ├─ policy de capabilities
      ├─ opérations idempotentes
      ├─ adaptateur OS déterministe
      ├─ vérification
      └─ audit HMAC / broker privilégié
```

## Surface model-facing réelle

Le schéma core expose 23 actions dans `tools/computer_use/schema.py:32-58` :

- observation/introspection : `capture`, `wait`, `list_apps`, `list_windows`, `cua_browser_state` ;
- input natif : clics, drag, scroll, type, key, set_value, focus_app ;
- page browser typée : prepare/navigate/click/type/pointer/dialog/files/download.

Le plugin ajoute `goal` via le seam d'extension dans `~/.hermes/plugins/walter-computer-use/__init__.py:894-924`. Son prompt force ce `goal` comme premier et unique appel model-facing (`:886-891`). Il n'ajoute pas un second tool, ce qui est une bonne propriété à conserver.

## Backend et primitives V1

`ComputerUseBackend` est un ABC orienté primitives (`tools/computer_use/backend.py:236-374`) :

- lifecycle `start/stop/is_available` ;
- `capture(mode, app, pid, window_id)` ;
- `click`, `drag`, `scroll`, `type_text`, `key` ;
- `list_apps`, `list_windows`, `focus_app`, `set_value` ;
- route browser typée optionnelle ;
- `wait`.

Le `CuaDriverBackend` possède aussi des capacités non exposées directement dans le schéma core : lancement natif, fermeture, bring-to-front, taille écran, zoom/crop, curseur, enregistrement. Par exemple `launch_app` retourne PID/bundle/windows et évite un round-trip de discovery (`tools/computer_use/cua_backend.py:3210-3241`). Ce sont des briques utilisables par un futur provider macOS, pas de nouvelles tools à publier.

## Observation et refs

Points solides :

- cible exacte possible par `(pid, window_id)` ;
- AX sans pixels avec `include_screenshot=false` (`cua_backend.py:2576-2589`) ;
- refs/tokens invalidés à chaque nouveau snapshot (`:2467-2469`, `:2654-2663`) ;
- route browser exacte, refs latest-snapshot et état frais obligatoire après mutation (`browser_route.py:7-14`, `:210-336`) ;
- résultats d'action sémantiques `confirmed`, `unverifiable`, `suspected_noop`, séparés du succès transport (`tool.py:870-916`).

Limites :

- `capture` a `som` comme défaut et sa description le présente comme meilleur chemin (`schema.py:68-78`) ;
- le schéma autorise jusqu'à 1000 éléments AX (`:109-129`) ;
- la compaction actuelle du plugin est une projection spécialisée et non un contrat universel ;
- l'observation n'est pas encore un objet versionné indépendant de la réponse backend.

## Vision V1

`vision_routing.py:5-45` choisit entre pixels envoyés au modèle principal et description par modèle auxiliaire. Le fallback auxiliaire coûte un appel LLM supplémentaire et renvoie du texte descriptif. Il résout la compatibilité multimodale, mais ce n'est pas le fast locator V2 demandé.

Le backend sait déjà produire un screenshot sans AX sur les drivers anciens et, sur les drivers récents, jeter l'AX après `get_window_state` (`cua_backend.py:2490-2545`). Il possède aussi `zoom` pour un crop natif (`:3308-3320`). Ce sont les bons points d'ancrage du fast-path vision.

## Approval et interruption V1

Mesure mécanique du schéma core :

- 5 actions classées safe : capture, list_apps, list_windows, wait, cua_browser_state ;
- 18 actions classées destructives/mutantes ;
- aucune action non classée.

Le gate se trouve avant dispatch (`tool.py:531-563`) et le focus persistant est approuvé séparément (`:539-547`). Limite importante relevée par la revue indépendante : lorsque `_approval_callback is None`, `_request_approval` autorise localement (`tool.py:602-606`) en supposant que le gateway externe porte l'approbation. Le chemin déployé peut donc être protégé par le gateway, mais le tool seul n'est pas intrinsèquement fail-closed hors hôte câblé. V2 ne doit pas reproduire cette hypothèse : un gate absent au point de dispatch doit refuser. Par ailleurs, V1 ne représente pas L0/L1/L2 selon les effets ; une action L1 n'a pas de preuve runtime de warning.

## Goal router V1 : dette explicitement non migrée

Le plugin V1 contient une recette volontairement bornée :

- six apps connues dans `known_apps` (`__init__.py:53-68`) ;
- traduction implicite YouTube → URL (`:75-83`) ;
- détection `first video` et sélection AX spécialisée (`:169+`) ;
- absence d'app → `unsupported_goal` (`:224-228`) ;
- lancement natif → capture AX → clic ;
- retry local caché élément → pixel dans une condition précise (`:780-840`).

Cette logique reste valide pour le V1 CLOSED. Elle n'est ni copiée ni généralisée dans V2.

## Device Node existant

Le Device Node séparé apporte déjà des patterns durables réutilisables :

- `OperationRequest` bornée, canonical JSON, idempotency (`src/walter_device_node/contracts.py:147-232`) ;
- résultats séparant transport, completion, effect et verified (`:118-145`) ;
- capability policy fail-closed par plateforme (`policy.py:23-86`) ;
- macOS live et Windows/Android contract-only pour certaines capabilities (`:89-141`) ;
- lifecycle persistant et vérification après exécution (`node.py:176-320`).

Il reste un **device-operation plane**, pas le cerveau du Universal Operator. V2 peut adopter ses contrats d'idempotence/audit sans lui déléguer le raisonnement ou le browsing.

## Décision de migration

| V1 | Décision V2 |
|---|---|
| une porte `computer_use` | conserver |
| backend/plugin seams | adapter, ne pas casser |
| semantic action verdicts | conserver et normaliser |
| exact targets + fresh refs | conserver comme invariant |
| native launch, AX, crop | publier comme offers internes |
| Device Node durable | réutiliser comme provider ciblé |
| 23 actions permanentes | masquer derrière 3 opérations V2 |
| `goal` recipe router | ne pas migrer |
| `unsupported_goal` | remplacer par observe/needs_reasoning |
| ladder/retry local caché | remplacer par offers + adaptation LLM |
| capture SOM par défaut | remplacer par observation minimale |
| vision descriptive générale | remplacer par locator borné et benchmarké |
| approval binaire | remplacer/compléter par gate d'effets L0/L1/L2 |
