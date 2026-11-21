---
name: french-admin-filing
category: productivity
description: French CSS/admin forms filled coherent with real tax data.
---

# French Admin Filing Skill

Fill French administrative forms — attestation de ressources, CSS (Complémentaire santé solidaire) dossiers, URSSAF-type resource declarations — so every number is **coherent with the supporting document that will be attached**. Written for this user: French citizen living abroad (Bangkok) handling French paperwork remotely, low-income auto-entrepreneur.

## When to Use

- Filling an attestation de ressources or any French income/resources declaration.
- Preparing a CSS dossier: identifying which documents to provide and checking coherence between them.
- Any French form where declared monthly income must match the avis d'imposition that goes in the same envelope.

## Prerequisites

- The real supporting document (avis d'imposition) — retrieve it via the `authenticated-portal-document-retrieval` skill (`references/impots-gouv-fr-auth.md`) or from the user's drop. **Never invent figures.**
- Hermes venv with `pdfplumber` + `pypdf` (and poppler `pdftotext`/`pdftoppm`).
- Identity data: fiscal number in Bitwarden (`*.impots.gouv.fr` items), birth date in the Kardex (`preferences.birth_date`), address from the avis/identity.

## The Coherence Rule (critical)

- The CSS caisse cross-checks your **Revenu fiscal de référence (RFR)** directly with the DGFiP. The attestation's monthly total must equal **RFR ÷ 12**. That is simultaneously the minimum *credible* figure and the truthful one for a low-income declarant.
- Never under-declare below the avis you are attaching — the document is right there in the dossier and the mismatch is trivially caught.
- For this user the honest minimum IS the real number (e.g. RFR 6 288 € → 524 €/mois, impôt 0). Declaring it is both correct and optimal; inventing a lower "credible-looking" number is the fastest way to fail the dossier or worse.

## How to Run

1. Extract the avis text: `pdftotext -layout avis.pdf -` (or pdfplumber `extract_text()`); locate the **RFR** line (e.g. "Revenu fiscal de référence 25 ... 6288").
2. Derive monthly total = RFR ÷ 12 when it divides clean (6 288 ÷ 12 = 524), else round conservatively.
3. Fill the attestation via `scripts/fill_pdf_left_align.py` using `templates/attestation_de_ressources_fields.json` as the coordinate map (see reference for the field layout).
4. Render to PNG (`pdftoppm -png -r 140 out.pdf page`) and visually verify every value lands on its line, left-aligned, before delivering.
5. Leave the signature line blank — see Pitfalls.

## Quick Reference

- `references/attestation-de-ressources-css.md` — full field/coordinate map, RFR→monthly derivation, CSS document list.
- `templates/attestation_de_ressources_fields.json` — start-from-me fields.json for the standard modèle-attestation.com form.
- `scripts/fill_pdf_left_align.py` — flat-form filler that forces left-aligned FreeText annotations.

## Pitfalls

- The attestation template is a **flat PDF** (no AcroForm) — overlay FreeText annotations; `fill_fillable_fields.py` is the wrong tool.
- pypdf FreeText may center text by default: force `ann.alignment = 0` after construction or values float mid-line and look sloppy (validated fix).
- Hidden vs visible password field pattern (impots portal `pwd` hidden / `pwd_tmp` visible) — see the impots reference, do not re-derive.
- `convert_pdf_to_images.py` may require `pdf2image`; `pdftoppm -png -r 140` is the reliable no-dependency fallback.
- **Signature:** do NOT fabricate a signature image. Only auto-sign once a real signature asset exists. Recovering an Apple Preview signature: not found in the standard Preview container dir on this Mac — prefer asking the user to export it (Preview → markup signature → File > Export) over guessing files.

## Verification

- Render output to PNG; check each field on the right line, left-aligned, no overflow.
- Confirm attestation total == RFR ÷ 12 (or your explicit rounding) before delivery.
