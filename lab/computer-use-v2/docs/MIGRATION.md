# Computer Use V2 — Migration path et lots mesurables

## Règle de coexistence

V1 reste la voie de production jusqu'à ce qu'un lot V2 satisfasse son gate. Aucun lot ne modifie la release certifiée. L'intégration future se fait par un nouveau plugin/version et les extension seams existants, avec feature flag et rollback vers V1.

## Lot 2.0 — Architecture et contrats (ce chantier)

**Livré**

- audit V1 read-only ;
- architecture et authority boundaries ;
- contrats exécutables DeviceContext, Activity, Policy, Offers/Costs, Observation, Execution, Vision ;
- surface model-facing `inspect|act|status` ;
- scénarios benchmark A–H et instrumentation contractuelle ;
- guards interdisant recipes, second browsing engine et faux multi-OS.

**Gate**

- suite contractuelle 100 % verte ;
- 8/8 scénarios chargés et validés en mode contract ;
- 0 app marker dans `adaptive_operator/*.py` ;
- 0 dépendance HTTP/browser dans le runtime ;
- seulement macOS `live_in_lot20` ;
- V1 release Git propre et hash plugin inchangé entre début/fin.

## Lot 2.1 — Shadow integration macOS

**But** : brancher la lecture du contexte et le catalogue d'offres sans autoriser V2 à muter le Mac.

**Travaux**

1. Nouveau plugin/version V2 hors plugin V1 actif.
2. Adapter `CuaDriverBackend` → provider macOS read-only : list apps/windows, exact target, AX no-pixels, screen metadata, CUA health.
3. Sources DeviceContext : config alias, référence Tailscale/SSH existante, discovery périodique, activity primitives read-only.
4. `computer_use(operation=inspect)` derrière feature flag ; V1 `goal` reste production.
5. Recorder de metrics/tokens/AX chars avec run ID et device ID pseudonymisé.

**Gate**

- 0 mutation émise par shadow mode ;
- 100 % des offers V2 ont provider/effects/confidence/cost/preconditions ;
- cache hit DeviceContext ≥ 95 % après warmup ;
- aucune redécouverte SSH/Tailscale par goal sur 100 résolutions consécutives ;
- observation minimal p95 ≤ 250 ms hors latence réseau à mesurer séparément ;
- payload observation minimal p95 ≤ 1 KiB ;
- 0 screenshot/vision dans A/B/D inspect-only ;
- V1 tests/smoke inchangés.

## Lot 2.2 — Policy enforcement et single-step canary

**But** : autoriser des actions L0 puis L1 bornées via `act`, sans plan runtime.

**Travaux**

1. Brancher `RuntimeEvidenceLedger` au vrai système de message/approval persistant ; aucun receipt model-supplied.
2. Adapter providers : native launch, exact focus selector, AX invoke/type/shortcut/scroll/drag.
3. Feature flag par device/session/action class.
4. Idempotency et audit avec Device Node pour filesystem/system actions appropriées.
5. V1 reste rollback immédiat.

**Ordre canary**

- L0 read-only ;
- A/B native launch avec warning L1 ;
- D AX deterministic ;
- C/F ensuite ;
- aucune L2 avant gate séparé.

**Gate**

- 0 dispatch L1 sans receipt valide ;
- 0 dispatch L2 sans confirmation grant valide ;
- 0 cross-device/cross-step/replay receipt accepté ;
- A/B/D success ≥ 99 % sur 30 runs chacun ;
- retries cachés = 0 ;
- warning count = nombre de transitions L1 visibles, ni 0 ni spam par primitive interne ;
- action confirmée par signal déterministe : screenshot=0, vision=0 ;
- rollback V1 testé en moins de 60 s.

## Lot 2.3 — Progressive observation et unknown-goal loop

**But** : remplacer `unsupported_goal` par observe → reason → act → verify.

**Travaux**

1. Mapping CUA elements → CompactObservation v2.
2. Query/ref progressive disclosure et expiry de snapshot.
3. Exposer `adaptation_required` au LLM sans automatic strategy loop.
4. Scénario F sur une fixture inconnue, pas sur une app codée dans les tests.
5. Scénario G avec vraie frontière Walter Browse puis Computer Use.

**Gate**

- F : success ≥ 90 % sur 30 variants de labels/layout ;
- aucun `unsupported_goal` pour goal inconnu observable ;
- AX chars p50 < 2 000, p95 < 8 000 pour les fixtures ;
- détails/pixels uniquement après demande ;
- G : `walter_browse_calls ≥ 1`, recherche visible Mac = 0 ;
- aucun import Walter Browse dans runtime CU ;
- total retries p95 ≤ 2, tous choisis par LLM.

## Lot 2.4 — Fast Vision Locator bake-off

**But** : implémenter E sans cascade de gros modèles.

**Travaux**

1. Harness de dataset : current crop, target, geometry hints, diff base, ground truth.
2. Comparer au moins : geometry cache, AX+vision fusion, lightweight VLM, SOM-assisted.
3. Provider choisi par config après benchmark, jamais hardcodé sans model-ID vérifié.
4. visual locate séparé de click et policy.

**Gate initial**

- localisation accuracy ≥ 97 % sur fixture held-out ;
- click task success ≥ 95 % sur 100 essais ;
- locator p50 ≤ 300 ms, p95 ≤ 800 ms sur l'environnement retenu ;
- maximum 1 vision call par tentative ;
- maximum 1 crop, zéro description plein écran ;
- stale snapshot/out-of-crop/low-confidence acceptés = 0 ;
- comparer coût total et latence, pas seulement précision.

Les seuils deviennent définitifs après baseline live ; Lot 2.0 ne choisit pas de modèle.

## Lot 2.5 — User activity aware operation

**But** : scénario H et adaptation à l'usage réel du Mac.

**Travaux**

1. Brancher primitives macOS fiables : lock state, foreground app, idle, recent input.
2. TTL court distinct du DeviceProfile stable.
3. Offers recalculent disruption/preconditions selon activity.
4. Préférer background/native ; warning avant toute action visible restante.

**Gate**

- lock-state false-negative = 0 sur suite contrôlée ;
- activité observée fraîche au moment du gate ;
- H : focus changes sans warning = 0 ;
- H : si offre L0 équivalente existe, action L1 choisie = 0 ;
- aucun polling agressif : budget activity probe documenté et mesuré ;
- aucun abandon silencieux : si L1 nécessaire, warning puis action ou résultat explicite.

## Lot 2.6 — Production cutover V2 macOS

**Prérequis** : gates 2.1–2.5, revue indépendante, replay sur release future exacte.

**Cutover**

1. snapshot/verify/rollback testés ;
2. compatibility gate sur base exacte ;
3. feature flag V2 par défaut off ;
4. canary sessions ;
5. comparaison V1/V2 A–H ;
6. bascule progressive ;
7. V1 conservé comme rollback pendant période définie.

**Gate**

- success V2 non inférieur à V1 sur A–D ;
- F/G/H passent les seuils ci-dessus ;
- baisse mesurable des screenshots, vision calls, AX tokens et focus changes ;
- 0 violation L1/L2 ;
- deuxième revue indépendante SHIP ;
- rollback drill vert.

## Hors périmètre explicite

- workflows Finder/Spotify/Photoshop ;
- App Profiles rigides ;
- provider Windows/Android ;
- browsing public dans Computer Use ;
- choix définitif d'un VLM ;
- gros refactor du core ;
- suppression du V1 avant cutover vérifié.
