# walter-lab

Measured experiments on the system. Lab compares variants on the shared end-to-end bench (`walter-scenario`),
interleaves their runs and evaluates the decision rule written in advance. It can conclude that nothing should
change. Lab records proposals and never applies them. Guardian checks operation; Curator organises skills.

## Interfaces and dependencies

* `walter-lab list`
* `walter-lab run <experiment> [--repeats N]`
* `walter-lab history <experiment>`
* `walter-lab sandbox probe`
* `walter-lab sandbox run --src <approved-checkout> [--image <local-image>] [--timeout 600] -- <command> [args...]`

The Python API is `walter_lab.sandbox.run`; its optional `out_dir` must name a new directory. Existing destinations
are never merged or overwritten. The CLI chooses `@instance/state/lab/sandbox/<time>` for exported results.

Scenario experiments need the public `walter-scenario` command and YAML support in the shared Python runtime.
Sandbox execution needs Linux descriptor APIs and a Docker daemon. Images must already be present locally
(`--pull never`); prefer a reviewed image addressed by immutable digest. The default is `python:3.12-slim`.
No long-running Lab service is required. A dependency failure is reported by the CLI and does not apply a change.

## Experiment protocol and reports

`experiments/<name>.yaml` is Experiment v1: name, hypothesis, scenario, variants, metrics and a decision rule.
The first variant is the baseline. Variants switch environment settings that the scenario already supports.
**Scenario experiments run with the host's existing execution permissions and environment.** They do not invoke
the sandbox automatically. External source code must use the separate sandbox interface.

Reports are written after every trial to `@instance/state/lab/<experiment>/<time>.json`. Completed reports retain
the same protocol as intermediate checkpoints: scenario, metric names, decision rule, variant order, environment
variable names, an SHA-256 fingerprint of the full experiment definition, and a fingerprint of the Lab Python code.
Environment values are deliberately absent from checkpoints and completed metadata. Keep the approved experiment
definition and scenario version with the evidence to reproduce a result; a fingerprint alone cannot reconstruct
them. Scenario results can themselves contain arbitrary text, so scenario authors must avoid emitting secrets.
`history` continues to read older reports that lack protocol metadata; old reports are not rewritten.

## Sandbox boundary

Only the prepared source copy and output directory are mounted. The container has no network, a read-only root,
no extra capabilities, no new privileges, UID/GID 65534, a 256-process limit, default memory/CPU limits of 2 GiB/2,
and a 600-second deadline. Its temporary filesystem is limited to 256 MiB. Host environment variables are not
forwarded; `HOME=/tmp` is set explicitly. Docker's log driver is disabled and client stdout/stderr are drained with
only the last 4000/2000 bytes retained.

The host copier opens every directory and file with `O_NOFOLLOW` relative to pinned directory descriptors. It
rejects symlinks, multiply-linked regular files and special files at both boundaries. It never changes the source
or target of an input link; permissions are set only on newly created destination descriptors. Executable files
remain executable in the disposable source copy. The container cannot replace the root-owned `src`/`out` entries.
After completion or timeout, the container must be confirmed removed before any output is validated and exported.
If removal cannot be confirmed, export is withheld and the work directory is retained rather than touched while
the container might still be running; inspect and remove that container before clearing its work directory.

Default copy limits, independently for input and output, are 256 MiB total, 32 MiB per file, 20,000 visited entries,
and depth 64. The Python API can reduce or raise byte/entry limits. Limits count bytes actually read, including a
growing file. All output is validated even when no export was requested. Invalid output creates no export; failed
exports remove the partial fresh directory. Normal/aborted runs remove their staging directories once the
container is confirmed stopped.

The input omits caches and known credential names: `.git`, `node_modules`, virtual environments, `__pycache__`,
`.env`/`.env.*` and all `*.env` files, `.aws`, `.ssh`, `.gnupg`, `.config`, `.kube`, `.docker`, `.pgpass`, `.netrc`,
common `credentials`/`secrets` filenames and their hidden variants, `auth.json`/`.auth.json`, SSH private key names,
and private-key extensions such as `.pem`/`.key`. Matching is case insensitive for credential names/extensions.
Links and special files are rejected before exclusions are considered. This name filter is a precaution:
**it cannot identify a secret or production data stored under an arbitrary name. Approve and sanitise the source
tree and image before execution.**

## Limits and verification

The container shares the host kernel; this is not a VM. The writable `/work` bind does **not** have a filesystem
quota during execution: copy limits bound input and export, not the bytes the candidate can create before exit.
Host disk exhaustion therefore remains possible, even though process output and Docker logs are bounded. Do not
use this backend for candidates that require a hard disk quota until a quota-enforced backend is available.
Mutable source files are not a point-in-time snapshot. There is no networked mode or dependency installation
mode. The external-source scout and runtime-neutral runtime comparison remain unimplemented.

Run `walter-lab sandbox probe` after a Docker/backend change; a nonzero exit or timeout fails the probe. It checks
the actual UID, visible host directories, environment, root filesystem writes and network/host-service access.
It does not prove resistance to kernel exploits, detect every secret or certify disk quotas. Unit regressions mock
Docker and cover host-side copies, path replacement, limits, credential exclusions, stopping and exported results:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. walter-python -m pytest -q -p no:cacheprovider tests
```

See `docs/CORRECTIONS-2026-10-29.md` for the boundary defects, regression evidence and remaining qualification.
