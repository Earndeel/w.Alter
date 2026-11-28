# Lot 2.0 — Rapport de revue indépendante

## Verdict

**SHIP pour le socle contractuel isolé. DO NOT INTEGRATE LIVE YET.**

Les trois revues READ-ONLY initiales ont couvert :

1. audit V1 core/plugin avec citations ;
2. revue contradictoire « LLM cerveau vs runtime RPA » ;
3. design benchmark SIM/LIVE, instrumentation et sécurité.

Une quatrième revue finale a été demandée sur l'artefact post-corrections. Le statut final doit être interprété avec les preuves d'exécution locales ci-dessous ; aucun résultat live macOS n'est revendiqué.

## Findings incorporés

### 1. Approval V1 sans callback local

La revue a corrigé une formulation trop forte : `_request_approval` autorise si aucun callback local n'est câblé, en supposant le gateway externe. V1 reste CLOSED ; le risque est documenté dans `V1_AUDIT.md`. V2 refuse si son gate/reader requis est absent.

### 2. L0/L1/L2 ne doit pas devenir une ladder

Décision : niveaux dérivés des effets immuables du provider, gate runtime seul autoritaire. Le LLM peut voir une estimation de disruption, mais ne choisit ni son autorisation ni une ladder automatique.

### 3. DeviceContext ne doit pas devenir cache de vue

Le profil persistant ne contient aucun AX, screenshot, ref ou snapshot. Une voie `update_runtime_state()` actualise activité/health sans écraser le profil stable ni prolonger son TTL.

### 4. Observation compacte sans intelligence cachée

L'ordre AX est conservé ; seul un filtre littéral demandé explicitement par le LLM peut réduire les éléments. `pixels` exige un crop et ne joint pas AX. Les refs inconnues/stale sont refusées.

### 5. Costs configurables et advisory

`CostWeights` est injecté dans `CapabilityRegistry`, pilote seulement le tri compact et laisse `selection_authority=llm`. Aucun planificateur runtime ne consomme ce classement pour agir.

### 6. Snapshot precondition fail-closed

Une offer liée à un snapshot requiert un `snapshot_reader` runtime et l'égalité entre snapshot attendu, snapshot demandé et snapshot courant. Sans reader, refus.

### 7. `status` réellement exécutable

`status` utilise uniquement un reader injecté ; en son absence, il refuse. Il ne poll ni ne retry automatiquement.

### 8. Benchmark anti-fausse-preuve

Une route attendue sans événement route échoue. H n'exige plus un warning artificiel si L0 suffit ; il échoue seulement lorsqu'un focus change est observé sans warning.

## Risques volontairement différés

- Le provider macOS V2 n'est pas intégré.
- Les activity primitives macOS ne sont pas branchées.
- Aucun provider vision n'est choisi.
- Les receipts sont un ledger contractuel en mémoire ; l'intégration doit utiliser le vrai store message/approval persistant.
- Le benchmark live exige un compte macOS sandboxé, fixtures contrôlées et abort d'urgence.

Ces points appartiennent aux Lots 2.1+, pas à un patch clandestin du Lot 2.0.

## Gates avant Lot 2.1

- V1 release et plugin immuables ;
- suite contractuelle verte ;
- benchmark contract 8/8 et explicitement non-live ;
- zéro recipe/app marker/runtime Web import ;
- scan statique sans finding ;
- shadow mode read-only uniquement.
