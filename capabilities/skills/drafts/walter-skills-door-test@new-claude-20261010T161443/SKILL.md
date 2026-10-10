---
name: walter-skills-door-test
description: "Use when testing the walter-skills write door end to end (propose, curator review, promotion)."
---

# walter-skills door test

1. Call `skill_propose` with a well-formed SKILL.md.
2. Run `walter-skills curate --shadow`.
3. Check `reports/curator-<date>.md` for the draft verdict.
