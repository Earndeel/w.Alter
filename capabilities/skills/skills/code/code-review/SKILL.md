---
name: code-review
description: "Code review guidelines and pre-commit verification pipeline — security scan, quality gates, independent reviewer subagent, auto-fix loop."
version: 2.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, security, verification, quality, pre-commit, auto-fix]
    related_skills: [subagent-driven-development, writing-plans, test-driven-development, github-code-review]
---

## When to Use

- User asks for a code review, PR review, or code audit
- Reviewing pull requests, diffs, or merge requests
- Auditing existing code for security or quality issues
- Provider/API migration reviews

## Pitfalls

- **Don't just list issues**: Explain *why* something is a problem and offer solutions
- **Security first**: Always check for hardcoded secrets, SQL injection, path traversal before style issues
- **Context matters**: A pattern that's bad in one context may be acceptable in another — consider the codebase conventions
- **Provider migrations**: Audit both UI and server-side enforcement — clients can't override via hidden JSON fields

---

# Code Review Skill

Use this skill when reviewing code changes, pull requests, or auditing existing code.

## Review Checklist

### 1. Security First
- [ ] No hardcoded secrets, API keys, or credentials
- [ ] Input validation on all user-provided data
- [ ] SQL queries use parameterized statements (no string concatenation)
- [ ] File operations validate paths (no path traversal)
- [ ] Authentication/authorization checks present where needed

### 2. Error Handling
- [ ] All external calls (API, DB, file) have try/catch
- [ ] Errors are logged with context (but no sensitive data)
- [ ] User-facing errors are helpful but don't leak internals
- [ ] Resources are cleaned up in finally blocks or context managers

### 3. Code Quality
- [ ] Functions do one thing and are reasonably sized (<50 lines ideal)
- [ ] Variable names are descriptive (no single letters except loops)
- [ ] No commented-out code left behind
- [ ] Complex logic has explanatory comments
- [ ] No duplicate code (DRY principle)

### 4. Testing Considerations
- [ ] Edge cases handled (empty inputs, nulls, boundaries)
- [ ] Happy path and error paths both work
- [ ] New code has corresponding tests (if test suite exists)

## Extra Checklist: Provider/API Migrations

When reviewing a provider migration, audit both UI and server-side enforcement:
- [ ] Build/import the exact modules touched by the migration before reviewing behavior.
- [ ] Search for old provider symbols across runtime routes, webhook handlers, tests, docs, payload builders, env types, and admin/portal UI.
- [ ] Verify server-side policy, not just UI removal: clients cannot override provider/model via hidden JSON fields.
- [ ] Check async callback contract changes (`taskId` vs `request_id`, completion URL shape, signed webhook path).
- [ ] Check BYOK actually uses the tenant key instead of silently falling back to platform secrets.

## Review Response Format

When providing review feedback, structure it as:

```
## Summary
[1-2 sentence overall assessment]

## Critical Issues (Must Fix)
- Issue 1: [description + suggested fix]
- Issue 2: ...

## Suggestions (Nice to Have)
- Suggestion 1: [description]

## Questions
- [Any clarifying questions about intent]
```

## Common Patterns to Flag

### Python
```python
# Bad: SQL injection risk
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# Good: Parameterized query
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

### JavaScript
```javascript
// Bad: XSS risk
element.innerHTML = userInput;

// Good: Safe text content
element.textContent = userInput;
```

## Pre-Commit Verification Pipeline

Automated verification before code lands. **Core principle:** No agent should verify its own work. Fresh context finds what you miss.

### When to Use

- After implementing a feature or bug fix, before `git commit` or `git push`
- When user says "commit", "push", "ship", "done", "verify", or "review before merge"
- After completing a task with 2+ file edits in a git repo
- After each task in subagent-driven-development (the two-stage review)

**Skip for:** documentation-only changes, pure config tweaks, or when user says "skip verification".

**This skill vs github-code-review:** This skill verifies YOUR changes before committing. `github-code-review` reviews OTHER people's PRs on GitHub with inline comments.

### Step 1 — Get the diff

```bash
git diff --cached
```

If empty, try `git diff` then `git diff HEAD~1 HEAD`. If diff exceeds 15,000 characters, split by file.

### Step 2 — Static security scan

Scan added lines only:

```bash
# Hardcoded secrets
git diff --cached | grep "^+" | grep -iE "(api_key|secret|password|token|passwd)\s*=\s*['\"][^'\"]{6,}['\"]"

# Shell injection
git diff --cached | grep "^+" | grep -E "os\.system\(|subprocess.*shell=True"

# Dangerous eval/exec
git diff --cached | grep "^+" | grep -E "\beval\(|\bexec\("

