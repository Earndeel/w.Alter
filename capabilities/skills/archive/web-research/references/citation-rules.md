# Citation and evidence rules

Use a stable ledger because models should emit source IDs, not reconstruct URLs from memory.

- Register each consulted URL immediately with `scripts/sources.py add` or `ingest`; keep query strings when they select different content.
- Cite while drafting, placing `[n]` directly after the supported sentence; use separate brackets and no more than three source IDs per sentence.
- Render the source list mechanically from the ledger. Use inline numeric markers plus a Sources block for chat/Markdown, footnotes or endnotes for PDFs, real footnotes for editable Word documents, a Sources slide for decks, and a source column plus Sources sheet for spreadsheets.
- Never cite a search snippet as if the page body was read, never hand-type the Sources block, and do not put citations into generated code.
- For high-stakes claims, attach a verbatim quote copied from fetched evidence with `quote`; mark genuinely unsourced claims `[unverified]`, and cross-check disputed facts independently.
- Run `scripts/sources.py verify <draft>`, using `--min-coverage` or `--evidence` when required, before delivery.
