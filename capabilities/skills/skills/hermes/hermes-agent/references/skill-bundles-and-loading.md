# Skill Bundles — Group Multiple Skills Under One Slash Command

A bundle is a YAML file in `~/.hermes/skill-bundles/` that loads N skills at once via a single `/command`.

## Anatomy

```yaml
# ~/.hermes/skill-bundles/backend-dev.yaml
name: backend-dev
description: Backend feature work — code review, testing, PR workflow.
skills:
  - github-code-review
  - test-driven-development
  - github-pr-workflow
instruction: |
  Optional extra guidance injected above the skill bodies.
```

## How it works

- `/<bundle-name>` → loads all referenced skills' full content into one user message
- Same mechanism as `/<skill-name>` but for N skills at once
- Bundles **reference** skills, they don't duplicate them
- If a bundle and skill share the same name → bundle wins
- Missing skills are skipped with a note (not an error)

## Commands

```bash
hermes bundles list          # list bundles
hermes bundles create        # create interactively
hermes bundles delete NAME   # delete
```

## Skill Loading Mechanics (two-level)

**System prompt** contains only an **index** (name + description per skill, ~2-3K tokens total for 80 skills). NOT the full content.

**Full SKILL.md content** is loaded on demand when the agent calls `skill_view(name)`.

```
System prompt (always)
  └── <available_skills> index: name + description per skill
        │
        ▼
  Agent scans index, decides if skill is relevant
        │
        ▼
  skill_view("skill-name") → loads full SKILL.md
  (injected as user message to preserve prompt caching)
```

This is why the system prompt says "Before replying, scan the skills below. If a skill matches, load it with skill_view."
