# Audit global du harness Hermes

**Périmètre** : Desktop → Gateway → session → agent → provider → outils → persistance → réponse  
**Instance auditée** : `<repo>` et `<state-db>`  
**Révision** : `<commit / branch / dirty state>`  
**Snapshot UTC** : `<timestamp>`  
**Nature** : audit de l’état observé, pas certification d’un état non testé

> Ce document est le livrable global autoritatif. Les études provider sont en annexe.

## 1. Verdict exécutif

- État global : `<fonctionnel / dégradé / bloqué>`
- Critiques : `<faits mesurés>`
- Hauts : `<faits mesurés>`
- Principales inconnues : `<unknowns>`
- Hypothèses antérieures corrigées : `<claim → evidence>`

## 2. Méthode et niveau de preuve

Définir : **MESURÉ**, **OBSERVÉ DANS LE CODE**, **RISQUE**, **INCONNU**.

Lister les sources : code/hashes, tests, DB read-only, runtime, logs, payloads, provider captures.

## 3. Cartographie du flux complet

```text
Desktop
  → Electron / JSON-RPC
  → tui_gateway
  → session lifecycle
  → AIAgent / conversation loop
  → turn context
  → ProviderTransport / NormalizedResponse
  → tools / retries / interruption
  → compression / split
  → SessionDB
  → outbound events / Desktop state
```

Pour chaque frontière : fichiers/symboles, contrat d’entrée/sortie, propriétaire, mutation d’état, invariant, failure modes, tests existants/manquants.

### 3.1 Desktop et JSON-RPC
### 3.2 Session et ownership
### 3.3 Assemblage du contexte
### 3.4 Abstraction provider
### 3.5 Streaming/retry/interruption
### 3.6 Cycle de vie outils
### 3.7 Compression et continuité
### 3.8 Persistance et projection
### 3.9 Événements retour
### 3.10 CLI/API/messaging

## 4. Sécurité

### 4.1 Secrets au repos

Ne publier que les classes et comptes de candidats. Ne jamais imprimer les valeurs.

### 4.2 Réseau et auth

Comparer configuration déclarée, bind réel, proxy/tunnel connu et mécanisme d’auth.

### 4.3 Permissions d’outils

Documenter toolsets actifs, confirmations, side effects et redaction pré-écriture.

## 5. Robustesse et observabilité runtime

- services, restarts, RSS, workers et ownership ;
- appels, retries, tokens, cache, coûts et limites de comptage ;
- logs, erreurs, compactions, corruption/OOM observés ou absents ;
- DB, WAL, FTS, croissance, rétention et backup.

## 6. Résultats de validation

| Lot | Résultat | Interprétation |
|---|---:|---|
| Gateway/session/WebSocket | `<n>` | `<pass/fail/skew>` |
| Transports/provider parity | `<n>` | `<...>` |
| Compression | `<n>` | `<...>` |
| Tools/DB | `<n>` | `<...>` |
| Electron | `<n>` | `<...>` |
| Desktop UI | `<n>` | `<...>` |
| TypeScript/lint | `<result>` | `<...>` |
| DB integrity / diff check | `<result>` | `<...>` |

Décrire séparément les tests bloqués à la collecte et les vrais échecs fonctionnels.

## 7. Registre des risques priorisés

| ID | Sévérité | Statut | Risque | Preuve | Prochaine validation |
|---|---|---|---|---|---|
| `<ID>` | `<CRIT/H/M/L>` | `<measured/risk/unknown>` | `<...>` | `<...>` | `<...>` |

## 8. Plan d’action coût-bénéfice

### P0 — sécurité/intégrité/instabilité mesurée
### P1 — fiabilité/visibilité/E2E
### P2 — optimisation/durcissement

Préserver le contexte utile et les index qui apportent une qualité mesurable. Optimiser d’abord les postes qui représentent une part substantielle du coût ou du risque.

## 9. Annexes provider

Pour chaque provider : type de preuve, endpoint, body capturé ou reconstruit, usage retourné, erreurs strictes, limites de généralisation.

## 10. Artefacts et reproductibilité

- rapport ;
- métriques JSON ;
- script de collecte ;
- hashes des sources ;
- sous-audits ;
- rapports archivés.

Inclure le SHA-256 des artefacts **après** leur écriture finale.

## Conclusion

Dire explicitement ce qui est validé, ce qui est dégradé, ce qui reste inconnu, et les trois prochains chantiers à meilleur rendement.
