---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior. 4-phase root cause investigation — NO fixes without understanding the problem first.
version: 1.1.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
metadata:
  hermes:
    tags: [debugging, troubleshooting, problem-solving, root-cause, investigation]
    related_skills: [test-driven-development, writing-plans, subagent-driven-development]
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Someone wants it fixed NOW (systematic is faster than thrashing)

## The Four Phases

You MUST complete each phase before proceeding to the next.

---

## Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

### 1. Read Error Messages Carefully

- Don't skip past errors or warnings
- They often contain the exact solution
- Read stack traces completely
- Note line numbers, file paths, error codes

**Action:** Use `read_file` on the relevant source files. Use `search_files` to find the error string in the codebase.

### 2. Reproduce Consistently

- Can you trigger it reliably?
- What are the exact steps?
- Does it happen every time?
- If not reproducible → gather more data, don't guess

**Action:** Use the `terminal` tool to run the failing test or trigger the bug:

```bash
# Run specific failing test
pytest tests/test_module.py::test_name -v

# Run with verbose output
pytest tests/test_module.py -v --tb=long
```

### 3. Check Recent Changes

- What changed that could cause this?
- Git diff, recent commits
- New dependencies, config changes

**Action:**

```bash
# Recent commits
git log --oneline -10

# Uncommitted changes
git diff

# Changes in specific file
git log -p --follow src/problematic_file.py | head -100
```

### 4. Gather Evidence in Multi-Component Systems

**WHEN system has multiple components (API → service → database, CI → build → deploy):**

**BEFORE proposing fixes, add diagnostic instrumentation:**

For EACH component boundary:
- Log what data enters the component
- Log what data exits the component
- Verify environment/config propagation
- Check state at each layer

Run once to gather evidence showing WHERE it breaks.
THEN analyze evidence to identify the failing component.
THEN investigate that specific component.

### 5. Trace Data Flow

**WHEN error is deep in the call stack:**

- Where does the bad value originate?
- What called this function with the bad value?
- Keep tracing upstream until you find the source
- Fix at the source, not at the symptom

**Action:** Use `search_files` to trace references:

```python
# Find where the function is called
search_files("function_name(", path="src/", file_glob="*.py")

# Find where the variable is set
search_files("variable_name\\s*=", path="src/", file_glob="*.py")
```

### Phase 1 Completion Checklist

- [ ] Error messages fully read and understood
- [ ] Issue reproduced consistently
- [ ] Recent changes identified and reviewed
- [ ] Evidence gathered (logs, state, data flow)
- [ ] Problem isolated to specific component/code
- [ ] Root cause hypothesis formed

**STOP:** Do not proceed to Phase 2 until you understand WHY it's happening.

---

## Phase 2: Pattern Analysis

**Find the pattern before fixing:**

### 1. Find Working Examples

- Locate similar working code in the same codebase
- What works that's similar to what's broken?

**Action:** Use `search_files` to find comparable patterns:

```python
search_files("similar_pattern", path="src/", file_glob="*.py")
```

### 2. Compare Against References

- If implementing a pattern, read the reference implementation COMPLETELY
- Don't skim — read every line
- Understand the pattern fully before applying

### 3. Identify Differences

- What's different between working and broken?
- List every difference, however small
- Don't assume "that can't matter"

### 4. Understand Dependencies

- What other components does this need?
- What settings, config, environment?
- What assumptions does it make?

---

## Phase 3: Hypothesis and Testing

**Scientific method:**

### 1. Form a Single Hypothesis

- State clearly: "I think X is the root cause because Y"
- Write it down
- Be specific, not vague

### 2. Test Minimally

- Make the SMALLEST possible change to test the hypothesis
- One variable at a time
- Don't fix multiple things at once

### 3. Verify Before Continuing

- Did it work? → Phase 4
- Didn't work? → Form NEW hypothesis
- DON'T add more fixes on top

### 4. When You Don't Know

- Say "I don't understand X"
- Don't pretend to know
- Ask the user for help
- Research more

