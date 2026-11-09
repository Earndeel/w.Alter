# Walter shared capabilities

| | |
|---|---|
| **Rôle** | Exposer les capacités Walter aux harnesses (serveur MCP `walter`, hooks, raccordements) et valider le registre des modules (`walter_platform`, `walter check`). Héberge le futur moteur unique ([engine/](engine/README.md)). |
| **Propriétaire** | walter-core (`/walter/core`). |
| **État** | **active** (constat du 09/11/2026) : serveur MCP (stdio), hooks des runtimes, `walter-standby.timer`. Moteur : lot E0 fait, lot E1 en cours. |
| **Ne fait pas** | Posséder les données d'un autre module. La boucle d'exécution et les permissions des runtimes actuels (Hermes, DSH, Codex, Claude Code) restent les leurs. |
| **Contrats** | [contracts/core.json](contracts/core.json), [contracts/schemas/](contracts/schemas/), [modules/registry.json](modules/registry.json) ; brouillons du moteur dans [engine/contracts/](engine/contracts/). |

Walter owns reusable capabilities and their data; Hermes, DSH, Codex and Claude Code own their execution loops and permission gates. Optional modules load only when called, so one missing module does not prevent memory or skills from starting.

`modules/registry.json` declares 17 logical modules: source boundaries, interfaces, owned data, dependencies, backup paths, per-harness bindings and explicit limits. `walter_platform` validates this registry without importing a harness. The encrypted backup reads the same declared paths and fails if required anchors disappear.

## Commands

- `walter modules`: contracts and interfaces, not a health certification.
- `walter check`: required files and static forbidden imports in declared shared cores.
- `walter status`: installation plus observed systemd service states (no paid requests, desktop control or secret retrieval).
- `walter harness check codex|claude-code|dsh|hermes`: actual configuration, kept native features and independent bindings. Configuration is distinct from already loaded processes.
- `walter harness attach codex|claude-code|dsh [--home PATH]`: preview common MCP attachment. `--apply` backs up and writes atomically; identical state is a no-op, conflicting custom Walter configuration is refused. This installs the MCP connection only, not a new runtime, tokens, model provider or context engine. Existing full compositions remain separately managed and verified.
- `walter backup-paths`: declared module paths for offsite coverage.
- `walter-guardians check|status|list`: declared watchdogs, strict incident validation and persisted notification retries; see [GUARDIANS.md](GUARDIANS.md).
- `walter-scenario run e2e-minimal --json`: recorded-run acceptance, including successful tasks and two distinct sourced JSON offers.
- `walter matrix`: distinguishes availability, binding, observed use and current qualification. A qualification requires a matching scenario/source/version attestation and a passing run less than 14 days old.

## Common MCP surface

The existing memory, skills, raw vault, logs, profile and browser-session tools remain. New thin ports in `walter_capabilities.py` add `walter_modules`, `walter_browse`, `secret_search`, `secret_reference`, the Walter Router tools (`walter_route`, `walter_run` — text sub-agent or media generation —, `walter_decide`, `walter_plans`, `walter_web` — a web chat service the owner enabled —; same names as the Hermes plugin, the router's brief joins the server instructions), and `computer_use`. All optional-module errors stay local and omit sensitive exception text. Fresh MCP connections discover the tools; already running clients need reconnection.

Computer Use is local stdio only. Scope ceilings are provisioned in `modules/computer-policy.json`; a tool argument cannot grant authorization. The host MCP approval gate and user's task govern actions, including screen pixels. Unknown client tags receive no scopes. This is not a bypass of a host permission system. Standalone vision is unavailable until a sensor is configured. Hermes keeps its own central approval and human-presence handling through its native adapter.

Secrets returns metadata/references only. Use the local `walter-secret exec` under the calling harness's execution permissions to inject values. The child output is suppressed, including transformed values; there is no generic shell executor or raw password tool in MCP.

Browse uses the same request validation, routing and storage as Hermes. Session names cannot escape the module's state root. Browser authentication is a separate explicit integration in `browser_auth.py`.

## Proof and scope

Unit tests cover independent optional modules, secret nondisclosure, per-call authorization, config preservation/idempotence/races, and source boundaries. Protocol tests perform a fresh MCP handshake, list tools and invoke safe read-only operations. Computer Use validation uses synthetic devices, not Monsieur's desktop. A directory, manifest or passing import test alone does not establish a complete live user journey.

Data currently under `.hermes` can remain at a compatibility path without requiring a running Hermes process. Source migration and adapters are recorded individually; no claim of complete clean-VM restoration is made by the registry.

## Scenario evidence (bench protocol 2, 2026-10-29)

The common metrics still come from the recorded run: this change adds no independent cost ledger. `cost_usd`
is `null` when no model calls are recorded, a call lacks a price, or a value is invalid; explicit recorded zero
remains zero. A complete sum concerns only recorded calls and does not establish completeness of instrumentation.

`e2e-minimal` now requires every recorded task to end successfully and each `walter_run` task to return at least
two distinct offers in its final recorded JSON (`product`, `price_thb`, `volume`, `source_url`, `method`). Missing
price or volume uses the explicit string `inconnu`. Source URLs must occur in a successful Browse result from the
same task. `search_snippet` is accepted and identified; a claimed page read also needs a successful Browse read
of that exact URL with returned content. This validates output structure and provenance; it does not prove the
semantic truth of every product or price. The scenario's qualification scope says so.

New qualifications carry SHA256 of the scenario, bench protocol version, declared module versions, source
inventories and harness configuration. Inventories use each local Git index plus untracked source files not
ignored by Git; current file contents include uncommitted edits. Private state, credentials and environment
folders are excluded; no source content or configuration values enter the qualification file. The sources are
fingerprinted before and after a run. A changed or unavailable inventory prevents qualification. The matrix
rechecks the fingerprint when read. Old qualifications remain in history but are not current proof without an
attestation; they must be replayed. This attests the declared local source inventory and bindings, not external
provider state or the loaded revision of an already running process.

Whole suite in one command (pytest from `walter-python` + the `mcp` package of core's venv, nothing installed):
`bin/walter-core-test` (extra arguments go to pytest). 223 tests on 2026-11-09.

Isolated regression checks (fixtures only; no models, database or real Telegram):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" walter-python -m pytest -q -p no:cacheprovider \
  tests/test_guardians.py tests/test_guardians_regressions.py tests/test_scenario_regressions.py \
  tests/test_matrix_qualified.py tests/test_qualification_regressions.py
```

### Échec d’un enfant DSH dans le banc

Le chemin d’erreur de DSH ne déclenche pas systématiquement Stop. Après la sortie échouée ou le timeout
du processus enfant, le banc retrouve uniquement le run de sa session et appelle le port public Memory
`runs end RUN_ID` avec le statut failed. Il ne synthétise aucun succès ni Stop normal. Le port est idempotent
et ne réécrit pas un run déjà fermé. Le fonctionnement DSH en dehors du banc garde son adaptateur natif ;
un run sans événement de fin reste soumis au mécanisme d’abandon existant.
