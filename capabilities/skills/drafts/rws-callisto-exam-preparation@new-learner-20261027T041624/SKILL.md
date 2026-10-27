---
name: rws-callisto-exam-preparation
description: Use when preparing Monsieur for the RWS Callisto exam by reviewing historical screenshots against the guidelines supplied for the upcoming exam.
---

## Establish the reference material

- Recall the RWS project context through `memory_context`; verify current deadlines and instructions against the actual invitation.
- Identify the guidelines supplied for the upcoming exam. Record their title, date and pagination. They take priority over historical answers and public copies.
- Label comparisons across versions explicitly. An answer photographed in June 2024 and reviewed against September 2025 guidelines is a retrospective comparison, not proof of the original exam's expected answer.
- Work in a dedicated session directory. Keep original photos and PDFs unchanged; put intermediate data in `work/` and deliverables in `outputs/`.

## Inventory and transcribe the evidence

- Inventory every photo before reviewing it. Preserve its filename as the evidence identifier.
- Group photos by question or practical task; distinguish overlapping screenshots from separate tasks.
- Record the exact statement, visible selected answer and legibility separately. Inspect the image before accepting a transcription.
- Preserve qualifiers such as “always”, “only”, “can” and negation. Similar wording does not establish that two questions have the same answer.
- Mark obscured selections as unreadable. Never infer a selected answer from the answer that would be correct.

## Extract and check guideline references

Use `python3` and PyMuPDF to create a searchable page index:

```bash
python3 - <<'PY'
import json
from pathlib import Path
import fitz

source = Path('inputs/guidelines.pdf')
with fitz.open(source) as doc:
    pages = [
        {'page': i + 1, 'text': page.get_text()}
        for i, page in enumerate(doc)
    ]
Path('work').mkdir(exist_ok=True)
Path('work/guideline_pages.json').write_text(
    json.dumps(pages, ensure_ascii=False, indent=2)
)
PY
```

- Search the extracted text, then read the full relevant section and its exceptions. A keyword hit alone is insufficient.
- Check whether PDF page numbers match printed page numbers; state which numbering the report uses.
- For each correction, record the photographed answer, guideline-based conclusion, section/page reference and explanation.
- Keep confirmed corrections, ambiguous wording and unreadable selections separate. Do not count uncertainty as an error.

## Review practical tasks within the visible evidence

- Separate Page Quality (PQ), Needs Met (NM), flags and duplicate handling.
- Compare grid selections with written comments. Flag contradictions such as a neutral reputation selection paired with a positive-reputation comment.
- Check special rules independently. The reviewed material exposed a missed exception: a malware warning does not receive the “Did Not Load” flag.
- Do not infer a definitive PQ or NM rating when the evaluated page or result is unavailable.
- Describe checkbox state at the photographed moment. Do not infer final submission state without evidence.

## Produce and verify the review

- Generate structured review data first, then render the report and exercises from it so conclusions stay consistent.
- Reconcile counts: source photos, unique theory statements, practical tasks, confirmed corrections and unresolved items.
- Give each conclusion a source-photo identifier and guideline reference.
- Open the generated PDF with PyMuPDF, check page text, and render representative pages for visual inspection. Include dense tables and pages containing screenshots.
- Prepare exercises from verified rules, with an explained answer key. Keep unresolved historical answers out of the definitive key.

## Reuse the review for preparation

- Compare any newly supplied question's complete wording and context before consulting an old answer.
- Recheck the applicable guideline section when wording, version, locale, result block or landing page differs.
- Use old practical tasks to explain reasoning when their original pages cannot be reconstructed.
- Report preparation coverage and remaining uncertainty accurately; do not promise a passing result.