---

## Phase 4: Implementation

**Fix the root cause, not the symptom:**

### 1. Create Failing Test Case

- Simplest possible reproduction
- Automated test if possible
- MUST have before fixing
- Use the `test-driven-development` skill

### 2. Implement Single Fix

- Address the root cause identified
- ONE change at a time
- No "while I'm here" improvements
- No bundled refactoring

### 3. Verify Fix

```bash
# Run the specific regression test
pytest tests/test_module.py::test_regression -v

# Run full suite — no regressions
pytest tests/ -q
```

### 4. If Fix Doesn't Work — The Rule of Three

- **STOP.**
- Count: How many fixes have you tried?
- If < 3: Return to Phase 1, re-analyze with new information
- **If ≥ 3: STOP and question the architecture (step 5 below)**
- DON'T attempt Fix #4 without architectural discussion

### 5. If 3+ Fixes Failed: Question Architecture

**Pattern indicating an architectural problem:**
- Each fix reveals new shared state/coupling in a different place
- Fixes require "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

**STOP and question fundamentals:**
- Is this pattern fundamentally sound?
- Are we "sticking with it through sheer inertia"?
- Should we refactor the architecture vs. continue fixing symptoms?

**Discuss with the user before attempting more fixes.**

This is NOT a failed hypothesis — this is a wrong architecture.

---

## Agent Loop Prevention Branch

The former `agent-loop-prevention` skill is absorbed as `references/agent-loop-prevention.md`. Use it as the repeated-tool-failure branch of systematic debugging.

Class-level rule: when the same tool, same error class, or same empty-result pattern repeats three times, stop trying fixes and switch to diagnosis. Classify the error (transient, rate limit, config missing, credential invalid, path missing, schema/argument error), inspect the authoritative source, and report the blocker instead of retrying. Repeated retries on non-transient failures are debugging failures, not persistence.

## Red Flags — STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before tracing data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals a new problem in a different place**

**ALL of these mean: STOP. Return to Phase 1.**

**If 3+ fixes failed:** Question the architecture (Phase 4 step 5).

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question the pattern, don't fix again. |

## Specialized Debugging References

- **`references/systemd-crash-loop-diagnosis.md`** — Server unresponsive / SSH timeout caused by systemd services crash-looping with missing WorkingDirectory. Diagnostic checklist + fix procedure.

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence, trace data flow | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare, identify differences | Know what's different |
| **3. Hypothesis** | Form theory, test minimally, one variable at a time | Confirmed or new hypothesis |
| **4. Implementation** | Create regression test, fix root cause, verify | Bug resolved, all tests pass |

## Hermes Agent Integration

### Investigation Tools

Use these Hermes tools during Phase 1:

- **`search_files`** — Find error strings, trace function calls, locate patterns
- **`read_file`** — Read source code with line numbers for precise analysis
- **`terminal`** — Run tests, check git history, reproduce bugs
- **`web_search`/`web_extract`** — Research error messages, library docs

### Web UI / Modal Troubleshooting

For front-end issues like "button does nothing" or "modal won't open":

1. Verify the live HTML/CSS/JS are actually deployed, not just local copies.
2. Reproduce in a real browser when possible.
3. If browser automation is unavailable, use Playwright headless via `terminal` to click the element, inspect visibility, and capture a screenshot.
4. Validate event binding in isolation with a minimal DOM/JS simulation when needed.
5. Inspect a screenshot before changing code; it often reveals z-index, overlay, contrast, and layout problems faster than logs.
6. For stateful UIs, expose explicit `open...()` / `close...()` helpers and wire overlay click + Escape key close behavior.

### With delegate_task

For complex multi-component debugging, dispatch investigation subagents:

```python
delegate_task(
    goal="Investigate why [specific test/behavior] fails",
    context="""
    Follow systematic-debugging skill:
    1. Read the error message carefully
    2. Reproduce the issue
    3. Trace the data flow to find root cause
    4. Report findings — do NOT fix yet

    Error: [paste full error]
    File: [path to failing code]
    Test command: [exact command]
    """,
    toolsets=['terminal', 'file']
)
```

