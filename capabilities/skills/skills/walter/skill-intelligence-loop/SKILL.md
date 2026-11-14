---
name: skill-intelligence-loop
description: >
  Automated skill library analysis, gap detection, store search, sub-skill
  decomposition, and curator integration. Runs as a cron job or on-demand
  to continuously improve the user's skill library quality and coverage.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [skills, curator, automation, quality, gaps]
    related_skills: [hermes-agent]
---

# Skill Intelligence Loop

Automated system that audits, improves, and extends the user's skill library
through a continuous analysis loop. Combines quality grading, store search,
sub-skill decomposition, and curator lifecycle management.

## Acceptance gate

Before auditing, grading or restructuring the library, load `references/skill-library-acceptance.md`: the objective is reliable discovery, minimal necessary loading, and verified execution—not maximizing archives or minimizing skill count. These acceptance criteria override superficial quality scores and unconditional consolidation/decomposition heuristics below.

## When to Use

- Triggered by cron job (weekly, alongside curator)
- On-demand via "audit skills", "skill quality check", "find skill gaps"
- After a session where the agent struggled without a relevant skill

## The Loop (7 Phases)

### Phase 1 — Quality Audit

Grade every installed skill on completeness. Score 0-100.

**Criteria (each 0-20 points):**

| Criterion | What to check | Max |
|-----------|---------------|-----|
| Structure | Has `## When to Use`, numbered steps, pitfalls section | 20 |
| Linked files | references/, templates/, scripts/ populated | 20 |
| Freshness | last_patched_at within 60 days, no stale commands | 20 |
| Usage | use_count > 0 in last 30 days (from skill_usage) | 20 |
| Specificity | Unique knowledge, not duplicate of another skill | 20 |

**Execution:**
```python
from tools.skill_usage import get_record
from pathlib import Path
import yaml

skills_dir = Path.home() / ".hermes" / "skills"
for skill_md in skills_dir.rglob("SKILL.md"):
    # Parse frontmatter + body
    # Check structure markers (## When to Use, pitfalls, verification)
    # Check linked_files existence
    # Query get_record(name) for usage stats
    # Score and categorize: A (80+), B (60-79), C (40-59), D (<40)
```

**Usage data source:** `~/.hermes/skills/.usage.json` — flat JSON keyed by skill name. Each entry:
```json
{
  "use_count": 198,        // total times skill was loaded via skill_view
  "view_count": 198,       // same as use_count (view = load)
  "created_by": "agent",   // "agent" | "user" | null (imported)
  "last_used_at": "2026-06-25T07:43:48.837116+00:00",
  "last_viewed_at": "...",
  "pinned": false,
  "patch_count": 16,
  "state": "active"        // "active" | "archived"
}
```
To find least-used agent-created skills: filter `created_by in ("user", "agent")` and sort by `use_count` ascending. To find most-used overall: sort by `use_count` descending.

**Output:** JSON report at `~/.hermes/skill-audit/audit-{date}.json`

### Phase 2 — Gap Detection

Identify recurring patterns where the agent SHOULD have had a skill but didn't.

**Primary method — run the local script first. Do not search the web, session database, or tool indices for gap detection before executing this.**
```bash
python3 ~/.hermes/skills/productivity/skill-intelligence-loop/scripts/skill_gap_detector.py --sessions 30 --output ~/.hermes/skill-audit
```
Review `~/.hermes/skill-audit/skill-gaps-{date}.md`. This covers recurring tool sequences, missing service skills, and heavy tool sessions.

**Secondary signals** (only if the script is unavailable or you need deeper context):
1. `session_search` for sessions where the agent did 5+ tool calls on a topic with no skill loaded
2. Cron job tasks that reference skills not installed
3. User corrections that would have been prevented by a skill
4. Tool call patterns (e.g., repeated `scrapling` calls on same site type = need a site-specific skill)

**Store search for installation candidates** (Phase 5):
```bash
hermes skills search "<detected_pattern>" --source all --limit 10
```

**Output:** `~/.hermes/skill-audit/skill-gaps-{date}.json` + `.md`

### Phase 3 — Sub-Skill Decomposition

Break monolithic skills into reusable sub-skills that compose into workflows.

