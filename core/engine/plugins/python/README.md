# core/engine/plugins/python — noyau Python persistant du moteur (`walter-python`)

| | |
|---|---|
| **Rôle** | Donne à l'agent du moteur un outil `python` : un noyau Python **persistant par conversation** (variables, imports, fonctions gardés d'un appel à l'autre et après compaction), d'où il appelle les outils Walter sous la même politique qu'un appel direct (`await tools.<nom>(**args)`, en parallèle avec `asyncio.gather`), lance des **tâches de fond** qui sont des tâches du moteur (il est réveillé quand elles finissent) et des **sous-agents** (`delegate`, `delegate_all`). Idée reprise d'Unharnessed (Lab, 16/11), adaptée au moteur unique au lieu de tourner à côté. |
| **Propriétaire** | walter-core (`core/engine`). Interrupteur `[dsh.engine] python = "off" \| "on"` dans `walter instance config core engine.toml`, rendu par `walter harness install dsh` (bloc `walter-python` de `cordis.patch.yml`) ; maison de test : variable `WALTER_ENGINE_PYTHON`. |
| **État** | **En service** : le noyau `runtime/walter_kernel.py` est celui du moteur natif (`walter-engine`, réglage `[native] python`, depuis le 17/11/2026) ; le greffon `index.mjs` ne sert qu'au retour arrière vers DSH (désinstallé le 18/11). Historique : en service sur `dsh-web` depuis le 16/11/2026. Prouvé en Lab (`/opt/dsh/lab-home`) et en production (compte de test `e2e`) : outils depuis Python, reprise après redémarrage, sous-agents en parallèle, réveil sur fin de tâche, isolation entre conversations (`docs/07-CONVERGENCE.md`). |
| **Ne fait pas** | N'administre pas l'hôte (l'outil `bash` du moteur le fait, sous la politique) ; ne lit aucun secret ni service local (réseau local refusé, `/root`, `/user/Lucas` et les maisons du moteur inaccessibles) ; ne choisit pas de modèle (un sous-agent demande un **poste** du Router) ; ne relance pas seul une tâche de fond coupée par un redémarrage (il le dit au tour suivant, une fois) ; n'écrit ni mémoire ni journal à lui (walter_logs garde les tours, Memory les runs). |
| **Contrats** | Protocole noyau ↔ greffon : JSON par ligne sur stdin/stdout (`runtime/walter_kernel.py`, en tête : `execute`, `interrupt`, `snapshot`, `restore`, `host_reply`, `job_bound`, `shutdown` ; événements `result`, `host`, `job`, `snapshot`…) ; outils du moteur par `ctx.tools.execute` (politique `core/security/policy.json`, classe `shell`) ; tâches par le service `jobs` du noyau DSH (`python-<n>`, `job_output` / `job_kill`) ; tour de réveil : `engine/plugins/intake` (run rattaché au tour qu'il continue, `trigger: wake:<avis>`). |

## Bulle (sécurité technique, pas un jugement de modèle)

Chaque noyau est une unité systemd transitoire `walter-python-<clé>` lancée par `systemd-run` (`bubbleArgv`) :
utilisateur `walter-sandbox` (sans shell ni home, uid système), `ProtectSystem=strict`, `ProtectHome=yes`,
`PrivateTmp`, `PrivateDevices`, `NoNewPrivileges`, aucune capacité, espaces de noms refusés, `UMask=0077` ;
**seul dossier inscriptible** : le sien (`@instance/state/core/engine/python/<clé>/`, monté en `/kernel`) ;
réseau local et privé refusé (`IPAddressDeny` 127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, fc00::/7,
fe80::/10 ; seul le résolveur 127.0.0.53 passe) : le noyau n'atteint Walter que par `tools`, donc par la politique ;
plafonds `MemoryMax` 4G, `TasksMax` 256, `CPUQuota` 200 %, cellule 10 min, arrêt après 20 min d'inactivité.
`PATH` commence par l'environnement du noyau (`/services/python/engine-python/bin` : `python`, `pip`).

Le moteur reste root (il administre l'hôte par `bash`, sous la politique) ; le code écrit par un modèle, lui, ne
s'exécute jamais avec ces droits. Une demande d'appel qui nomme un fichier de secrets est refusée en entier par la
politique avant le noyau (règle déterministe).

## Fichiers

| Fichier | Contenu |
|---|---|
| `index.mjs` | Greffon : outil `python`, une instance `Kernel` par conversation (démarrage, cellule, interruption, instantané après chaque cellule, restauration au redémarrage, arrêt sur inactivité), relais des appels d'outils, tâches de fond liées au service `jobs` du moteur (`job_bound`, `<clé>.jobs.json` = tâches en cours, avis « arrêtées par un redémarrage » une fois), recherche d'outils, bulle |
| `runtime/walter_kernel.py` | Le noyau : espace de noms, `tools`, `bash`, `spawn`, `Job` (`await job.wait()`), `delegate`, `delegate_all`, instantané `dill` (`.snapshot/state.pkl`), restauration |
| `runtime/test_kernel.py` | Tests du noyau seul |

État : `@instance/state/core/engine/python/` — un dossier par noyau (0700 `walter-sandbox`), `<clé>.owner.json`,
`<clé>.jobs.json`, `kernels-<jour>.jsonl` (cycle de vie, jamais le code ni les sorties).

## Tests

`node --test core/engine/tests/python.test.mjs` (dont la vraie bulle quand lancé en root) ;
`/services/python/engine-python/bin/python core/engine/plugins/python/runtime/test_kernel.py`.

Retour arrière : `/user/Lucas/backups/changes/2026-11-16-engine-python/README.md`.
