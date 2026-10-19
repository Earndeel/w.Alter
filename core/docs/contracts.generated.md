# Contrats des modules Walter

Généré depuis les manifestes propriétaires. Les scénarios décrivent les critères ; leur réussite est mesurée séparément.

| Module | Niveau | Responsabilité | Dépendances obligatoires |
|---|---|---|---|
| browse | capability | Rechercher, extraire et gérer les parcours web avec un moteur commun. | — |
| bus | foundation | Livrer les événements entre modules et conserver les curseurs de traitement. | memory |
| colab | capability | Préparer et exécuter des travaux de calcul distant qualifiés. | — |
| computer | capability | Observer et manipuler un appareil avec des permissions et cibles explicites. | — |
| context | capability | Construire le contexte et les checkpoints selon le contrat de chaque harness. | — |
| core | foundation | Exposer les capacités et installer les raccordements des harnesses. | — |
| llm | capability | Exécuter les appels modèles des consommateurs autorisés via les postes du Router. | router, secrets |
| logs | foundation | Conserver les traces accessibles de tous les harnesses dans un journal commun. | memory |
| memory | capability | Posséder les événements et objets canoniques, leur provenance et les connaissances dérivées. | — |
| raw-vault | capability | Conserver les octets originaux et les relier au catalogue canonique. | memory |
| router | capability | Choisir les modèles par poste avec décisions et coûts traçables. | — |
| runtime | foundation | Fournir l’environnement Python partagé des modules Walter. | — |
| secrets | capability | Gérer les références au coffre et injecter localement les valeurs autorisées. | — |
| skills | capability | Gérer le contenu, la recherche, les propositions et la curation des procédures. | bus |
| soul | foundation | Rendre l'identité de l'instance active pour chaque runtime ; livrer l'identité et les règles par défaut d'une nouvelle instance. | — |

## browse

Rechercher, extraire et gérer les parcours web avec un moteur commun.

Contrat 1.0.0; propriétaire : browse.
Racine actuelle : `/walter/browse`. Cible : `/walter/browse`.

Interfaces : shared request contract, CLI, MCP, Hermes plugin.

**Critères de validation :**

- Une extraction publique passe par le noyau partagé sans processus agent Hermes. (live)
- Une session gérée permet un parcours autorisé sans divulguer ses identifiants. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Authenticated HTTP uses managed server-side cookies and refuses cross-origin redirects or anonymous fallback.
- Authenticated interactive browser routes are not qualified by the HTTP fixture.

## bus

Livrer les événements entre modules et conserver les curseurs de traitement.

Contrat 1.0.0; propriétaire : bus.
Racine actuelle : `/opt/walter-memory`. Cible : `/walter/memory`.

Interfaces : Python emit/Consumer, Postgres LISTEN/NOTIFY.

**Critères de validation :**

- Un consommateur arrêté reprend depuis son curseur sans perdre les événements persistés. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## colab

Préparer et exécuter des travaux de calcul distant qualifiés.

Contrat 1.0.0; propriétaire : colab.
Racine actuelle : `/walter/colab`. Cible : `/walter/colab`.

Interfaces : on_demand.py CLI.

**Critères de validation :**

- Une charge non qualifiée est refusée avant toute allocation de calcul. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- GPU remains blocked until prepared artifact validation; modularity work does not remove this guard.
- No remote compute is allocated by modularity checks.

## computer

Observer et manipuler un appareil avec des permissions et cibles explicites.

Contrat 1.0.0; propriétaire : computer.
Racine actuelle : `/walter/computer`. Cible : `/walter/computer`.

Interfaces : OperatorSessions, MCP computer_use, Hermes plugin.

**Critères de validation :**

- Une tâche synthétique sur le Mac réussit sans accéder aux applications personnelles. (live)
- Les cibles périmées et les accès concurrents non autorisés sont refusés. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- No desktop input in health checks.
- Read, pixels, vision and input require explicit grants.
- Cloud vision additionally requires host-only authorization for one exact window; default denied.
- Workflow reservations are cross-process leases with bounded expiry; live Mac qualification tracked separately.

## context

Construire le contexte et les checkpoints selon le contrat de chaque harness.

Contrat 1.0.0; propriétaire : context.
Racine actuelle : `/opt/walter-context`. Cible : `/walter/context`.

Interfaces : Python Session, Hermes ContextEngine adapter, DSH CompactionEngine adapter.

**Critères de validation :**

- Les contraintes, instructions, références et budgets survivent aux checkpoints répétés ou l’opération est refusée. (integration)
- Un corpus fixé à l’avance respecte les seuils de qualité, coût et rétention visible. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- DSH uses public compaction transactions; checkpoints retain all visible user and assistant dialogue or refuse.
- Hermes remains on walter-compress; walter-context projection is not activated.
- Structural and known-answer tests do not certify semantic model quality.

## core

Exposer les capacités et installer les raccordements des harnesses.

Contrat 1.0.0; propriétaire : core.
Racine actuelle : `/opt/walter-core`. Cible : `/walter/core`.