**Rules:**
- A sub-skill MUST be independently usable (not just a section of a parent)
- A sub-skill MUST have its own `## When to Use` trigger
- Parent skill references sub-skills: `Load <sub-skill-name> for the X step`
- Sub-skill naming: `{parent}-{specific}` (e.g., `r2-setup-and-video-pipeline`)

**When to decompose:**
- Skill > 300 lines AND has clearly separable phases
- Same steps appear in 2+ skills (extract to shared sub-skill)
- Skill references external tools that have their own learning curve

**Example decomposition:**
```
BEFORE:
  scena-video-factory (800 lines, everything in one)

AFTER:
  scena-video-factory (200 lines, orchestration)
    → references: scena-auth-client-sync-debug (auth step)
    → references: scena-deploy-workflow (deployment step)
    → references: scena-cloudflare-serverless (infra step)
```

### Phase 4 — Gap Detection

Analyze recent sessions to find patterns without skill coverage.

**Script:** `scripts/skill_gap_detector.py`

**Detects:**
1. **Recurring tool sequences** — same tools used together 3+ times across sessions
2. **Missing service skills** — external services referenced 10+ times without dedicated skill
3. **Heavy tool sessions** — 5+ tool calls on same topic with no skill loaded
4. **Common tool pairs** — two tools frequently used together

**Output:** `~/.hermes/skill-audit/skill-gaps-{date}.json` + `.md`

### Phase 5 — Auto-create Skills for Gaps

For service gaps with 10+ references:
1. Search store: `hermes skills search "<service>" --source all --limit 5`
2. Preview quality: `hermes skills inspect <id>`
3. If quality > 70 → install automatically
4. If no store match → create minimal skill with `skill_manage(action='create')`

For gaps < 10 references → list as recommendations only.

### Phase 6 — Curator Integration

The existing curator handles lifecycle. Feed it better data.

**What to pass to curator:**
1. Quality grades from Phase 1 (so it archives D-grade skills)
2. Usage deltas from Phase 2 (so it promotes frequently-needed skills)
3. Decomposition candidates from Phase 3 (so it can consolidate)

**Curator config:**
```yaml
auxiliary:
  curator:
    enabled: true
    interval_hours: 168  # 7 days
    model: "gemini/gemini-3.1-flash-lite"
```

**Run curator manually:**
```bash
hermes curator run --dry-run   # preview
hermes curator run             # execute
hermes curator status          # last run summary
```

### Phase 7 — Report & Action

Generate a human-readable report and take automated actions.

**Automated (no approval needed):**
- Install recommended skills from store (quality score > 70 only)
- Patch skills missing pitfalls/verification sections
- Remove dead skills (use_count=0, last_used > 90 days, grade D)
- Update stale skills (`hermes skills update`)

**Requires approval:**
- Decompose a skill into sub-skills (structural change)
- Install skills from GitHub taps (not official registry)
- Consolidate 2+ skills into one

## Pinned Skills — ABSOLUTE RULE

Skills created from user instructions are SACRED. When the agent creates a skill via `skill_manage(action='create')` following a user request:
1. Immediately pin it: `hermes curator pin <skill_name>`
2. The Curator MUST NEVER archive, prune, or consolidate pinned skills
3. `skills.guard_agent_created: true` in config.yaml enforces this
4. If a task was solved once, the skill makes repetition instant — no re-discovery

## Continuous Improvement — LIVE RULE

Every time a skill is used in a real session, the agent MUST improve it if any of these apply:
- A pitfall was discovered that isn't documented → `skill_manage(action='patch')` immediately
- A better command/approach was found → update the skill in-place
- The same context was added around the skill multiple times → bake it into the skill
- A linked file (reference, template, script) would have saved time → create it
- The skill's "## When to Use" trigger was too narrow or too broad → refine it
- Verification steps were missing and something broke → add them

**DO NOT wait for the Curator or the Intelligence Loop.** Patch skills in real-time, during the session, as soon as the improvement is identified. The Curator only handles lifecycle (stale/archive). Improvement is the agent's job, every turn.

**Frequency rule:** A skill used 3+ times without being patched is a missed opportunity.

Currently pinned (12):
contact-intelligence-systems, free-model-offer-watchdog, google-oauth-session-persistence,
hermes-multi-agent-profiles, hyperframes-video-rendering, irs-form-filling,
landing-page-product-images, miroshark, multi-provider-image-gen, ssh-mac-remote-control,
stripe-checkout-automation, systemd-crash-loop-recovery

