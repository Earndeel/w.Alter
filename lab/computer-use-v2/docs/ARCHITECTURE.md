# Computer Use V2 — Adaptive Universal Operator Architecture

Statut : **Lot 2.0, socle contractuel exécutable, non intégré en production**  
Workspace isolé : (ancien dossier de travail, retiré le 2026-11-09)

## 1. Invariant directeur

```text
LLM = comprend le but, choisit la stratégie, demande l'information manquante,
      adapte après échec et décide quand la tâche est terminée.

Runtime = résout le device, expose des capacités et leurs coûts, applique la
          policy, exécute exactement un step, observe compactement et vérifie.
```

Le runtime n'analyse pas le goal avec des règles d'application, ne génère pas de recette, n'appelle pas automatiquement Walter Browse et n'effectue pas de ladder cachée. Un résultat non vérifié retourne au LLM avec `adaptation_required=true` et `next_authority=llm`.

## 2. Target V2

```text
                           ┌─────────────────────────┐
User goal ────────────────▶│ LLM / Universal Operator│
                           │ intent + strategy + adapt│
                           └───────┬──────────┬──────┘
                                   │          │
                 public Web info   │          │ real user session
                                   ▼          ▼
                         ┌──────────────┐  ┌──────────────────────┐
                         │walter_browse │  │computer_use (unique) │
                         │HTTP/Scrapling│  │inspect / act / status│
                         │Camoufox last │  └──────────┬───────────┘
                         └──────────────┘             │
                                                     ▼
                         ┌────────────────────────────────────────┐
                         │ Adaptive Operator Runtime              │
                         │ DeviceContextResolver                  │
                         │ CapabilityRegistry + CostWeights       │
                         │ InterruptionGate L0/L1/L2              │
                         │ ObservationBuilder progressive         │
                         │ one-step ExecutionEngine + verifier    │
                         └──────────────┬─────────────────────────┘
                                        │ provider-neutral offers
                         ┌──────────────┼────────────────┐
                         ▼              ▼                ▼
                  CUA/macOS       Device Node      FastVisualLocator
                  native + AX     durable ops      crop/diff/hints
                         │
              SSH/Tailscale connection selected from DeviceContext

Future provider boundary only:
                  ┌───────────────┬───────────────┐
                  │ macOS (live)  │ Windows       │ Android       │
                  │ Lot 2.x       │ contract only │ contract only │
                  └───────────────┴───────────────┘
```

## 3. Authority matrix

| Decision | LLM | Runtime | Walter Browse |
|---|---:|---:|---:|
| comprendre le goal | **owner** | non | non |
| décomposer et choisir le prochain step | **owner** | propose offers | non |
| décider qu'une documentation Web manque | **owner** | peut signaler offer externe | exécute la recherche demandée |
| rechercher le Web public | orchestre | **interdit** | **owner** |
| sélectionner le device connu | choisit alias si ambigu | **resolve/cache** | non |
| classer effets L0/L1/L2 | non fiable seul | **owner/enforced** | non |
| émettre warning L1 | message utilisateur | mint receipt après émission | non |
| obtenir confirmation L2 | demande utilisateur | mint/consume grant | non |
| choisir parmi offers suffisantes | **owner** | filtre + score advisory | non |
| exécuter une primitive | non | **owner** | non |
| vérifier par signal déterministe | reçoit résultat | **owner** | non |
| adapter après résultat non confirmé | **owner** | fournit evidence | non |
| décider fin de tâche | **owner** | non | non |

## 4. Unique front door

Le modèle garde un seul tool : `computer_use`. V2 ne publie pas les primitives comme 15 tools.

### 4.1 Opérations model-facing

Contrat exécutable : `adaptive_operator/front_door.py`.

```json
{"operation":"inspect","device_id":"mac-main","goal":"..."}
```

Résultat compact conceptuel :

```json
{
  "status": "needs_reasoning",
  "selection_authority": "llm",
  "executed": false,
  "device": {"id":"mac-main","activity":"active"},
  "observation": {"app":"Unknown","window":"Settings","snapshot":"s-18"},
  "offers": [
    {
      "id":"ax.invoke.current",
      "primitive":"invoke",
      "provider":"computer_use",
      "confidence":0.94,
      "cost":0.42,
      "interruption":"L0",
      "preconditions":["snapshot:s-18"]
    },
    {
      "id":"docs.external",
      "primitive":"research",
      "provider":"walter_browse",
      "boundary":"external_front_door"
    }
  ]
}
```

`inspect` n'exécute rien. Un goal inconnu retourne au minimum une offer `observe`, jamais un terminal `unsupported_goal`.

```json
{
  "operation":"act",
  "device_id":"mac-main",
  "offer_id":"ax.invoke.current",
  "arguments":{"ref":"e18-a97b31c2"},
  "verify":{"kind":"predicate","expected":{"selected":true}}
}
```