Interfaces : MCP stdio, walter CLI, CLI contracts, matrix, doctor, Declarative harness compositions, Offline source release and staged installation.

**Critères de validation :**

- Un module optionnel absent ne désactive pas les capacités restantes. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- MCP client must reconnect to discover newly installed tools.
- CLI attachment installs common MCP; context/model/lifecycle bindings are checked independently.

## llm

Exécuter les appels modèles des consommateurs autorisés via les postes du Router.

Contrat 1.0.0; propriétaire : llm.
Racine actuelle : `/walter/router/llm`. Cible : `/walter/router/llm`.

Interfaces : OpenAI-compatible :8894.

**Critères de validation :**

- Un jeton absent ou invalide est refusé et un poste choisi utilise la route attendue. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## logs

Conserver les traces accessibles de tous les harnesses dans un journal commun.

Contrat 1.0.0; propriétaire : logs.
Racine actuelle : `/opt/walter-memory`. Cible : `/walter/memory`.

Interfaces : Writer, CLI, MCP.

**Critères de validation :**

- Les sources principales et profils sont collectés avec reprise idempotente après interruption. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Only traces made available by the harness can be archived; hidden reasoning cannot be reconstructed.

## memory

Posséder les événements et objets canoniques, leur provenance et les connaissances dérivées.

Contrat 1.0.0; propriétaire : memory.
Racine actuelle : `/opt/walter-memory`. Cible : `/walter/memory`.

Interfaces : Python library, HTTP :8890, CLI, MCP.

**Critères de validation :**

- Les lectures refusent les sources privées, purgées ou rétractées et les fragments périmés. (integration)
- Les décisions datées et remplacées ne sont pas présentées comme des instructions actuelles. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Canonical reads exclude stale, retracted, private and unprovenanced legacy cognitive rows.
- Wild profile reads are refused by the cloud-safe port; local-only history remains local.
- Existing desktop provider instances change on next session initialization; not force-restarted.

## raw-vault

Conserver les octets originaux et les relier au catalogue canonique.

Contrat 1.0.0; propriétaire : raw-vault.
Racine actuelle : `/opt/walter-raw-vault`. Cible : `/walter/memory/vault`.

Interfaces : memory objects library, S3, MCP.

**Critères de validation :**

- Un objet synthétique est écrit, catalogué et relu avec son empreinte et sa confidentialité. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## router

Choisir les modèles par poste avec décisions et coûts traçables.

Contrat 1.0.0; propriétaire : router.
Racine actuelle : `/walter/router`. Cible : `/walter/router`.

Interfaces : CLI, walter-llm task routes, MCP route lookup.

**Critères de validation :**

- Un poste renvoie le choix actif et un poste inconnu échoue explicitement sans sélection arbitraire. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Codex subscription catalog and quota collection retain optional Hermes subprocess adapters.
- New model choices remain subject to the owner's approval; no automatic switching introduced.

## runtime

Fournir l’environnement Python partagé des modules Walter.

Contrat 1.0.0; propriétaire : runtime.
Racine actuelle : `/walter/runtime`. Cible : `/walter/runtime`.

Interfaces : command walter-python.

**Critères de validation :**

- walter-python importe les dépendances déclarées dans le lock (unit)
- aucun module n’appelle l’interpréteur d’un autre module (integration)

**Limites déclarées :**

- The venv is rebuilt from the lock, not exported; a dependency upgrade affects every consumer at once.

## secrets

Gérer les références au coffre et injecter localement les valeurs autorisées.

Contrat 1.0.0; propriétaire : secrets.
Racine actuelle : `/walter/secrets`. Cible : `/walter/secrets`.

Interfaces : safe MCP metadata/reference, local CLI exec/get, Hermes hooks, walter-secret grants / grant access, walter_secrets.grants.

**Critères de validation :**

- Références, erreurs et sorties des processus ne divulguent pas les valeurs du coffre. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Hermes browser-field fill is a host-specific adapter.
- MCP never returns raw secret values; CLI exec suppresses child output.

## skills

Gérer le contenu, la recherche, les propositions et la curation des procédures.

Contrat 1.0.0; propriétaire : skills.
Racine actuelle : `/opt/walter-skills`. Cible : `/walter/skills`.

Interfaces : HTTP :8891, stdlib client, MCP, Hermes plugin.

**Critères de validation :**

- Une procédure publiée est retrouvée depuis deux harnesses et une proposition reste en brouillon. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## soul

Rendre l'identité de l'instance active pour chaque runtime ; livrer l'identité et les règles par défaut d'une nouvelle instance.

Contrat 1.0.0; propriétaire : soul.
Racine actuelle : `/walter/soul`. Cible : `/walter/soul`.

Interfaces : renderer, walter-soul render/path/sync/check/init, walter_profile MCP.

**Critères de validation :**

- Une modification des sources produit des profils cohérents et détecte les retouches manuelles. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Limites déclarées :**

- An instance may keep historical target locations (harness homes, profile workspaces) through its targets override.
