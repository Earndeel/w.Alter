# core/security — politique d'exécution unique de Walter

| | |
|---|---|
| **Rôle** | Une seule politique pour tout ce qui exécute un outil (lot E3) : ce qu'un agent ne fait jamais, ce qu'une porte (web, Telegram, API, mode commande) autorise, demande ou refuse, et ce qu'un sous-agent peut au plus (jamais plus que son parent). |
| **Propriétaire** | walter-core. Les classes de confidentialité restent fournies par Walter Memory (`/v1/privacy/classify`, contrôle de divulgation `/v1/disclosure/check`). |
| **État** | Implémentée et testée le 10/11/2026. **Filet du serveur MCP actif** pour chaque nouveau processus `server.py` (tout client). Greffon du moteur prêt, interrupteur `[dsh.engine] policy = "off" \| "enforce"` ; en service : `off` jusqu'à l'activation d'E2/E3 sur `dsh-web`. |
| **Ne fait pas** | Ne demande rien elle-même : `ask` passe par le répondant de la porte (dialogue web, boutons Telegram) via le mécanisme d'approbation du noyau, sans répondant = refus. Ne remplace pas le bac à sable du noyau (écritures confinées), qui décide encore après elle. Ne lit ni ne journalise la valeur des arguments sensibles. |
| **Contrats** | `policy.json` (données) ; décision v1 (`../engine/contracts/policy-decision.v1.json`) : `allow` \| `check` (contrôle de divulgation) \| `ask` \| `deny`, avec la règle appliquée. |

## Fichiers

| Fichier | Contenu |
|---|---|
| `policy.json` | `never` (fichiers de secrets et d'accès, commandes qui révèlent un secret, profondeur de délégation), `classes` (read, write_local, shell, outgoing, act_as_owner, delegate ; nom d'outil exact ou motif `*`), `presets` par porte, `interfaces` (porte → preset), `mcp_clients` (client MCP → porte) |
| `walter_security/policy.py` | `load`, `decide`, `classify`, `strictest` (Python) |
| `policy.mjs` | les mêmes fonctions en JS, pour le moteur |
| `walter_security/mcp_guard.py` | filet du serveur MCP : un appel refusé n'atteint jamais l'outil, quel que soit le client ; `walter_call` est jugé comme l'outil qu'il ouvre |
| `tests/vectors.json` | cas partagés, joués par `tests/test_policy.py` et `tests/policy.test.mjs` : les deux côtés décident pareil |

## Ordre de décision (le plus restrictif l'emporte)

1. **Jamais** : profondeur de délégation ≥ `max_depth` ; chemin protégé dans les arguments de chemin (ou n'importe
   où dans une commande shell, liens symboliques résolus, `~/` compris) ; commande qui révèle un secret (`bw …`,
   `walter-secret get|file|grant access`). La voie admise est `walter-secret exec --bind` (valeur jamais vue).
2. **Classe de l'outil** sous le preset de la porte de la session (une session enfant est jugée sous la porte de sa
   racine) ; outil inconnu = `unknown` du preset (demande).
3. **Enfant** : le preset `child` s'applique en plus dès la profondeur 1 (jamais d'envoi à un tiers, demande avant
   d'agir au nom de Monsieur).
4. `check` : contrôle de divulgation de Memory (bloque ⇒ refus, demande ⇒ demande, indisponible ⇒ demande).
5. Puis le noyau : bac à sable et ses propres demandes.

## Qui l'applique

- **Moteur** (`../engine/plugins/policy`) : garde monotone (`ctx.tools.guard`, refus que rien ne peut lever) +
  `tools/pre-execute` (demande, divulgation) pour chaque appel de chaque agent, enfants et appels imbriqués de
  `run_code` compris. Journal des décisions non triviales : `@instance/state/core/security/policy-<jour>.jsonl` (outil,
  classe, règle ; jamais les arguments). Les refus et approbations apparaissent aussi dans le journal de session, donc
  dans walter_logs.
- **Serveur MCP walter** (`server.py`, tout client : moteur, Claude Code, Codex, Hermes tant qu'il existe) : refus
  seulement (`deny`) ; les demandes restent au client qui a un répondant. Journal : `mcp-<jour>.jsonl`.

## Tests

`walter-python -m pytest -q core/security/tests` ; `node --test core/security/tests/policy.test.mjs` (aussi par
`core/engine/tests/test_engine_plugins.py`).

## Retour arrière

Moteur : `[dsh.engine] policy = "off"` puis `walter harness install dsh --apply` et redémarrage de `dsh-web` (le bac à
sable et l'approbation du noyau restent : jamais moins protégé qu'avant). Serveur MCP : retirer les trois lignes
`mcp_guard` de `server.py` (sauvegarde : `@instance/backups/changes/2026-11-10-engine-E2-activation/code-before/`).
