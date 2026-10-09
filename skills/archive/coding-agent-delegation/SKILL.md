---
name: coding-agent-delegation
description: "Use for safely delegating coding work to CLI agents."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [coding-agents, delegation, claude, codex, opencode, review, automation]
---

# Coding Agent Delegation

Use this class-level skill when Hermes delegates implementation, refactoring, code review, or exploratory coding to an external CLI worker. Select the provider branch only after defining the task boundary and verification contract.

## Always-on delegation rules

- Inspect the repository, clean/dirty state, active branch or worktree, tool availability, auth mode, and intended working directory before launching a worker.
- Give one bounded objective with acceptance criteria, explicit allowed paths/tools, a test command, and a stop condition; vague prompts create uncontrolled edits.
- Prefer non-interactive one-shot commands for bounded work and PTY-backed background sessions only when the worker needs multiple turns or interactive input.
- Use an isolated worktree or directory for parallel or risky tasks, because shared working trees cause collisions and corrupt review evidence.
- Set turn, time, permission, and spend limits; do not grant dangerous bypass flags unless the scope and recovery path are explicit.
- Monitor long-running sessions, answer only expected prompts, and clean up sessions after completion; do not kill a slow worker without checking its state.
- Review the complete diff, run focused tests and the repository's broader required checks, and report files changed, commands run, results, and remaining risk before claiming completion.
- Keep the external worker's result separate from Hermes' own verification; a worker's success message is not evidence that the repository is correct.

## Provider selection

### Claude Code

- Use `claude -p` for bounded automation and structured output; use an interactive tmux session for multi-turn work, slash commands, or human decisions.
- Set `workdir`, `--max-turns`, and `--allowedTools`/`--disallowedTools`; use `--output-format json` when machine-readable session, cost, and stop metadata matters.
- Handle first-use workspace trust explicitly and never accept a dangerous permission-bypass dialog by pressing the default choice blindly.
- Use `--bare` only when hooks, plugins, MCP discovery, and project memory are intentionally excluded; it still needs API-key-compatible auth.
- Resume only in the same project context or with an explicit session ID, and use worktrees for isolated PR or feature work.

### Codex

- Run Codex inside a Git repository with `pty=true`; use `codex exec` for one-shot tasks and a monitored background process for long work.
- Prefer `--sandbox workspace-write` for normal implementation; if a Hermes service cannot create the sandbox, use the narrowest available alternative and compensate with explicit workdir, clean status, diff review, tests, and approval before commit.
- Treat OAuth credentials and API keys as separate auth paths; missing `OPENAI_API_KEY` alone does not prove the CLI is unauthenticated.
- Use separate worktrees for parallel issue fixes and remove them only after the resulting branches and artifacts are accounted for.

### OpenCode

- Verify the resolved binary and provider auth because shell PATH and Hermes service PATH can select different installations.
- Use `opencode run` for bounded work and a PTY-backed background TUI for iterative sessions; exit with Ctrl-C or process termination, never an unsupported `/exit` command.
- Keep one repository/workdir per session and inspect logs before killing a seemingly stuck process.
- Match provider wire protocol to the model: OpenAI-compatible models use chat completions, while designated Qwen/MiniMax OpenCode routes use Anthropic messages; a format mismatch is not a generic auth failure.
- When an Anthropic-compatible OpenCode gateway rejects a request because the SDK sends both `x-api-key` and `Authorization: Bearer`, isolate the endpoint client and remove the incompatible header rather than rotating valid credentials.
- Treat base-URL version segments and TLS/Cloudflare differences as provider-contract questions; verify the actual request path and transport before changing model IDs.

## Review and handoff

1. Capture the pre-launch repository state and task contract.
2. Launch the smallest safe provider command.
3. Observe or poll the worker until it exits, asks for input, or reaches the stop condition.
4. Read the complete diff and worker output; separate claimed work from observed changes.
5. Run the focused test, relevant lint/type/build checks, and any acceptance-specific command.
6. Preserve or revert only the worker's scoped changes, then report the exact outcome and unverified gates.

Never commit, push, merge, or post a PR solely because an external worker says it finished; those are separate side effects requiring their own authorization and read-back.