`act` exécute **une offer choisie par le LLM**. Il refuse une offer `provider=walter_browse` : le LLM doit appeler la vraie porte Walter Browse. Une offer portant `preconditions=["snapshot:s18"]` exige à la fois ce `snapshot_id` dans la requête et la confirmation d'un `snapshot_reader` runtime que `s18` est toujours courant ; sans reader ou sur mismatch, refus fail-closed. Ces contraintes sont testées.

```json
{"operation":"status","device_id":"mac-main","operation_id":"op-..."}
```

`status` est réservé aux opérations asynchrones/idempotentes du Device Node. Il exige un `status_reader` runtime injecté et refuse s'il est absent ; il n'autorise pas un polling ou retry caché.

### 4.2 Surface interne universelle

Contrat : `adaptive_operator/capabilities.py::Primitive`.

- observe
- launch_app
- focus
- open_url
- invoke
- type
- shortcut
- scroll
- drag
- filesystem
- system_action
- capture
- visual_locate
- visual_click
- verify

`research` existe seulement comme offer `provider=walter_browse` et est exclu de `computer_use_runtime_primitives()`.

## 5. DeviceContext persistant

Contrat : `adaptive_operator/device_context.py`.

```python
DeviceContext(
    profile=DeviceProfile(
        device_id: str,
        platform: Platform,
        hostname: str | None,
        connections: tuple[ConnectionCapability, ...],
        displays: tuple[DisplayProfile, ...],
        installed_apps: tuple[str, ...],
        accessibility: AccessibilityState,
        input: InputCapabilities,
    ),
    activity: DeviceActivity | None,
    health: DeviceHealth | None,
    updated_at: float,
    sources: tuple[str, ...],
)
```

### Sources et actualisation

```text
config/device alias ─┐
persistent JSON store├─▶ DeviceContextResolver ─▶ current context
periodic discovery ──┘       TTL ou refresh explicite
```

- `DeviceContextStore` est atomique (`.tmp` puis replace), multi-device et ne contient aucun device hardcodé.
- `DeviceContextResolver.resolve()` consulte d'abord le store ; il ne rappelle les discovery sources qu'après TTL ou `refresh=true`.
- `DeviceContextStore.update_runtime_state()` actualise activité/health sans pouvoir écraser hostname, connexions, displays, apps ou input capabilities, et sans prolonger le TTL du profil stable.
- un profil découvert plus ancien ne remplace pas le profil stable plus récent ; la plateforme d'un `device_id` existant est immuable et un conflit est refusé.
- activité et health portent leur propre `observed_at` ; une observation ancienne ne remplace pas une récente.
- connection `identity_ref` est une référence de config/vault, jamais un secret embarqué.
- le Mac principal actuel sera fourni par config/discovery dans le lot d'intégration, pas ajouté au code.

### Device activity contract

```python
DeviceActivity(
    observed_at: float,
    screen_locked: bool | None,
    foreground_app: str | None,
    idle_seconds: float | None,
    recent_keyboard: bool | None,
    recent_pointer: bool | None,
)
```

Lot 2.0 ne fait aucune déduction complexe : `user_active` est vrai si input récent ou idle < 30 s, faux si écran verrouillé, sinon inconnu. Les primitives macOS fiables seront branchées dans un provider ultérieur.

## 6. InterruptionPolicy runtime-enforced

Contrat : `adaptive_operator/interruption.py`.

La classe n'est pas choisie par le modèle. Elle est dérivée des `ActionEffects` immuables d'une offer enregistrée par un provider de confiance, puis vérifiée immédiatement avant dispatch. Les libellés L0/L1/L2 peuvent être rendus au LLM comme information de disruption, mais ne constituent ni une ladder ni une autorisation : seul le gate runtime décide.

| Niveau | Effets | Gate |
|---|---|---|
| L0 | lecture, HTTP externe, filesystem non visible, native background | aucune interruption |
| L1 | UI visible, focus, pointer, keyboard, desktop | receipt de warning obligatoire |
| L2 | destructif, unsaved work, permission sensible, irréversible, restart/shutdown | grant de confirmation obligatoire |

`RuntimeEvidenceLedger` émet des receipts/grants :

- opaques ;
- scopés à `device_id + action_scope` ;
- expirables ;
- consommés une seule fois ;
- absents du schéma modèle.

Un booléen model-supplied ne peut donc pas simuler une confirmation. Un écran verrouillé refuse une action L1 même avec warning.

Séquence L1 :

```text
LLM choisit offer L1
→ surface de messagerie émet réellement le warning
→ runtime mint warning_receipt(device, step, TTL)
→ act consomme receipt juste avant dispatch
```

Séquence L2 identique avec confirmation humaine et grant.

## 7. Adaptive capability selection

Contrat : `adaptive_operator/capabilities.py`.

Chaque provider publie des `CapabilityOffer` éphémères :

```python
CapabilityOffer(
    offer_id: str,
    primitive: Primitive,
    provider: CapabilityProvider,
    confidence: float,
    cost: CostEstimate,
    effects: ActionEffects,
    preconditions: tuple[str, ...],
    evidence: tuple[str, ...],
)
```

Le runtime :

