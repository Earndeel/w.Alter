---
name: aa-pareto-to-hermes-skill
description: "Use when AA findings inform a committed Hermes skill."
type: workflow
requires: [aa-pareto-model-optimizer, hermes-agent-skill-authoring]
---

# AA Pareto Findings to Hermes Skill

## When to Use

Use when an ad-hoc AA comparison must lead to creating or editing a committed Hermes-Agent skill: first establish the evidence, then encode the reusable procedure in the repository. A report-only request or an unrelated skill edit does not require this chain.

This workflow owns the handoff and acceptance gates. The sub-skills own collection, analysis, authoring, and validation procedures; load their current instructions rather than reproducing them here.

## Procedure

### 1. Establish evidence

Load aa-pareto-model-optimizer with skill_read.

Apply it to the requested intelligence frontier, upgrade ladder, multimodal leaderboard, or intelligence-versus-cost extraction. Establish whether existing Walter Router evidence meets the request or an ad-hoc collection is required, following the sub-skill's guidance.

Produce an evidence packet containing:
- Requested task, objective, freshness requirement, and analysis settings.
- Artifact locations, source timestamps, row counts, and provenance.
- Verified findings, exclusions, missing measurements, and relevant limitations.
- The reusable behavior the requested skill change should implement, distinguished from time-sensitive model rankings.
- Verification results and any unresolved collection or analysis failure.

Gate: advance only when the evidence satisfies the requested freshness and coverage, comparisons use compatible measurements, and the sub-skill's applicable verification succeeds. If collection or validation fails, resolve it here or report the blocker; do not turn an unverified result into skill guidance.

### 2. Turn verified findings into repository guidance

Load hermes-agent-skill-authoring with skill_read.

Pass the evidence packet together with the requested repository, target branch, and intended skill change. Follow the sub-skill to inspect repository instructions and peers, choose placement, implement the change, and validate its structure, tests, and generated documentation.

Use the packet to define reproducible behavior and acceptance criteria. Keep changing rankings and prices in evidence artifacts or runtime outputs; avoid embedding them as permanent recommendations. Reference existing specialist procedures instead of copying their implementation into the authored skill.

Gate: every substantive recommendation must trace to the verified packet, every modified file must belong to the requested change, and all applicable authoring checks must pass. If authoring reveals a missing measurement or unsupported claim, return to step 1, load aa-pareto-model-optimizer with skill_read, and repair the packet before continuing step 2.

## Pitfalls

- Seven observed chains establish a useful sequence, not permission to author or publish a skill after every AA report. Apply the workflow only when both outcomes are requested.
- Passing a prose conclusion without artifact locations and provenance prevents the authoring step from checking its basis.
- Successful repository validation does not establish that the underlying comparison is correct; both gates must pass.
- Dependency loading failures block the affected step. Do not reconstruct a missing sub-skill from memory.

## Verification and Handoff

Deliver the verified report or evidence references, the resulting skill change, and the relevant test and documentation results. State any unresolved limitations and the actual commit or PR status. Repository and external publication actions remain within the user's authorized scope; do not imply that drafting this workflow authorizes executing or publishing it.
