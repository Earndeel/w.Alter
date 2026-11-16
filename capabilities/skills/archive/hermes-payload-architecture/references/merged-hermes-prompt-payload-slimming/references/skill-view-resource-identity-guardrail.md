# `skill_view` resource identity guardrail

Prompt-view deduplication must treat a skill's main file and every linked support file as distinct instructional resources.

## Correct identity

Key loaded-resource state by:

```text
(skill_name, file_path or "SKILL.md")
```

Do not key it by skill name alone.

## Required behavior

1. Loading `SKILL.md`, then `references/a.md`, returns both raw once.
2. Loading `references/a.md`, then `references/b.md`, returns both raw once.
3. Only an exact repeat of the same resource may become `[SKILL ALREADY LOADED]`.
4. An explicit main-skill reload for curator read-before-write can return raw content in the current review turn.
5. After a support file is created or changed, its first subsequent read is not suppressed by an earlier read of the skill main file.

## Why this matters

If deduplication uses only `skill_name`, linked reference reads collapse into digests before the model receives their instructions. It also prevents `skill_manage` from satisfying its read-before-write safety guard, because requesting a raw reload produces `[SKILL ALREADY LOADED]` instead of the file content.

## Behavioral tests

- main → reference A → exact repeat A;
- reference A → reference B;
- main → curator patch in the same review turn;
- create reference C → read C → patch C;
- prompt rendering remains byte-idempotent after each exact repeat.
