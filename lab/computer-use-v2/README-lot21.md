# Computer Use V2 — Lot 2.1 Shadow Integration

Sidecar macOS read-only d'Adaptive Universal Operator, isolé du V1 CLOSED et sans appel Computer Use supplémentaire.

## Lire dans cet ordre

1. `docs/SHADOW_LOT21.md` — branchement, sources, métriques, A–H, policy et gaps.
2. `docs/ARCHITECTURE.md` — target V2 et interfaces contractuelles du Lot 2.0.
3. `docs/BENCHMARK.md` — discipline anti-fausse-preuve et scénarios.
4. `docs/MIGRATION.md` — lots suivants et gates.
5. `docs/REVIEW.md` — revue du socle contractuel.

## Composants Lot 2.1

- `shadow_replay.py` — corrélation `state.db` en SQLite `mode=ro` ;
- `shadow_sidecar.py` / `shadow_spool.py` — observation hors processus et spool idempotent ;
- `shadow_observation.py` — conversion/compaction V1→V2 ;
- `shadow_policy.py` — prédiction L0/L1/L2 non appliquée ;
- `macos_shadow.py` / `shadow_context.py` — DeviceContext et présence read-only ;
- `shadow_benchmark.py` / `shadow_report.py` — percentiles et gates ;
- `shadow_sanitize.py` — artefact métrique partageable par whitelist ;
- `deploy/computer-use-v2-shadow.*` — service/timer indépendants de V1.

## Vérifier le bundle

```bash
python3 -m pytest -q -p no:cacheprovider
sha256sum -c SHA256SUMS
```

Le benchmark live final est livré sous forme assainie dans `artifacts/shadow-live/benchmark-report.sanitized.json`. Le bundle exclut volontairement le spool AX privé, le cache DeviceContext réel, le probe live brut, les call IDs et la route Tailscale. Rejouer le benchmark live exige les sources privées locales et reste une opération d'audit explicite ; les tests du bundle n'appellent ni Mac, ni backend, ni réseau.
