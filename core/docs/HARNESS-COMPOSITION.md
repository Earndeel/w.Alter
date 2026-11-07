# Harness composition — 2026-10-18

`walter harness install HOST` previews a declarative composition for `codex`,
`claude-code`, `dsh` or `hermes`. `--home` selects an isolated harness home;
`--apply --backup-root PATH` writes it. This composes supported bindings on an
already provisioned local installation; it does not provision binaries, restore
secrets, start services, authenticate accounts, or claim successful model use.

Definitions live in `compositions/*.json`; `walter matrix` distinguishes local
availability, configured binding, dated historical invocation and full acceptance.
Null usage/qualification means unknown, never inferred from a CLI or config file.
Historical observations are metadata only (runtime/tool/time/count), with no
message contents. They do not prove success or current revision. Codex's nested
exec calls currently obscure per-tool attribution in raw log metadata.

| Host | Managed composition | Kept native / limitations |
|---|---|---|
| Codex | Walter cwd profile, shared skills bridge, MCP, end-of-turn notify | Runtime, model, compaction, approval settings; notify is not pre-prompt injection; global AGENTS.md remains untouched |
| Claude Code | Walter cwd profile, shared skills bridge, MCP, supported lifecycle hooks | Runtime, model, compaction, permissions |
| DSH 0.2.0-rc.2 | Identity, MCP, skills, supported hooks, local Walter model gateway, checkpoint context | Host loop, permissions, token meter, transactions and replay; hook adapter has no SessionEnd/PreCompact event; watcher owns transcript persistence |
| Hermes | Identity, shared plugin adapters, lifecycle hooks, Walter computer backend | Existing model and memory provider preserved; walter-compress kept; new projection not activated |

Codex/Claude identity takes effect only when their session loads the generated
Walter profile cwd. Default profile roots are `/opt/walter-profiles/{codex,claude-code}`;
with `--home`, they are `<home>/walter-profile`. Merely installing does not change
an already running conversation's identity or tools.

Hermes must already have a declared memory provider (`hindsight` or `walter-memory`)
and its corresponding installed plugin. A fresh home without one returns an
unmet prerequisite rather than silently selecting legacy Hindsight. The installer
preserves the configured provider; acceptance and live activation are separate.
The public memory-provider loader selects memory.provider directly and respects
plugins.disabled; it does not require the general plugins.enabled allowlist.
DSH alternative homes reference the existing local credential source by symlink;
no credential value is copied, serialized in a preview, or printed. This is a
same-VM composition, not an export for another host.

Foreign MCP servers, providers, hooks and skills directories are retained.
Conflicting Walter bindings, disabled required adapters, unknown context engines,
foreign notify hooks and edited managed identity sections cause explicit refusal.
YAML comments can change when merging an existing mapping; foreign values survive.
Existing symlinks and modes are preserved. Preimages are stored in a private backup
folder (0700, files 0600), with a transaction manifest containing hashes and paths.

`walter harness rollback BACKUP` previews restoration; `--apply` restores only if
all owned postimages still match. A human edit blocks the entire rollback. An
interrupted transaction can recover its recorded preimages. New empty directories
may remain; host-created profiles, sessions and logs are never removed by rollback.

Validation: 20 new installer tests + 9 platform tests (29 total), including all
four hosts, previews, idempotence, rollback, native settings, secret-free metadata,
foreign configuration, concurrency, symlinks and simulated partial failure.
A fresh isolated DSH home was also read by its actual headless loader with
`--dump-config`: Walter MCP/hooks/context enabled, stock compaction disabled,
Walter default model selected. A second install preview reported no change.
The loader initializes native profile files; this check made no model call.
Full live acceptance of every capability remains separate from this configuration
proof, and the current process must reload its composition before using changes.