1. supprime les offers sous le seuil de confiance ;
2. applique la borne d'interruption ;
3. calcule un score avec `CostWeights` configurables ;
4. rend une shortlist compacte triée de façon advisory.

Le score est :

```text
latency_seconds × w_latency
+ token_cost × w_token
+ interaction_cost × w_interaction
+ disruption × w_disruption
+ failure_risk × w_failure
```

Les poids ne sont pas une policy cachée codée en dur : `CostWeights` est un contrat configurable. Le LLM demeure `selection_authority=llm` et peut choisir une offer non première si le contexte du goal le justifie.

## 8. Compact Observation Model

Contrat : `adaptive_operator/observation.py`.

### Progressive disclosure

1. `minimal` : device/app/window/focus/snapshot/generation/element_count ;
2. `relevant` : ordre AX conservé, ou filtre littéral déterministe uniquement si le LLM fournit explicitement une query ; limite par défaut 20 ;
3. `detailed` : attributs seulement pour les refs demandées ;
4. `pixels` : crop lié au snapshot uniquement.

Exemple réel du contrat :

```json
{
  "schema_version":"2.0",
  "device":"mac-main",
  "app":"Safari",
  "window":"YouTube",
  "focus":true,
  "snapshot":"s18",
  "generation":18,
  "element_count":173,
  "elements":[
    {"ref":"e18-a97b31c2","role":"button","label":"Search","actionable":true}
  ],
  "truncated":true,
  "next_detail":"detailed"
}
```

Invariants :

- ref dérivée d'un identifiant natif et de la génération ;
- snapshot/generation obligatoires ;
- 256 caractères maximum par label ;
- bounds/attributs seulement quand nécessaires ;
- `pixels` exige un crop explicite et ne joint aucun élément AX ;
- une ref détaillée absente de la génération courante est refusée, jamais rendue comme liste vide ambiguë ;
- `ax_chars` mesuré dans le runtime, pas estimé après coup ;
- pixels jamais automatiques.

## 9. Fast Vision Click

Contrat provider-neutral : `adaptive_operator/vision.py`.

```python
VisionLocateRequest(
    request_id,
    snapshot_id,
    target,
    crop,
    budget=VisionBudget(max_latency_ms, max_image_pixels, max_output_tokens),
    geometry_hints=(),
    diff_base_snapshot=None,
    model_id=None,
    click=False,
)
```

Le locator :

- reçoit un crop courant, pas un écran arbitraire par défaut ;
- peut recevoir géométrie AX/cache et base de diff ;
- retourne point ou ref, confidence, latency et evidence ;
- **ne clique jamais** ;
- ne choisit pas définitivement un modèle dans Lot 2.0.

Validation avant mutation : même request, même snapshot, confidence suffisante, point dans crop, budget latency respecté. Ensuite seulement le LLM choisit l'offer `visual_click`, qui repasse par l'InterruptionGate et une vérification minimale.

Candidate pipeline à benchmarker, pas à figer maintenant :

```text
current snapshot
→ relevant region / cached geometry / screen diff
→ lightweight locator
→ validated point/ref
→ one click
→ deterministic signal or minimal crop diff
```

SOM reste une option de provider, pas une étape obligatoire.

## 10. Act → Observe → Verify → Adapt

Contrat : `adaptive_operator/execution.py`.

```text
ExecutionStep choisi par LLM
→ InterruptionGate
→ dispatch exact d'un seul step
→ si driver proof deterministic: confirmed, zéro observation
→ sinon observation minimale
→ predicate/diff/semantic verifier
→ ActionOutcome
→ si non confirmé: adaptation_required=true, next_authority=llm
```

`ExecutionEngine` garantit `automatic_retry_performed=false`. Une stratégie élément→pixel, AX→vision ou background→foreground doit être choisie à partir du résultat par le LLM ; elle n'est pas une boucle invisible du runtime.

## 11. Multi-OS sans fausse implémentation

`Platform = macos | windows | android`. La propriété `live_in_lot20` n'est vraie que pour macOS. Tous les autres contrats utilisent device, provider et capabilities, pas AppKit/Win32/ADB. Aucun provider Windows/Android n'est implémenté.

## 12. Ce qui est exécuté aujourd'hui

Implémenté et testé dans ce workspace :

- DeviceContext/Profile/Activity/Health + store + resolver TTL ;
- InterruptionPolicy L0/L1/L2 + receipts/grants runtime ;
- Capability/Cost model configurable ;
- compact progressive observation ;
- unique front-door protocol ;
- single-step execution/verification ;
- provider-neutral fast visual locator ;
- benchmark schema, metrics, validation et contract CLI ;
- architecture guards anti-recipes/anti-browsing-engine.

Volontairement non intégré dans Lot 2.0 :

- aucune modification du V1/core/plugin actifs ;
- aucun adapter macOS V2 branché ;
- aucun provider vision choisi ;
- aucune live automation A–H revendiquée ;
- aucun warning/approval UX branché ;
- aucune logique Windows/Android.
