# Mesures de référence avant le moteur (lot E0)

| | |
|---|---|
| **Rôle** | Fixer l'état mesuré du système actuel pour juger chaque lot : un lot n'est adopté que s'il fait au moins aussi bien. |
| **Propriétaire** | walter-core. |
| **État** | Relevé le **09/11/2026 vers 09 h UTC** sur la VM. Chiffres agrégés seulement, aucun contenu personnel. |
| **Ne fait pas** | Ne remplace ni le banc de Lab ni les tests des modules ; ne mesure pas la qualité des réponses. |
| **Contrats** | Bancs existants : `context/bench/levels.py`, tests `pytest` de chaque module, schémas `walter_logs`, `runs`, `models.exec_log`, `system.model_calls`. |

Comment refaire ce relevé : les commandes sont listées à la fin du document (§ 8). Le relevé suivant se fait avant
le lot E1 puis à la fin de chaque lot, avec les mêmes requêtes.

## 1. Machine

| Mesure | Valeur | Remarque |
|---|---|---|
| Disque `/` | **135 Go utilisés sur 145, 9,5 Go libres (94 %)** | Contrainte n° 1 avant E1 : Docker 35 Go, `~/.hermes` 22 Go (dont `state.db` 5,3 Go, checkout Hermes 9,7 Go), `/user/Lucas` 19 Go, `/root/archive` 6,1 Go |
| Mémoire vive | 23,9 Go, 12,5 Go disponibles | — |
| Moteur actuel `dsh-web` | 209 Mo de mémoire résidente | Une seule instance, :3080 |
| Services Walter (résidents) | passerelle Memory 963 Mo, `walter-skills-bus` 897 Mo, pipeline Memory 883 Mo, `walter-skills` 725 Mo, Camoufox 647 Mo, preflight 436 Mo, passerelle Hermes 349 Mo, walter-llm 125 Mo | Trois processus Python de plus de 700 Mo : à surveiller pour le moteur |

## 2. Moteur actuel (DSH, web)

| Mesure (7 derniers jours) | Valeur |
|---|---|
| Messages de Monsieur | 330, dans 66 sessions |
| Runs ouverts par DSH | 114 terminés, 2 abandonnés, 1 annulé |
| Durée d'un tour (message → dernière réponse), mesurable sur 52 tours | médiane **5,3 s**, 90ᵉ centile **10,6 s** |
| Appels de modèle par tour | 3,3 en moyenne (387 appels pour 116 runs) |
| Coût par tour | 0,0042 $ en moyenne, **mais 2 572 appels sur 2 588 ont un coût inconnu** (routes par abonnement) : le coût réel par tour n'est pas mesurable aujourd'hui |

## 3. Préparation du contexte