# SQL injection
git diff --cached | grep "^+" | grep -E "execute\(f\"|\.format\(.*SELECT|\.format\(.*INSERT"
```

### Step 3 — Baseline tests and linting

Detect project language and run appropriate tools. Capture failure count BEFORE changes as baseline. Only NEW failures block the commit.

### Step 4 — Self-review checklist

- [ ] No hardcoded secrets, API keys, or credentials
- [ ] Input validation on user-provided data
- [ ] SQL queries use parameterized statements
- [ ] File operations validate paths (no traversal)
- [ ] External calls have error handling (try/catch)
- [ ] No debug print/console.log left behind
- [ ] No commented-out code
- [ ] New code has tests (if test suite exists)

### Step 5 — Independent reviewer subagent

Call `delegate_task` — it is NOT available inside execute_code or scripts.

The reviewer gets ONLY the diff and static scan results. No shared context with the implementer. Fail-closed: unparseable response = fail.

```python
delegate_task(
    goal="""You are an independent code reviewer. Review the git diff and return ONLY valid JSON.

FAIL-CLOSED RULES:
- security_concerns non-empty -> passed must be false
- logic_errors non-empty -> passed must be false
- Only set passed=true when BOTH lists are empty

<static_scan_results>[INSERT FINDINGS]</static_scan_results>
<code_changes>[INSERT GIT DIFF]</code_changes>

Return ONLY this JSON:
{
  "passed": true or false,
  "security_concerns": [],
  "logic_errors": [],
  "suggestions": [],
  "summary": "one sentence verdict"
}""",
    context="Independent code review. Return only JSON verdict.",
    toolsets=["terminal"]
)
```

### Step 6 — Evaluate results

**All passed:** Proceed to commit.
**Any failures:** Report what failed, then proceed to Step 7 (auto-fix).

### Step 7 — Auto-fix loop (max 2 cycles)

Spawn a THIRD agent context — not you (the implementer), not the reviewer. It fixes ONLY the reported issues. After fix, re-run Steps 1-6.

### Step 8 — Commit

```bash
git add -A && git commit -m "[verified] <description>"
```

The `[verified]` prefix indicates an independent reviewer approved this change.

### Integration

- **subagent-driven-development:** Run this after EACH task as the quality gate.
- **test-driven-development:** Verifies TDD discipline was followed.
- **writing-plans:** Validates implementation matches the plan requirements.

### Pitfalls

- **Empty diff** — check `git status`, tell user nothing to verify
- **Large diff (>15k chars)** — split by file, review each separately
- **delegate_task returns non-JSON** — retry once with stricter prompt, then treat as FAIL
- **No test framework found** — skip regression check, reviewer verdict still runs
- **Lint tools not installed** — skip that check silently, don't fail

## Review deployed-in-place W.Alter modules without changing production

- Treat `/walter` module repositories as live deployments, not disposable checkouts. Read the review package, design, plan and progress ledger first; identify the baseline and reviewed HEAD separately for every affected repository. Do not checkout, reset, restart services, run migrations or trigger a backfill during a read-only review.
- Compare committed code with deployed artifacts. For walter-devboard, run:
  ```bash
  cd /walter/ops
  git log --oneline <baseline>..HEAD
  git diff --stat <baseline>..HEAD
  cd /walter/ops/devboard
  for u in bus.service docs.service due.service due.timer web.service; do
    diff -u "ops/walter-devboard-$u" "/etc/systemd/system/walter-devboard-$u"
  done
  ls -l /usr/local/bin/walter-devboard
  cat bin/walter-devboard
  ```
  Record deployment drift rather than assuming a passing repository test validates installed units or wrappers.
- Inspect test fixtures before executing tests against a live module. For devboard, inspect `/walter/ops/devboard/tests/conftest.py`: its database fixture is intended to create and drop a throwaway database on the memory test server at `127.0.0.1:5440`, not production at port `5433`. Verify environment overrides preserve that separation. Run tests while retaining their actual exit status:
  ```bash
  cd /walter/ops/devboard
  set -o pipefail
  timeout 600 walter-python -m pytest -q 2>&1 | tail -15
  cd web
  timeout 300 npm test 2>&1 | tail -15
  ```
  Do not report the exit status of `tail` or `grep` as the test command's status.
- Enforce read-only database access explicitly, before the first query. Use the locally configured connection without copying credentials into reports:
  ```python
  import psycopg
  c = psycopg.connect("postgresql://walter@127.0.0.1:5433/walter")
  c.read_only = True
  ```
  Inspect live state as well as tests: `devboard.sessions` grouped by runtime, eligibility and state; `devboard.cards` grouped by status and activity age; and `bus.dead` filtered to `consumer='devboard'`. A working HTTP endpoint does not prove ingestion, retries or backfill are healthy.
- Check the installed CLI from outside the repository, then probe the deployed read-only API:
  ```bash
  cd /tmp
  walter-devboard status
  for p in summary inbox 'cards?group=status' 'cards?group=module' today decisions vision live docs; do
    curl -s -o /dev/null -m 20 -w "$p %{http_code} %{time_total}s %{size_download}B\n" "http://100.91.35.121:3093/api/$p"
  done
  ```
  Inspect document path resolution in code and probe traversal attempts without printing sensitive file contents; a 404 alone is not a complete authorization audit.
- Audit model-produced claims against their stored sources, not only JSON schemas or mocked model responses. For devboard, join session evidence to logs with `walter_logs.events.session_id = devboard.card_evidence.source_ref` and `walter_logs.events.seq = devboard.card_evidence.seq`, restricting evidence to `kind='session'`. Check source existence, speaker/event type, quotation fidelity, and whether approval or decision claims are actually supported.
- Trace subscription-only routing end to end: configured Router poste, selected provider, freshness and threshold of subscription meters, exact gateway model/provider request, and gateway error handling. Distinguish a burst rate limit from exhausted subscription quota; check that retries cannot silently select a paid route. Do not make paid model calls merely to verify this policy.
- Separate report evidence into code findings, test results and timestamped live observations. Distinguish ongoing backfill from permanent missing coverage. Remove temporary review scripts after use, and recommend operational interventions rather than executing them without authorization.
