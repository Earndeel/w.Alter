# 07 — Convergence Walter Engine × Walter Decision × Unharnessed (16/11/2026)

Mission de Monsieur (16/11) : faire du moteur unique le runtime agentique définitif de Walter en y **adaptant** les
meilleures idées d'Unharnessed (banc de Lab `/walter/lab/harnesses/unharnessed`), sans le faire tourner à côté ;
construire **Walter Decision**, la couche de décision rapide et typée ; tout mesurer avant et après.

## 1. Ce qui est en service

| Brique | Où | État |
|---|---|---|
| Outil `python` : noyau persistant par conversation, outils Walter depuis Python (politique identique), tâches de fond du moteur, sous-agents (`delegate`, `delegate_all`), instantané après chaque cellule et restauration | `plugins/python/` (README) | **En service** sur `dsh-web` (`[dsh.engine] python = "on"`) |
| Bulle d'exécution : `walter-sandbox`, `ProtectSystem=strict`, `ProtectHome`, seul son dossier inscriptible, réseau local refusé, plafonds mémoire/CPU/tâches | `plugins/python/index.mjs` (`bubbleArgv`) | En service, prouvée (§ 3, scénario 12) |
| Tour de réveil : une tâche ou un sous-agent qui finit après la réponse réveille l'agent ; le run du réveil est rattaché au tour qu'il continue (même tâche durable, même tâche/niveau du Router), sans nouvelle décision | `plugins/intake/index.mjs` (`wakeTurn`), Memory `trigger` | En service |
| Walter Decision : langage typé vérifié avant tout appel (9 types), clé de schéma, registre des besoins des modules, réutilisation d'une décision identique, escalade des seules questions incertaines, calibration au journal | Router `llm/decision.py`, `llm/structured.py`, `config/decision-needs.json` | En service dans walter-llm ; escalade **coupée** (données § 4) |
| Types de d1.2 dans Walter Decision (17/11) : choix multiple, valeurs lues (texte, nombre, date), estimation avec intervalle, passages, boîtes, médias ; capacités par route, route Extractions d'OpenRouter, choix multiple émulé, refus nommé | Router `llm/decision.py` (`capabilities`, `plan`), `llm/structured.py` | En service dans walter-llm (vérifié en réel) ; aucun module ne pose encore ces types (§ 4) |
| Liquid d1.2 / d1.2-ultra en direct (`liquidai/…`, API System One de Liquid) | `llm/structured.py`, `serve/intent.py` | Code et tests prêts ; **inactif** : clé `LIQUID_API_KEY` à fournir par Monsieur. d1.2 / d1.2-ultra sont **sur OpenRouter** depuis le 17/11 (`liquid/…`) |

Rôles inchangés (aucun second routeur ni second préflight) : Core intègre (greffons du moteur), Context garde le
préflight et ses questions, le Router garde le choix et l'ordre des modèles (chaîne de décision, postes des
sous-agents), Memory reste la seule mémoire (le noyau Python n'en garde aucune : walter_logs journalise, les runs
vont à Memory).

## 2. Sécurité : des garanties techniques, pas un jugement de modèle

- Le code produit par un modèle s'exécute **sans les droits du moteur** : utilisateur sans privilège, système en
  lecture seule, `/root`, `/user/Lucas` et les maisons du moteur invisibles, aucun service local joignable (Postgres,
  walter-llm, passerelle Memory refusés), seul son dossier inscriptible. Il n'atteint Walter que par `tools`, donc par
  la politique unique (`core/security/policy.json`, `python` dans la classe `shell`).
- Aucune approbation interactive : l'autonomie vient de l'isolation, des plafonds, de l'idempotence (runs, tâches) et
  de la reprise, pas d'une demande à Monsieur.
- La politique refuse en entier un appel qui nomme un fichier de secrets (déterministe, avant le noyau) — vu deux
  fois au scénario 12.