Banc `levels.py` (29 cas de l'instance, politiques `legacy` = hook actuel et `pack` = walter-context) :

| Mesure | `legacy` | `pack` | Référence précédente (07/11) |
|---|---|---|---|
| Rappel (réponse attendue présente dans le contexte) | 16/18 | **16/18** | 17/18 |
| Niveau planifié juste | — | **20/29** | — |
| Capacités planifiées justes | — | 11/12 | — |
| Fuite de mémoire sur une question web | — | 0 | 0 |
| Jetons injectés L0–L1 | 16 307 | **5 205** | — |
| Jetons injectés au total | 50 633 | 55 586 | — |
| Latence de préparation | médiane 1,69 s | médiane **1,25 s**, 90ᵉ centile 2,72 s, max 3,32 s | — |

Le rappel a perdu un cas depuis le 07/11, et le preflight sous-estime le niveau dans 9 cas, dont 6 où L3 est
attendu mais L0 planifié. Ce sont des sujets de Context (continuité Context/Memory, priorité 2 de la vision), pas du
moteur. Le moteur doit seulement ne rien dégrader : même plan pour un même message (lot E2).

### 3 bis. Coût de l'accueil d'un tour (lot E2, relevé du 10/11)

| Mesure | Valeur |
|---|---|
| Crochet `UserPromptSubmit` sur les sessions DSH réelles depuis le 03/11 (journaux de session) | 63 tours : médiane **1,00 s**, 90ᵉ centile 2,5 s, max 5,5 s |
| Crochet `Stop` sur les mêmes sessions | 55 tours : médiane **0,77 s**, 90ᵉ centile 0,9 s |
| Banc `bench/e2_intake.py`, 15 tours par mode, mêmes messages en alternance | crochet : accueil médiane 2,16 s + `Stop` 0,80 s ; natif : accueil médiane **1,68 s**, fin de tour hors du tour ; durée totale médiane 10,4 s → **9,2 s** |

Les tours du banc demandent tous le pack complet (questions de mémoire, et une question d'heure servie sans modèle de
réponse), d'où un accueil plus long qu'en usage réel. Même texte, même plan dans les deux modes à l'échantillonnage
du modèle de décision près : c'est ce bruit que `bench/e2_shadow.py` sépare des écarts imputables à l'accueil.

## 4. Journal et bus

| Mesure (7 jours) | p50 | p95 |
|---|---|---|
| Délai d'arrivée dans walter_logs : Claude Code | 0,5 s | 6,4 s |
| Codex | 0,3 s | 0,4 s |
| DSH | 0,3 s | 0,6 s |
| Hermes | 0,3 s | **135,7 s** |

## 5. Sous-agents `walter_run`

| Mesure | Valeur |
|---|---|
| Tâches tracées dans le Run Plane | 23 (27–28/10), aucune depuis |
| Outils utilisés | `walter_browse` 173 appels, `skill_read` 8 ; **terminal et fichiers : 0** |
| Correction du 09/11 | Terminal retiré, fichiers confinés au dossier du run (router `64b1b48`) |

## 6. Appels de modèles hors moteur (7 jours)

| Source | Appels | Coût déclaré |
|---|---|---|
| Memory (tous traitements) | ~3 900 | 2,97 $ dont rerank 2,87 $ |
| Router `exec_log` texte | 2 562 | 0,70 $ (coûts majoritairement inconnus) |
| Hermes « Memory Dreaming » | 1 par nuit, en échec depuis le 19/10 | **mise en pause le 09/11** |

## 7. Tests des modules (avant toute modification du moteur)

| Module | Résultat | Remarque |
|---|---|---|
| router | 343 réussis, 4 ignorés | après la correction du terminal |
| core | 218 réussis (commande du README) + 18 tests MCP | les 18 tests MCP (`test_capabilities`, `test_toolset`) ne tournent avec **aucun** interpréteur seul : il faut les paquets du venv de core + pytest (prérequis E1) |
| context | 110 réussis | — |
| memory | 308 réussis, 1 ignoré | — |
| skills | 35 réussis (`tests/`) | `archive/docx` échoue à la collecte (dépendance absente, skill archivé) |
| ops | 31 réussis | — |
| secrets | 43 réussis | dépôt avec du travail non committé depuis le 25/10 (§ risques de 03-MIGRATION) |
| lab | 44 réussis | — |
| computer | 48 réussis | — |
| browse | **123 réussis, 5 en échec** | échecs antérieurs au 09/11 (repli statique, contrats du greffon Hermes, rejeu de l'extracteur) |
| soul | pas de tests | — |
| `walter check` | vert | contrôle documentaire en avertissement : 13 en-têtes de README incomplets, 2 README de module absents (colab, raw-vault) |

## 8. Refaire le relevé

- Banc de contexte : `walter-python bench/levels.py --json <fichier>` depuis le module context.
- Tests : la commande documentée de chaque module ; pour core, celle du README plus les deux fichiers MCP avec les
  paquets de son venv.
- Base : requêtes agrégées sur `walter_logs.events` (`ingested_at - occurred_at`), `runs.runs` (par
  `origin->>'runtime'`), `models.exec_log` (jointure par `run_id`) et `system.model_calls` (par `processor`), sur
  7 jours glissants.
- Machine : `df -h /`, `free -m`, mémoire résidente des unités par leur `MainPID`.
