# Computer Use V2 — Lot 2.1 macOS Shadow Integration

## Statut

Implémentation et benchmark terminés dans le workspace isolé :

(ancien dossier de travail, retiré le 2026-11-09)

Lot 2.0 reste certifié et immuable :

- archive : (ancien dossier de travail, retiré le 2026-11-09)
- SHA-256 : `867f333f7140b3e083ebb72e0a9660865093e386032afd4966ab808f3281cf3a`
- revue finale : hash vérifié, manifeste vérifié, tests 51/51, benchmark 8/8, `must_fix=[]`, `passed=true`

## Invariant de branchement

```text
LLM
 └─ computer_use
     └─ V1 walter backend ──▶ Mac

state.db (résultats V1 déjà persistés, lecture seule)
 └─ V2 sidecar hors processus
     ├─ ObservationContract minimal/relevant/detailed
     ├─ Shadow InterruptionPolicy
     ├─ DeviceContext cache
     └─ spool telemetry privé
```

Le sidecar n'est pas importé dans V1 et ne modifie ni prompt, ni schéma outil, ni réponse modèle, ni routing, ni Walter Browse, ni plugin V1. Une panne sidecar ne peut pas lever une exception dans le chemin V1.

## Seam réel

Le sidecar lit `~/.hermes/state.db` avec SQLite URI `mode=ro` et corrèle :

- message assistant contenant `tool_calls` ;
- message tool `tool_name=computer_use` ;
- même `tool_call_id` ;
- timestamps call/result pour la latence V1.

Aucun import de `CuaDriverBackend`, aucune session RPC, aucun `call_tool`, aucun second `capture`/`AX.observe`. Les paires historiques définitivement malformées sont quarantinées ; un résultat non apparié reste bloquant pour ne pas masquer une course de persistance.

Le spool écrit un fichier privé par `result_message_id`, puis un curseur atomique. Le replay est idempotent : un fichier existant n'est jamais écrasé.

## Opérationnalisation

Unités séparées de V1 :

- `/etc/systemd/system/computer-use-v2-shadow.service`
- `/etc/systemd/system/computer-use-v2-shadow.timer`

Le service est `Type=oneshot`, sans `Restart=`, `Nice=10`, I/O idle, `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateDevices`, `RestrictAddressFamilies=AF_UNIX`. Il peut lire `state.db` et écrire uniquement dans :