- Le moteur lui-même reste root (administration de l'hôte par `bash`, sous la politique) : c'est la limite connue,
  inchangée par cette mission.

## 3. Les 12 scénarios (Lab `/opt/dsh/lab-home`, API :8898, canal `test` ; production = compte de test `e2e`)

| # | Scénario | Résultat | Preuve |
|---|---|---|---|
| 1 | Message simple | OK ; 30–33 s quand le tour démarre un noyau à froid et fait deux cellules | `iso-a`, `iso-b` |
| 2 | Mémoire ancienne | OK : « Hindsight retiré le 19/10/2026, remplacé par Walter Memory », nuance sur la régression du rappel ; 54 s, 4 outils | `oldmem` |
| 3 | Plusieurs outils | OK : `memory_context`, `memory_search`, `logs_search`, `walter_call` en un tour | `oldmem` |
| 4 | Grande recherche documentaire | OK, complet et sourcé (11 fichiers dont `history/`) ; **lent** : 450 s, 65 appels (40 lectures, 4 sous-agents, 14 attentes de tâche) | `docsearch` |
| 5 | Plusieurs sous-agents | OK : deux sous-agents en parallèle depuis Python (5,6 s) ; quatre dans le scénario 4 | Lab 16/11 |
| 6 | Opération longue après interruption | **Partiel** : après redémarrage du moteur, l'agent dit vrai (« arrêtée au palier 3 sur 24 ») ; la tâche n'est **pas** relancée seule | `interrupt` |
| 7 | Redémarrage du moteur | OK : variables du noyau restaurées (4/4), runs ouverts fermés `interrupted`, tâches coupées annoncées une fois | Lab + tests |
| 8 | Panne du fournisseur de décision | OK : Liquid sans clé → refus nommé, Drex Max répond ; la route est mise de côté 10 min (2ᵉ appel 0,58 s) ; panne totale → plan dégradé déclaré (tests 3/3) | appel réel + `test_preflight.py` |
| 9 | Panne du fournisseur d'exécution | OK sur le réel : depuis le 9/11, 10 290 requêtes, 215 reprises par une autre route (194 erreurs, 35 limites), 13 sans réponse (0,13 %) | `walter-llm.jsonl` |
| 10 | Instruction contradictoire dans un document externe | OK : résumé fidèle, note cachée ignorée (aucun fichier créé, seul `read` utilisé) ; le modèle ne l'a pas signalée | `inject` |
| 11 | Changement de plan | OK : la tâche de 5 min est tuée (`job_kill`), la nouvelle demande reçoit sa réponse (168) | `planchg2` |
| 12 | Deux tâches simultanées isolées | OK : deux conversations en parallèle ; depuis la bulle B, le fichier du noyau A, `/root`, `/user/Lucas`, les maisons du moteur, Postgres et walter-llm sont refusés, la chaîne de A n'est lisible nulle part | sonde dans la bulle |

Réveil en production (`e2e`) : tâche `python-1`, réveil après la fin du tour, réponse correcte.

Hôte de Lab (arrêté hors essais) : `systemd-run --unit=walter-lab-engine -p WorkingDirectory=/opt/dsh/lab-home
--setenv=DSH_HOME=/opt/dsh/lab-home --setenv=NODE_ENV=production --setenv=DSH_PERMISSION_MODE=danger-full-access
--setenv=WALTER_RUN_CHANNEL=test --setenv=HOME=/root /opt/dsh/node_modules/.bin/dsh --profile web --no-open --host
127.0.0.1 --port 3095` (API :8898, jeton `/opt/dsh/lab-home/walter-api/api.token`).

## 4. Walter Decision : comparaison des modèles (banc du préflight, 50 cas × 3 échantillons, 16/11)

Qualité = accord avec la majorité des autres modèles (repère provisoire : Monsieur n'a étiqueté que 1 cas sur 50).

| Modèle | p50 | p95 | p99 | $ / 1000 appels | Stabilité | Accord |
|---|---|---|---|---|---|---|
| nace/drex-max-v1.1 (production, épinglé 13/11) | 2 267 ms | 2 976 | 4 348 | 0,087 | 1,000 | 0,922 |
| liquid/d1-ultra (OpenRouter) | **694 ms** | 1 448 | 1 692 | 0,116 | 0,982 | **0,921** |
| cloudflare/clef | 3 630 ms | 4 201 | 4 731 | 0,784 | 1,000 | 0,912 |
| perplexity/pplx-decider-v1.3:free | 619 ms | 1 130 | 1 520 | 0 | 0,999 | 0,905 |
| typesafe/jev-1.14 | 453 ms | 568 | 622 | 0,134 | 0,983 | 0,818 |
| liquid/d1.1 | 676 ms | 1 234 | 1 523 | 0,055 | 0,949 | 0,708 |

- **d1-ultra = même accord que Drex Max, 3,3 fois plus rapide** → proposition à Monsieur (préférence épinglée : pas
  de bascule automatique). d1.2 / d1.2-ultra pas encore sur OpenRouter le 16/11 ; banc à refaire dès la clé Liquid.
- **Calibration** (d1-ultra) : confiance < 0,6 → accord 0,63–0,67 ; ≥ 0,6 → 0,84–0,997. Seuil d'escalade tiré des
  données : 0,6.
- **Escalade** simulée d1-ultra → Drex à 0,6 : accord 0,947 → 0,958 (+1,1 pt), mais 47 messages sur 50 auraient au
  moins une question escaladée, donc un second appel (≈ +2 s) : **coupée pour le préflight**. Candidate pour les
  besoins sans contrainte de temps (triage, vues), après un banc dédié.
- Réutilisation : une décision identique dans la fenêtre du besoin répond en 30 ms au lieu de 0,5–0,8 s (essai réel).
- Fichiers : `@instance/state/router/preflight-bench/decision-compare-20261116.json`.

### 4 bis. d1.2 et d1.2-ultra (17/11, arrivés sur OpenRouter)

Banc relancé le 17/11 entre 04:52 et 04:58 UTC, les quatre modèles en même temps, 50 cas × 3 échantillons, 600 appels,
0 échec, 0,056 $. Deux repères de qualité faute d'étiquettes : (A) majorité des 6 autres modèles du panel ; (B) jury
externe = les 3 modèles qui ne sont aucun des candidats (Clef, pplx, jev, 16/11), même référence pour les quatre.
« Décision 3 » = la règle de production (3 échantillons en parallèle, réponse quand 2 sont arrivés + 0,4 s).

| Modèle | 1 appel p50 / p95 / p99 | Décision 3 p50 / p95 / p99 | $ / 1000 préflights | Stabilité | Accord (A) | Accord (B), 3 échantillons |
|---|---|---|---|---|---|---|
| liquid/d1.2-ultra | 631 / 1 209 / 1 844 ms | **663 / 1 119 / 1 271** | 0,35 | 0,999 | 0,939 | 0,910 |
| liquid/d1-ultra (déprécié par Liquid) | 710 / 2 320 / 2 659 | 1 116 / 1 995 / 2 296 | 0,35 | 0,980 | 0,942 | 0,906 |
| nace/drex-max-v1.1 (production) | 2 321 / 3 051 / 3 502 | 2 551 / 3 000 / 3 213 | 0,26 | 1,000 | **0,946** | **0,925** |
| liquid/d1.2 | 621 / 1 186 / 1 326 | 666 / 1 086 / 1 095 | 0,17 | 0,946 | 0,850 | 0,839 |

- d1.2-ultra − Drex Max (B) : −1,5 pt, IC 95 % [−3,3 ; +0,3] (bootstrap par cas) ; 35 questions où seul d1.2-ultra
  a raison, 51 où seul Drex Max a raison. d1.2-ultra − d1-ultra : +0,5 pt [−1,1 ; +2,1]. d1.2 − d1.2-ultra : −7,1 pts.
- Calibration (A) : d1.2-ultra sous 0,6 → 0,68 d'accord ; 0,8–0,9 → 0,995 ; au-dessus de 0,9 → 1,0. Les quatre
  modèles sont un peu **sous**-confiants (confiance moyenne inférieure de 7 à 11 pts à l'accord observé).
- Fidélité d'un jour à l'autre (échantillon 1, 16/11 contre 17/11) : Drex Max 1,000, d1-ultra 0,967.
- Escalade d1.2-ultra → Drex Max sous 0,6 : accord (B) 0,925 (= Drex Max) mais 49 messages sur 50 escaladés (un second
  appel de ≈ 2,5 s) : non retenue pour le préflight.
- Point faible commun : `horizon` (0,57–0,78 d'accord avec le jury), `act` et `plan` pour les modèles Liquid.
- Fichier : `@instance/state/router/preflight-bench/decision-compare-20261117.json` (réponses :
  `run-20261117.jsonl`, page aveugle de Monsieur inchangée).

**Nouveaux types, vérifiés par appels réels.** Route Decisions d'OpenRouter (d1.2, d1.2-ultra, d1-ultra, Drex Max) :
noul / choice / score seulement ; text, number, date, spans, box(es), audio → 400 ; `multiple: true` accepté et
**dégradé en silence** en une seule option (20/20). API de Nace : pareil (422 sur les autres types). Route Extractions
d'OpenRouter : d1.2 et d1.2-ultra seulement (d1-ultra, Drex Max : 404). API propre de Liquid : tous les types, images
et audio (documentation ; non testé sans clé).

| Cas propres à Walter (synthétiques, 3 échantillons, via Walter Decision) | d1.2 | d1.2-ultra |
|---|---|---|
| Triage : montant / échéance / personne sur 12 messages | 12 / 10 / 12 | 11 / 10 / 12 |
| … échéance avec `order: dmy` (5 dates dont 4 ambiguës) | 5/5 (0/5 sans) | 5/5 (1/5 sans) |
| Disclosure : données personnelles d'un message sortant (13 attendues, 8 messages) | 13/13, 0 en trop | 13/13, 1 en trop (« jeudi ») |
| Préflight : nombre de tâches d'un message (estimation 0–10) | médiane exacte 4/8, intervalle couvre 8/8 | 2/8, 8/8 |
| Image : nombre de carrés (1 à 12) | exacte 18/24, intervalle 24/24 | 15/24, 24/24 |
| Modules concernés (choix multiple émulé, 10 messages) | 8/10 exacts | 9/10 (Drex Max 10/10, d1-ultra 8/10) |

Latence de ces questions courtes : 0,5–0,8 s (p50) pour 3 échantillons.

**Recommandation (proposition, pas de bascule)** : `liquid/d1.2-ultra` sur OpenRouter comme modèle principal du
préflight, Drex Max en secours dans la chaîne. Il divise par 3,8 la décision du préflight (p50 0,66 s contre 2,55 s,
p95 1,12 s contre 3,0 s — dans le budget déclaré de 1,5 s, que Drex Max dépasse) pour une qualité entre d1-ultra et
Drex Max (−1,5 pt contre Drex, non significatif à 95 %), et il est le seul à porter les nouveaux types. d1.2 seul :
non (−7 pts). Drex Max reste épinglé jusqu'à la décision de Monsieur.

## 5. Mesures avant / après

| Mesure | Avant (5 jours de production jusqu'au 16/11) | Après (fenêtre des essais 20:45–21:27, 17 tours de Lab) |
|---|---|---|
| Accueil d'un tour (`native_ms`) p50 / p95 / p99 | 2 308 / 5 399 / 7 194 ms | 2 486 / 5 649 ms |
| Décision du préflight p50 / p95 | 876 / 2 114 ms | 932 / 1 585 ms |
| Recherche du contexte après le plan p50 / p95 | 788 / 3 322 ms | 1 314 / 2 374 ms |
| Plans dégradés | 3 / 434 | 0 / 17 |
| Processus du moteur (RSS) | 196 Mo | 197 Mo ; un noyau au repos ≈ 13 Mo |
| Durée d'un tour p50 / p95 | 9,4 / 119,5 s (production) | runs de Lab 29,5 / 284,8 s (scénarios lourds) |

Lecture honnête : la latence avant le premier appel de modèle **n'a pas baissé** — cette mission a ajouté des
capacités (noyau, réveil, Decision), pas encore le gain de vitesse, qui viendra du modèle de décision (§ 4) ; la
fenêtre « après » est petite et faite de tours de test lourds. Mesure à refaire sur 5 jours de production :
`walter-python core/engine/bench/baseline.py --since 2026-11-17T00:00:00+00:00`. Référence : 
`@instance/state/core/engine/bench/baseline-before-20261116.json`, `after-lab-20261116.json`.

## 6. Ce qui reste (non fait, ou fait mais pas prouvé)

1. Banc d1.2 / d1.2-ultra fait par OpenRouter (17/11, § 4 bis) → proposition à Monsieur. Reste : clé Liquid
   (`LIQUID_API_KEY`) pour box, boxes, audio et le choix multiple natif ; adoption des nouveaux types par les modules
   propriétaires (triage, disclosure, documents.verify, préflight).
2. Choix du modèle de décision par besoin (budget de latence déclaré → le Router choisit) : non fait, une seule chaîne.
3. Questions du préflight compilées depuis le registre (sélection dynamique) : non fait, elles restent dans Context.
4. Reprise automatique d'une tâche de fond coupée par un redémarrage (tâches idempotentes) et réveil spontané après
   redémarrage : non fait — aujourd'hui l'avis arrive au prochain appel `python`.
5. Recherche documentaire large : 7,5 min ; le modèle attend ses sous-agents par `job_output` (consigne du noyau DSH).
6. Le modèle n'a pas signalé l'instruction cachée du scénario 10 (il l'a seulement ignorée).
7. Étiquettes de Monsieur sur les bancs (1/50, 5/63) : qualité contre son jugement encore inconnue.
8. Les tours de test (Lab canal `test`, compte `e2e`) créent des tâches durables dans la liste de Monsieur : 15
   fermées à la main le 16/11 (note « tour de test technique »). À corriger : pas de tâche du propriétaire pour un
   canal de test.

## 7. Retour arrière

`/user/Lucas/backups/changes/2026-11-16-engine-python/README.md` (moteur) et
`/user/Lucas/backups/changes/2026-11-16-walter-decision/README.md` (Decision). Aucune donnée supprimée ni réécrite.