## Cron Job Prompt

```
Run the skill intelligence loop: audit all installed skills for quality
(structure, linked files, freshness, usage, specificity), detect gaps by
searching recent sessions for tool-heavy patterns without skill coverage,
search the skill store for complementary skills, and generate a report.
Patch low-quality skills automatically. For decomposition candidates or
new store installs, list them and wait for approval. Update the curator
with the quality grades.
```

## Output Format

```markdown
# Skill Intelligence Report — {date}

## Quality Grades
| Skill | Grade | Issues |
|-------|-------|--------|
| hermes-agent | A (92) | — |
| kanban-worker | C (45) | Missing pitfalls, unused 60d |
| comfyui | B (71) | No linked templates |

## Gaps Detected
- Repeated scraping of e-commerce sites → recommend: `scrapling` skill already installed
- 3 sessions needed email parsing → recommend: `ocr-and-documents` (not installed)

## Store Recommendations
| Skill | Source | Quality | Action |
|-------|--------|---------|--------|
| playwright-mcp | skills.sh | 85 | ✅ Auto-install |
| stripe-api-v2 | github:user/repo | 62 | ⏳ Needs review |

## Decomposition Candidates
- `scena-video-factory` (800 lines) → split into 4 sub-skills
- `walter-brain` (600 lines) → split into architecture + implementation

## Curator Actions
- Archived: 2 dead skills
- Promoted: 3 skills with rising usage
- Patched: 5 skills with missing sections
```

## Pitfalls

- Don't auto-install skills from untrusted GitHub repos — always preview first
- Don't decompose skills that are already small (< 150 lines) — overhead > benefit
- Don't archive skills that are pinned (`hermes curator pin <name>`)
- Monsieur requires Curator consolidation via OpenAI Codex Luna at maximum reasoning, not a cheaper substituted model. Load `hermes-provider-mastery` → `references/curator-codex-reasoning.md` for exact configuration and real wire verification; preserve protected skills and measure consolidation outcomes.
- Gap detection needs ≥ 10 sessions of data to be meaningful
- Sub-skill decomposition changes slash command names — update cron jobs that reference them
- **Mid-run anti-progress signal:** If the user gives mid-turn feedback (e.g., "You've reached the maximum number of tool-calling iterations. Please provide a final response...") — STOP. Provide a summary of what was accomplished, not additional tool calls. The summary is the deliverable. This is not a prompt to continue with more tools; it is the session ending.
- **Inherited stale state:** If prior context says the agent is "stuck searching" or "transitioning from search to audit," discard the search state and run the local audit scripts directly.
- **Empty response trap:** Never emit a blank reply after tool calls execute. Always process the tool output, summarize it, and continue to the next phase or report.
- **Tool-call budget exhaustion:** Hermes caps tool-call iterations per session. If you hit the limit, provide the best available summary and never regress to an earlier phase. The run is complete, not broken. The user's "Please provide a final response" after a tool-call limit should trigger a summary of whatever was accomplished, not additional tool use.
- **Self-referential loop:** Do not re-invoke the intelligence loop or its sub-scripts as a "solution" to hitting a tool-call limit. The loop has already run; produce the final report immediately.

## Verification

After each loop run:
1. `hermes skills list` — verify all expected skills present
2. `hermes curator status` — verify curator received grades
3. `ls ~/.hermes/skill-audit/` — verify report written
4. Spot-check 2-3 patched skills for correctness

## Diagnose a shrinking library before changing Curator policy

1. Separate the two Curators: Hermes owns `~/.hermes/skills`; walter-skills owns `/walter/capabilities/skills`. Do not interpret one library's managed count as the total number of available skills.

2. Inspect Hermes lifecycle reports and provenance before running a mutation:
```bash
/root/.hermes/hermes-agent/venv/bin/hermes curator status
/root/.hermes/hermes-agent/venv/bin/hermes curator usage
/root/.hermes/hermes-agent/venv/bin/hermes curator list-unmanaged
```
Treat `created_by: agent` in `.usage.json` as an explicit management marker. Do not infer eligibility from directory location or treat unmanaged skills as missing.