(ancien dossier de travail, retiré le 2026-11-09)/artifacts/shadow-spool`

Permissions : dossiers `0700`, événements/curseur `0600`.

Preuve du premier branchement :

- 277 événements V1 persistés ;
- 277 fichiers créés ;
- second poll : 0 événement vu, 0 fichier créé ;
- curseur : 283039 ;
- appels backend supplémentaires : 0 ;
- failures shadow affectant V1 : 0 ;
- service : `Result=success`, `ExecMainStatus=0`, `NRestarts=0` ;
- timer : active/waiting.

## DeviceContext réel

### Sources

| Fait | Source | Fraîcheur | Appel Mac |
|---|---|---:|---:|
| device identity | alias runtime + peer Tailscale local | stable | 0 |
| OS/platform | batch SSH read-only fixe (`sw_vers`) | stable | refresh missing/stale seulement |
| connexion/route | `remote-cua.json` + `tailscale status --json` local | 30–60 s | 0 |
| display geometry | batch fixe `system_profiler SPDisplaysDataType` ; sinon payload V1 si dimensions positives | semi-stable | même refresh batch |
| driver health | batch fixe `cua-driver status` + capture health V1 | 30–60 s | même refresh batch / 0 si V1 |
| Accessibility | payload V1 si prouvé ; sinon `unknown` | volatile | 0 dans ce lot |
| current activity / foreground | payload V1 `list_apps`/capture si présent | par observation | 0 |
| idle/recent input | `ioreg IOHIDSystem HIDIdleTime` dans batch fixe | 5–15 s | refresh missing/stale seulement |
| screen lock | payload V1 si présent ; sinon `unknown` | 15–30 s | 0 |

Aucune donnée personnelle ou clé privée n'est codée dans `adaptive_operator`. Le store contient une référence runtime à la connexion, jamais une clé Tailscale ou SSH.

### Probe live constaté

- macOS `15.7.7` ;
- display `2880×1800`, scale inconnue ;
- driver `healthy` ;
- Accessibility `unknown` ;
- foreground app, idle, recent input et lock : `unknown` dans la session SSH non-GUI ;
- premier refresh missing/stale : 1 batch read-only ;
- second resolve : cache hit, 0 appel ;
- mutation/capture/focus : 0.

Le cache persistant a servi 100 résolutions : 100 cache hits, 0 redécouverte Tailscale/SSH, 4,746 ms au total.

## Observation V1 → V2

Exemple riche réel :

- source V1 : capture Safari, 700 éléments sérialisés, total déclaré 971 ;
- snapshot V2 : `<session_id>:<result_message_id>` ;
- génération : `result_message_id` ;
- refs historiques sans `element_token` : `shadow_synthetic`, donc non actionnables ;
- screenshot automatique : 0.

Mesures sur 30 runs par niveau :

| Niveau | raw tokens estimés | compact tokens estimés | réduction | shadow CPU p50/p95/max | compaction p50/p95/max |
|---|---:|---:|---:|---:|---:|
| minimal riche | 18 495 | 1 | 99,997 % | 5,260 / 5,364 / 13,222 ms | 3,728 / 3,795 / 11,633 ms |
| relevant riche | 18 495 | 727 | 96,073 % | 7,700 / 7,779 / 7,880 ms | 6,097 / 6,216 / 6,246 ms |
| detailed riche | 18 495 | 847 | 95,424 % | 7,830 / 8,004 / 16,514 ms | 6,211 / 6,334 / 14,877 ms |
| minimal sparse | 19 | 1 | 97,333 % | 0,090 / 0,120 / 0,130 ms | 0,013 / 0,014 / 0,014 ms |
| relevant sparse | 19 | 34 | -80,0 % | 0,109 / 0,156 / 0,175 ms | 0,026 / 0,050 / 0,052 ms |
| detailed sparse | 19 | 40 | -112,0 % | 0,110 / 0,133 / 0,138 ms | 0,026 / 0,037 / 0,043 ms |

Le cas sparse montre l'overhead du contrat V2 : compact n'est pas automatiquement plus petit lorsque la source ne contient qu'un nœud.

Sur 180 runs mesurés après 60 warmups :

- intervalle V1 persisté (timestamp assistant → résultat tool, pas `duration_ms`) : p50 `410,433`, p95/max `1 489,015` ms ;
- shadow CPU : min `0,086`, p50 `0,175`, p95 `7,869`, max `16,514` ms ;
- compaction : min `0,012`, p50 `0,052`, p95 `6,246`, max `14,877` ms ;
- DeviceContext cache : p50 `0,107`, p95 `0,140`, max `0,169` ms ;
- activity detection : p95 `0,00080` ms ;
- policy classification : p95 `0,01628` ms ;
- critical-path overhead V1 : min/p50/p95/max `0` ms ;
- fraîcheur des refs : `unknown` sur 180/180 runs, car 0 ref native et uniquement des refs synthétiques non actionnables ;
- appels backend supplémentaires : 0.

## Matrice A–H

| ID | Scénario | Statut | Preuve |
|---|---|---|---|
| A | Safari déjà ouvert | observed | `list_apps` V1 persisté rapporte Safari running |
| B | Finder foreground | unknown | dernière preuve foreground = Hermes, pas Finder ; aucune action forcée |
| C | AX riche | observed | capture V1 réelle, 700 éléments |
| D | AX pauvre | observed | capture V1 réelle, 1 élément |
| E | utilisateur actif | unknown | recent input absent du contexte SSH non-GUI |
| F | Mac idle | unknown | idle indisponible ; aucune simulation |
| G | écran verrouillé | unknown | état non exposé et verrouillage non forcé |
| H | requête Web | contract_observed | `external_provider=walter_browse`, Computer Use ne l'exécute pas |

`unknown` n'est jamais promu en pass ou en postcondition satisfaite. Le rapport porte `postcondition_satisfied="unknown"`.

## Shadow InterruptionPolicy observée

277 actions V1 réelles :

- L0 : 167 ;
- L1 : 65 ;
- L2 : 1 ;
- unknown : 44 goals composites sans effets atomiques exposés.

Exemples :

| Action réelle V1 | Effet observé | Niveau | would_warn | would_confirm | Enforcement V2 |
|---|---|---:|---:|---:|---:|
| capture/list_apps/list_windows/wait/verify_state | read-only | L0 | false | false | false |
| launch_app/open_url/type/click/key | visible/input | L1 | true | false | false |
| focus_app raise=false | aucune élévation | L0 | false | false | false |
| focus_app raise=true | UI visible + focus | L1 | true | false | false |
| kill_app | destructif + risque travail non sauvegardé | L2 | false | true | false |
| goal composite | effets atomiques absents | unknown | false | false | false |

Aucun warning ni confirmation n'est réellement émis par V2 dans ce lot ; ce ne sont que des prédictions de télémétrie.

## Gates Lot 2.1

```text
V1 behavior changed                         = false
model-facing schema changed                 = false
V1 production source changed                = false
V2 device actions                           = 0
V2 clicks                                   = 0
V2 keystrokes                               = 0
V2 focus changes                            = 0
V2 screenshots                              = 0
V2 vision calls                             = 0
duplicate backend observations              = 0
shadow failures affecting V1                = 0
additional backend calls on reused V1 data  = 0
```

Intégrité après exécution :

- archive Lot 2.0 SHA-256 inchangée ;
- V1 HEAD `c00089cd6113bdc039abccd9c4fb21243a81904d` ;
- V1 tree `cf12115dd9a2502065b59431d0a8245e96320228` ;
- V1 git clean ;
- plugin `__init__.py` SHA-256 `fb53e390bce004fae0c75bc9f5641a5d297d0a150f78c15e8ea700fb206e1168` ;
- plugin `plugin.yaml` SHA-256 `5727e8a31317b47ec4bd81ff23ada1e5da846cfb18422c8b39d646fdd097030f` ;
- `state.db` size et mtime inchangés pendant le benchmark.

## Budgets proposés pour Lot 2.2

Première baseline, donc budgets proposés et non rétroactivement appliqués :

- shadow CPU local p95 ≤ 12 ms, max ≤ 30 ms ;
- compaction riche p95 ≤ 10 ms ;
- DeviceContext cache p95 ≤ 0,5 ms ;
- policy classification p95 ≤ 0,1 ms ;
- critical-path overhead V1 = 0 ms tant que le sidecar reste hors processus ;
- cache hit profil stable ≥ 99 % après warmup ;
- redécouverte SSH/Tailscale sur profil frais = 0 ;
- appels backend dupliqués = 0 ;
- mutation/screenshot/vision = 0 jusqu'au lot qui les autorise explicitement.

## Gaps Lot 2.2

1. Les résultats V1 persistés sont capés et ne contiennent aucun `element_token` natif ; les refs shadow sont donc non actionnables. Un hook/backend observer in-process serait nécessaire pour l'AX complet natif, mais augmenterait le couplage au V1.
2. User Presence via SSH non-GUI reste partiel. Brancher des primitives driver déjà existantes (`desktop_unlocked`, frontmost/list_apps) uniquement lorsqu'elles figurent dans le payload V1, sans second appel.
3. Le spool persiste des libellés AX privés en `0600`; définir rétention/rotation et éventuelle redaction avant conservation longue.
4. Les 10 paires historiques malformées doivent rester quarantinées et monitorées, pas supprimées de `state.db`.
5. B/E/F/G restent inconnus par contrainte de non-perturbation ; prévoir fixtures contrôlées dans un lot benchmark dédié si une couverture observée est exigée.
6. Ne pas activer enforcement, vision live, visual click, retry automatique ou nouvelle surface modèle dans Lot 2.2 sans un lot explicite séparé.