### With test-driven-development

When fixing bugs:
1. Write a test that reproduces the bug (RED)
2. Debug systematically to find root cause
3. Fix the root cause (GREEN)
4. The test proves the fix and prevents regression

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common

**No shortcuts. No guessing. Systematic always wins.**

## Diagnostiquer une alerte d’egress du guardian Browse

1. Pars de `cd /walter/capabilities/browse`. Lis `README.md`, `guardian/playbook.json`, `guardian/check` et `network/exit-local/bin/walter-exit-local`. Repère où le résultat de la mesure devient une alerte : `walter-exit-local probe` mesure la sortie, `guardian/check` attribue la gravité. Évite les recherches récursives dans tout `/walter` : elles ont expiré alors que les preuves étaient dans le journal des incidents et les logs des services.
2. Relève l’horodatage et les preuves de l’incident avec `grep -F 'France exit' /user/Lucas/state/guardians/incidents.jsonl | tail -20`. Distingue une IP interdite effectivement observée d’un résultat sans IP ni pays (`chromium_exit_country: null` seul ne prouve ni fuite ni fermeture). Compare la même fenêtre horaire dans `/var/log/walter-exit-default.log`, `/var/log/walter-exit-local.log` et `journalctl -u walter-exit-mac --since "$DEBUT" --until "$FIN" --no-pager -o short-iso`, en vérifiant les fuseaux. Le Mac peut dormir ou quitter le tunnel normalement : la sortie locale se ferme et le sélecteur doit prendre le relais via WireGuard. Une bascule au moment de l’alerte étaye une mesure interrompue ; elle ne prouve pas une fuite.
3. Compare `walter-exit-default status`, `walter-exit-local status` et `walter-exit-local probe` (garde son JSON **et** son code retour). Pour isoler la mesure de Chromium sans changer le routage, répète `curl -sS --max-time 12 -x socks5h://127.0.0.1:1083 -w '\nHTTP %{http_code} en %{time_total}s\n' https://ipinfo.io/json` ; relève aussi le code retour de curl. Ne teste pas en connexion directe : tu mesurerais une autre sortie. Compare l’IP observée à celle attendue pour l’instance, pas seulement le pays. Dans `walter-exit-local status`, un ancien champ `ip` peut subsister avec `route: closed` : consulte `checked_ip_at` avant de l’interpréter comme une observation actuelle.
4. Si le défaut est dans la sonde, garde trois résultats distincts : IP autorisée observée, IP inattendue observée (violation critique), aucune réponse (`chromium_exit_unanswered`, diagnostic non critique). Ne transforme pas une absence de réponse en preuve que la sortie est saine. Borne les nouvelles tentatives et vérifie que le cumul reste sous le délai du guardian ; garde les sondes auxiliaires à un seul essai si nécessaire. Ne change ni le routage ni la fermeture par défaut pour faire taire l’alerte.
5. Teste au minimum les trois résultats avec `python3 -m pytest network/exit-local/tests -q`. Si tu ajoutes un argument nommé à `exit_ip`, adapte aussi les doubles de test qui le remplacent. Si le service a changé, exécute `systemctl restart walter-exit-local` puis `systemctl is-active walter-exit-local`. Relance `walter-exit-local probe` et `timeout 230 python3 guardian/check` ; vérifie le JSON, la gravité et les codes retour avant de conclure. Pour la suite large, isole l’état avec `WALTER_BROWSE_STATE_DIR=$(mktemp -d) timeout 900 python3 -m pytest runtime/test_*.py tests network -q`. Si seul le test de replay de l’extracteur échoue faute de Scrapling, relance-le avec `~/.venv/scrapling/bin/python -m pytest runtime/test_universal_extractor.py -q -k replay_fetches` et rapporte son résultat séparément.
