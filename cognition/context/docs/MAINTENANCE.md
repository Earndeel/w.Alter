# Maintenance de walter-context

Référence d’exploitation du module, mise à jour le 29 octobre 2026.
[Vue d’ensemble](../README.md) · [Contrat](../contracts/context.json) · [Corpus de rétention](ACCEPTANCE.md).
Ce document décrit le code et les raccordements ; un test structurel ne vaut pas une qualification de qualité.

## Responsabilités et données

Context choisit et ordonne le contexte à transmettre au modèle. `compress` projette ou réduit l’historique selon
le contrat du host. `preflight` produit un plan, `retrieval` récupère ses sources, `assembly` compose les blocs et
`child` prépare le contexte d’une tâche déléguée. Router choisit les modèles concrets. Memory/Logs possèdent
sujets, vues, observations, runs et journaux ; Skills possède les procédures.

Les epochs de projection et caches en mémoire sont éphémères. Le fichier de configuration logiciel est
`config/walter-context.toml` (surcharge `WALTER_CONTEXT_CONFIG`). Des budgets locaux de retrieval/child restent
dans leurs modules Python. Les sélections d’activation et observations appartiennent à l’instance :
`@instance/config/context/inject.json`, `@instance/state/context/modules.md` et
`@instance/state/context/shadow/preflight-*.jsonl`. Ces derniers peuvent contenir des textes privés ; ne pas les
publier dans le dépôt. Context peut mettre à jour niveau/acte/sujet du run via la commande publique Memory ; il
n’écrit pas directement les notebooks ni les sources canoniques.

## Interfaces et dépendances

| Interface | Dépendance et données | Comportement en indisponibilité |
|---|---|---|
| Python `Session`, checkpoint et bridge JSON v1 | Bibliothèque standard et configuration locale | Configuration invalide : erreur ; pas de nouvelle politique implicite |
| `walter-context recover` | API publique Memory Logs et sa politique de confidentialité | Original absent, non autorisé ou source inaccessible : récupération indisponible ; aucun original inventé |
| Notes `router`, `TurnNotes` | `walter-router brief --json` | Note non disponible/invalide : pas d’injection autorisée |
| Notes `all`, `TurnLayer`, retrieval des capacités | `walter present` de Core | Notes absentes ou invalides ignorées ; retrieval conserve une note d’échec du bloc |
| Preflight et retrieval | API Memory : vues, contexte, registres, Logs ; décision via `walter_memory.llm` et CLI Router | Candidats absents : plan sur la conversation ; modèle indisponible : plan local L1 ; source en panne : bloc omis et note |
| CLI `walter-context-child` | Client public Skills ; API Memory runs/vues/observations/contexte ; présentations Core | Une source optionnelle en échec ne supprime pas les autres blocs ; mission/contexte de l’appelant restent construits |
| CLI `walter-context-entrance` (hook PostToolUse de Claude Code) | Aucune pour le fantôme ; `walter instance path` pour l’enregistrement | Instance introuvable : rien n’est enregistré ; toute erreur est muette côté agent (le hook est détaché) ; `WALTER_HOOK_ENTRANCE=off` ou `[entrance].mode = "off"` désactive |
| Publication `capability all --write` | Core pour le chemin d’instance ; `walter-soul sync` pour le rendu | Échec de publication explicite ; pas de garantie de rechargement des hosts |

`requires` reste vide : la compression locale fonctionne sans ces services. Core, Logs, Memory, Router, Skills et
Soul sont des dépendances **optionnelles au niveau du module**, nécessaires aux fonctions indiquées. Le client
Skills et la bibliothèque Memory sont importés à la demande ; cela ne les rend pas indépendants de leurs services
pour les opérations qui les consultent. Les modèles sont atteints par Memory/Router ; Context ne possède aucun
modèle concret ni clé fournisseur.