3. Reconcile active files, archived files, telemetry and ledger actions:
```bash
python3 - <<'PY'
from pathlib import Path
from collections import Counter
import json
root = Path('/root/.hermes/skills')
active = [p for p in root.rglob('SKILL.md')
          if not any(part.startswith('.') for part in p.relative_to(root).parts)]
archive = root / '.archive'
archived = list(archive.rglob('SKILL.md')) if archive.exists() else []
usage = json.loads((root / '.usage.json').read_text())
ledger = [json.loads(line) for line in (root / '.curator_ledger.jsonl').read_text().splitlines()
          if line.strip()]
print('active files:', len(active), 'archived files:', len(archived))
print('provenance/state:', Counter((str(v.get('created_by')), str(v.get('state')))
                                  for v in usage.values()))
print('ledger actor/action:', Counter((r.get('actor'), r.get('action')) for r in ledger))
for r in ledger:
    evidence = r.get('evidence') or {}
    if r.get('action') == 'delete' or evidence.get('absorbed_into'):
        print(r.get('ts'), r.get('actor'), r.get('action'), r.get('skill'),
              'absorbed_into:', evidence.get('absorbed_into'))
PY
```
Trace consolidation destinations through `evidence.absorbed_into`; verify that the destination exists and retains the useful procedure. Compare dated `~/.hermes/logs/curator/*/run.json` reports. Distinguish archival, consolidation, deletion and provenance exclusion before proposing restoration or policy changes.

4. Back up affected files under `/root/.hermes/backups/` before modifying them. Prefer quarantine or restoration review over deletion. Extend Hermes through plugins rather than patching its upstream checkout.

5. Submit shared-library improvements through `skill_propose` or `skill_patch`, which create drafts. Use this draft-review preview for walter-skills:
```bash
cd /walter/capabilities/skills
/walter/cognition/memory/venv/bin/python - <<'PY'
import json
from walter_skills import curator
r = curator.run(apply=False, only={'drafts'})
print(json.dumps(r['summary']))
for key in ('drafts_accepted', 'drafts_rejected', 'drafts_pending', 'hermes_conflicts'):
    print(key, r['done'].get(key, []))
PY
```
Check pending decisions and Hermes conflicts before treating a draft as accepted; a shadow review does not publish changes.

## Vérifier la conversion des secrets en références par le curator

Lors d'un audit des secrets de la bibliothèque, vérifier ensemble l'opérateur `secrets` du curator et la porte d'entrée des propositions/corrections. Une suppression du secret n'est complète que si l'agent dispose encore d'une référence utilisable.

1. Résoudre le module avec `walter path skills`. Examiner `walter_skills/secret_refs.py`, `walter_skills/curation/operators.py`, `walter_skills/door.py` et la configuration des passages rapides. Vérifier que l'opérateur couvre les skills actifs, archivés, les brouillons et les copies Hermes.
2. Utiliser le format officiel `{{bw:<élément>:<champ>}}`. Vérifier les interfaces avec `walter-secret --help`. Pour obtenir une référence sans valeur, utiliser `walter-secret ref <élément> <champ>`. Ne jamais afficher les valeurs pour établir le diagnostic.
3. Convertir les valeurs connues du coffre avant les contrôles et écritures de la porte d'entrée. Vérifier que le détecteur distingue les références officielles des secrets en clair : une ligne portant une étiquette de mot de passe peut produire un faux positif même après conversion.
4. Pour réparer d'anciens marqueurs génériques `«secret:vault»`, retrouver la correspondance exacte depuis la sauvegarde antérieure au masquage, traitée localement. Ne pas deviner l'élément à partir du seul marqueur. Sauvegarder avant modification et ne journaliser que les chemins, comptes et références sans valeur.
5. Depuis la racine du module, lancer `walter-python -m pytest -q tests/test_secret_refs.py`, puis les contrôles pertinents de la porte et du curator. Exécuter ensuite le passage rapide documenté dans la version installée et contrôler les actions `secrets` dans `skills.ledger`. Un test unitaire réussi ne prouve pas que le passage réel couvre toute la bibliothèque.
6. Vérifier la synchronisation Hermes après les conversions. Comparer les contenus avant de mettre à jour les empreintes des sidecars ; ne pas masquer une divergence réelle en remplaçant simplement leur SHA.

Ne pas présenter la comparaison d'empreintes comme une absence totale de manipulation des valeurs : la construction des correspondances et la réécriture peuvent nécessiter leur lecture locale. Garder ces valeurs hors des sorties d'outils et du contexte du modèle.
