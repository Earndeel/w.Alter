# Computer Use V2 — Benchmark A–H

## Statut

Lot 2.0 livre :

- manifeste A–H exécutable ;
- event schema append-only JSONL ;
- agrégateur de toutes les métriques demandées ;
- validation des routes, postconditions, warnings et budgets Web/vision ;
- CLI `contract` qui teste l'instrumentation sans piloter le Mac.

Lot 2.0 **ne revendique aucun résultat live macOS**. `evidence_class=contract_only` et `live_execution_performed=false` sont obligatoires en mode contract. La CLI ne propose volontairement pas de faux mode `live`.

## Exécution contractuelle

```bash
cd (ancien dossier de travail, retiré le 2026-11-09)
python3 -m adaptive_operator.benchmark_cli contract \
  --scenarios benchmarks/scenarios.json \
  --output artifacts/contract-benchmark
```

Sorties par scénario :

- `<scenario>.events.jsonl` : événements bruts append-only ;
- `<scenario>.report.json` : agrégation et classe de preuve.

## Scénarios

| ID | But | Route attendue | Contraintes initiales |
|---|---|---|---|
| A | ouvre Safari | computer_use → native.launch_app → verify | Walter Browse 0, screenshot 0, vision 0, warning L1 ≥1 |
| B | ouvre Finder | computer_use → native.launch_app → verify | mêmes budgets que A |
| C | Finder + Downloads | observe → invoke → verify | Web 0, warning L1 ≥1 |
| D | élément AX identifiable | observe.ax → invoke → verify | screenshot 0, vision 0 |
| E | élément uniquement visuel | crop → visual_locate → visual_click → verify | screenshot ≤1, vision ≤1 |
| F | app inconnue | observe → LLM reason → invoke → verify | aucune recipe/app profile |
| G | documentation puis action | CU observe → Walter Browse → CU → verify | Walter Browse exactement 1 ; navigateur Mac pour recherche interdit |
| H | même tâche, utilisateur actif | activity → background/research → CU → verify | warning seulement si une action L1 est réellement nécessaire ; aucun focus change non averti |

Les apps nommées A–C appartiennent au benchmark, pas au runtime. Les tests d'architecture interdisent ces noms dans `adaptive_operator/*.py`.

## Événements et compteurs

`MetricKind` :

- `llm_call` avec `input_tokens`, `output_tokens` ;
- `computer_use_call` ;
- `walter_browse_call` ;
- `screenshot` ;
- `vision_call` ;
- `ax_payload` avec `chars`, `tokens` ;
- `focus_change` ;
- `mouse_movement` ;
- `interruption_warning` ;
- `retry` ;
- `route` ;
- `postcondition` avec `satisfied`.

Agrégat `BenchmarkMetrics` :

```text
success
total_latency_ms
llm_calls
computer_use_calls
walter_browse_calls
screenshots
vision_calls
ax_chars
ax_tokens
input_tokens
output_tokens
focus_changes
mouse_movements
interruption_warnings
retries
evidence_class
```

Les compteurs proviennent d'événements aux frontières réelles : provider LLM, tool dispatcher, Walter Browse front door, capture/vision provider, AX encoder, interruption gate et device driver. Ils ne doivent pas être reconstruits depuis le texte final du modèle.

## Protocole live macOS — lot ultérieur

### Fixtures

1. **Native launch fixture** : app réelle + inspection déterministe process/window.
2. **AX fixture** : petite app de test dont le bouton publie un rôle/label/stable postcondition.
3. **Visual-only fixture** : cible Canvas/image sans nœud AX, postcondition accessible hors pixels.
4. **Unknown-app fixture** : labels/layout randomisés et nom d'app absent du prompt/runtime.
5. **Documentation fixture** : procédure hébergée sur une page Web publique de test, secret d'action absent de l'UI initiale.
6. **Active-user fixture** : générateur d'activité contrôlé et mesure indépendante focus/pointer.

Finder/Safari peuvent rester des scénarios de surface, mais les scénarios F/G doivent utiliser des fixtures randomisées pour empêcher une recipe de passer le test.

### Conditions de run

- warm et cold cache séparés ;
- 30 runs minimum A–D/F/G/H ; 100 pour E vision ;
- order randomisé ;
- device context version et CUA driver health enregistrés ;
- activité utilisateur/lock state capturés juste avant gate ;
- timeout explicite et failures conservées ;
- aucune relance silencieuse supprimée des métriques.

### Preuve de réussite

`success=true` exige le dernier événement `postcondition.satisfied=true` **et** une trace `route` non vide respectant l'ordre attendu. Le transport, la réponse LLM ou l'absence de contradiction ne suffisent jamais.

Exemples de postconditions déterministes :

- A/B : PID + fenêtre existante du bundle attendu ;
- C : window location URL/path = Downloads ;
- D/E/F/G : état fixture lu par canal déterministe ;
- H : état fixture correct **et** aucun événement focus non averti.

### Latence

- total : premier token/requête orchestration → postcondition ;
- sous-phases : LLM, resolve device, observe, Web, dispatch, locator, verify ;
- p50/p95/p99 par scénario ;
- réseau VPS↔Mac séparé lorsqu'il est instrumentable.

### AX et tokens

- `ax_chars` mesuré avant envoi au LLM ;
- `ax_tokens` issu du tokenizer provider quand disponible, sinon estimation marquée ;
- input/output tokens pris dans les usages API réels ;
- payload brut non conservé dans les rapports publics s'il contient des données utilisateur.

### User disruption

- focus change et real mouse movement doivent venir du driver/OS, pas des intentions ;
- l'overlay agent cursor n'est pas compté comme déplacement de souris réelle ;
- warning est compté lorsque le message a été délivré et son receipt runtime minté ;
- H échoue si focus change > 0 et warnings = 0.

## Comparaison V1 / V2

Rapporter, par scénario et globalement :

```text
Δ success (points)
Δ latency (%)
Δ LLM/tool/Web calls
Δ screenshots/vision
Δ AX chars/tokens
Δ total tokens
Δ focus/mouse/warnings
Δ retries
```

Ne jamais agréger une hausse de success avec une violation de policy : toute violation L1/L2 est un gate failure distinct, même si la tâche “réussit”.