Le preflight propose des capacités et un niveau ; il ne retire pas les outils du modèle orchestrateur. Stabilité
(09/11) : la décision est la moyenne de `DECISION_SAMPLES` = 3 appels parallèles au même modèle
(`walter_memory.llm.decide(samples=…)`, `merge_answers` : moyenne des probabilités, confiance pondérée par l'accord),
car l'API de décision échantillonne : sur les mêmes entrées, un appel unique faisait basculer la capacité mémoire
(0,37–0,55 sur un message). Cohérence : capacité `memory` (modèle ≥ 0,5 ou nom connu de Memory) ⇒ niveau au moins
L3. Mesures et coût dans `/walter/docs/CONTEXT-ENGINE.md` (étape B). Un message
`local_only` n’est pas envoyé au modèle de décision et ne reçoit pas de pack cloud assemblé. Les lectures Memory
appliquent leur politique propre ; la projection locale et le bridge n’effectuent pas implicitement de décision
cloud. Une erreur d’une source ne constitue pas une preuve que les données correspondantes n’existent pas.

## Activation et service

- DSH : configuration observée avec le port Context sélectionné. Le chargement effectif d’une révision exige un
  lancement et une trace ; le contrôle de configuration seul ne le démontre pas.
- Hermes : adaptateur Context disponible, compresseur natif sélectionné dans la configuration observée. Aucun
  remplacement automatique de ce compresseur.
- Codex/Claude Code : compaction native ; le hook et les notes apportent du contexte supplémentaire.
- Preflight par message : le service local reçoit `POST /preflight`, `?shadow=1` enregistre seulement et
  `?inject=1` retourne le pack. `WALTER_HOOK_PREFLIGHT=off` désactive le travail fantôme côté hook ; le hook
  distingue ce mode de la sélection d’injection DSH.
- Injection DSH : `WALTER_HOOK_INJECT_DSH=legacy|pack` a priorité sur l’interrupteur d’instance ; à défaut, `legacy`.
  Aucun fichier d’interrupteur n’était présent lors de la vérification du 29 octobre. Une expérience peut modifier
  son environnement sans modifier l’instance. Si le pack échoue, le hook conserve le comportement mémoire précédent.
- Sous-agents Router : `WALTER_RUN_CONTEXT=caller` demande uniquement le contexte de l’appelant. Sinon Router
  appelle `walter-context-child` ; s’il est indisponible, Router conserve le contexte de l’appelant.

Commandes de contrôle, depuis le module obtenu par `walter path context` :

```sh
walter harness check dsh
walter harness check hermes
systemctl is-active walter-context-preflight
walter-context-preflight --report --days 1
```

Le service est déclaré dans `ops/walter-context-preflight.service`, superviseur `guardian/check`, protocole de
maintenance dans `contracts/maintenance.json`. `GET http://127.0.0.1:8897/health` confirme uniquement que le
service répond, pas la qualité ni la disponibilité de toutes les sources. Le port est local et de confiance ; ne
pas l’exposer publiquement. `WALTER_CONTEXT_PREFLIGHT_PORT` peut changer son port ; vérifier aussi les consommateurs.
Le redémarrage du service ne recharge pas à lui seul un adaptateur déjà chargé dans un autre host.

Le contrôle systemd n’était pas accessible depuis l’environnement restreint de cette révision documentaire ;
aucune affirmation nouvelle d’état actif du service n’en est déduite.

## Validation et limites

Les tests `test_preflight.py`, `test_retrieval_assembly.py`, `test_records_calibration.py`, `test_child.py` et
`test_plan.py` couvrent décisions simulées, panne d’une source, ordre et sélection des blocs, conservation du
contexte de l’appelant et schémas. Ils ne nécessitent pas un modèle ni une base de production.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" walter-python -m pytest -q -p no:cacheprovider \
 tests/test_plan.py tests/test_preflight.py tests/test_retrieval_assembly.py \
 tests/test_records_calibration.py tests/test_child.py
walter-context acceptance
node tests/test_dsh.mjs
```

Les deux dernières commandes vérifient respectivement la rétention synthétique et le port DSH installé ; elles
ne remplacent pas une mesure sur un parcours réel. Les résultats historiques et leur corpus sont dans
`ACCEPTANCE.md`. Les commandes de replay d’historiques privés et les évaluations avec modèle ne sont pas des
tests hors réseau. Préserver corpus, version des sources, scope et date avec toute nouvelle mesure ; comparer
qualité, durée et coût avant une décision d’activation. Aucun SLO général ni gain universel n’est revendiqué.

## Compatibilité et retrait

Le bridge de compression et ChildContextSpec portent chacun leur version 1 ; ContextPlan a son schéma versionné.
Vérifier les consommateurs avant de changer un format. DSH conserve le journal et les transactions de compaction,
Hermes son API publique ContextEngine, Codex/Claude leur compaction native. Les notes de capacités exigent
l’inventaire d’outils du host ; pas de note injectée par simple présence d’un répertoire.

Avant une modification, sauvegarder source, configuration et état d’instance concernés avec le mécanisme Backup
existant. Pour revenir en arrière : restaurer la version et les paramètres compatibles, redémarrer seulement le
service concerné et relancer les hosts qui chargent son adaptateur. Pour retirer Context : désactiver séparément
le pack par message, le preflight fantôme, le port de compaction et l’appel child dans leurs consommateurs ;
restaurer la composition native du host avant de retirer les commandes. Arrêter le service seul ne retire pas la
bibliothèque de compression ni les notes déjà chargées. Conserver les journaux et rapports dans l’instance selon
leur politique ; ne pas effacer les données Memory/Logs que Context consomme.

Les anciens chemins de compatibilité relèvent du résolveur `walter path` et du catalogue de Core. Aucun nouveau
chemin propriétaire n’est ajouté ici. Leur suppression exige d’abord l’inventaire des consommateurs et un test de
retour arrière ; ce document ne crée pas de second registre ou de mécanisme de migration.
