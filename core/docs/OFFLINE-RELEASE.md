# Offline release and staged installation

This installs reviewed module source and can prepare Python environments from
local wheels. It is separate from `walter_memory.restore_drill`, which restores
protected backups and data. It neither starts services nor claims a working clean
VM merely because files were installed.

Python API (`walter_platform.release`):

- `build(destination, apply=False, root='/', catalog=None, wheelhouse=None, include_dependencies=True)`
- `inspect(bundle)`
- `install(bundle, root, apply=False, backup_root=None)`
- `environment_plan(bundle, root, python=..., environments=None)`
- `install_environments(bundle, root, python=..., apply=False, environments=None)`
- `rollback(backup, apply=False)` for source/config transactions.

All write operations preview by default. `root` must be a dedicated staging
root; `/`, `/opt`, `/root`, `/etc`, `/usr`, `/var` and `/walter` are refused. Paths under that
root preserve the current declared absolute module layout (`root/opt/...` or `root/walter/...`).
The allowlist is keyed by stable module ids, so it follows a declared migration
without introducing a second list of physical source roots. The bundle
contains a reviewed source allowlist (`modules/release-sources.json`), owner
contracts, per-file hashes/modes, Git commit/dirty state, package versions, lockfile
inventory, local wheel hashes/tags and explicit runtime prerequisites. Unversioned
modules are identified as snapshots. No Git history or dependency download occurs.

Credentials, auth files, data stores, sessions, model weights, skills content,
personal Soul sources, caches and virtualenvs are excluded. The two Soul anchors
are explicitly restoration prerequisites. Account/device/router configuration
outside the reviewed allowlist must be restored separately. Three credential
masking test files with token-shaped synthetic literals are omitted rather than
bypassing the source scanner. The scanner catches common literal credentials;
it is not a general proof that arbitrary source text contains no secret. The
local release directory is private (0700), and no external publication is made.
Systemd unit source may be included; it is never enabled or started.

The full bundle is checked before writes: bounded text files, normalized paths,
no symlink traversal, duplicate rejection, hashes, owner-contract agreement,
anchors and compiled embedded catalogue. The bytes captured for the transaction
are hashed again; foreign existing files cause refusal. Owned source updates
preserve rollback preimages and original permissions. A repeated install of the
same bundle changes nothing. Human edits, including permission changes, block
rollback; removing a file from a later release does not delete the earlier copy.
The receipt is an integrity record, not a signature establishing publisher trust.

Environment preparation is a second explicit step. It requires an appropriate
Python interpreter and every exact package version as a compatible, hash-checked
local wheel. Pip uses `--no-index --no-deps --only-binary=:all: --require-hashes`;
no source package build or package download is allowed. For mixed Python versions, an explicit list of logical environment paths can be
selected per interpreter; unselected paths are reported and never counted as
ready. Foreign environments are never overwritten. Failed new environments are quarantined. Repeated creation
checks the receipt and installed package versions; it does not attest every
installed package byte against later tampering. Environment preparation has no
automatic rollback after successful creation; source rollback leaves environments
and user data untouched. Use only trusted local wheels and interpreters.

Missing Node/harness distributions, system libraries, PostgreSQL/extensions,
external services, accounts and data remain explicit prerequisites. No Docker
image or Node cache is invented from a dependency list. An inventory without the
corresponding artifacts is not a fully reproducible offline environment.

Validation includes isolated source build/install/rollback, CRLF and modes,
credential/data sentinels, changed source after validation, missing anchors,
foreign paths, symlinks, wheelhouse extras, incompatible wheel tags and URL
requirement injection. A real synthetic wheel is installed into a new virtualenv
with no index; its import path is proved to be inside the staging root. The
shared stdlib Context module can additionally run its acceptance corpus from the
installed staging tree with an isolated Python `sys.path`; invoking its original
absolute-path shell wrapper alone would accidentally exercise production.
