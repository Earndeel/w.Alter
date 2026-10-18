---
name: dsh-context-compaction-validation
description: Use when changing or validating the Walter context adapter for DSH, especially automatic or manual compaction, privileged message preservation, replay, and recovery of original tool results.
---

## Inspect the real compaction transaction

Read `/opt/walter-context/ports/dsh/index.mjs`, its `README.md`, and `/opt/walter-context/tests/test_dsh.mjs` before changing the adapter.

Inspect the installed DSH implementation:

```bash
rg -n 'buildSummarizationInput|compactSurfaceRegion|compactRegion|compactNow|summarize' /opt/dsh/node_modules/@deepseek-ai/dsh-compaction-basic/lib/index.js
```

Trace which durable messages are retained, which messages enter the summarizer input, and which selected messages the transaction replaces. Summarizer input and replacement span are different sets: DSH can prepend the retained global system head to the selected region.

Treat installed dependency source as inspection evidence. Implement Walter protections in `/opt/walter-context/ports/dsh/index.mjs`.

## Preserve privileged messages across every entry point

Exercise automatic compaction, `compactRegion`, and `compactNow` separately. Automatic range selection does not establish safety for manually selected ranges.

Exempt exactly the retained global system head when validating summarizer input. Reject a replacement span containing any `system` or `developer` message, including one at the beginning of the span. Do not skip an arbitrary leading run of privileged messages: those messages can belong to the region being replaced.

On rejection or bridge failure, verify that the compaction transaction closes and leaves the conversation surface unchanged.

## Validate through real DSH transactions

Run the adapter tests from the module directory:

```bash
cd /opt/walter-context
node --test tests/test_dsh.mjs
```

Maintain regression coverage for:

- Walter checkpoint creation, persistence of raw originals, replay, and recovery.
- Python bridge failure without a changed conversation surface.
- Privileged messages inside an automatic compaction range.
- A leading privileged message inside a manually selected range.
- Both `compactRegion` and `compactNow`.
- Successful compaction while preserving the retained global system head.

Use actual DSH sessions and transactions for these checks; a mocked summarizer alone cannot prove that selected messages survive replacement.

## Deploy and verify the final artifact

Back up every changed installed file under `/root/.hermes/backups/` before installing the candidate. Review the candidate diff and check for active DSH processes before replacing loaded adapter code.

Rerun the transaction tests against the installed adapter. Record the deployed commit and file hashes in the deployment evidence.

If a late regression produces another fix, rebuild the deployment manifest and repeat backup verification. Verify that the encrypted offsite archive contains the final deployed files; an archive verified before the last fix does not cover that fix.
