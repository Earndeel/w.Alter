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
