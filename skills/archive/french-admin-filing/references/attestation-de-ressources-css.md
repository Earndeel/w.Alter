# Attestation de ressources — field map + CSS coherence

Validated 2026-08-07 on the standard `modele-attestation.com` attestation de ressources template (2 pages, flat PDF, non-fillable, 595.28 × 841.89 pt).

## Field coordinate map (page 1, PDF coords, y=0 top)

Extracted with `extract_form_structure.py`. Entry x0 = label x1 + small gap; top/bottom straddle the underline line for that row.

| Field | x0 | top | x1 | bottom |
|-------|-----|-----|-----|--------|
| Nom | 92 | 102 | 538 | 118 |
| Prénom | 107 | 118 | 538 | 135 |
| Date de naissance | 157 | 136 | 538 | 152 |
| Adresse complète | 156 | 152 | 538 | 169 |
| Salaire net mensuel | 178 | 226 | 538 | 243 |
| Autres revenus professionnels | 224 | 243 | 538 | 260 |
| Allocations chômage | 182 | 294 | 538 | 311 |
| Allocations familiales | 183 | 311 | 538 | 328 |
| Autres prestations | 170 | 328 | 538 | 345 |
| Montant total | 142 | 379 | 538 | 396 |
| Fait à | 90 | 447 | 300 | 462 |
| Le (date) | 332 | 447 | 538 | 462 |

**Layout convention:** values are entered inline after the label (left-aligned in their zone), not centered down the page. Font size 10.

## RFR → monthly derivation (the coherence core)

- Read the avis d'imposition RFR line (e.g. "Revenu fiscal de référence 25 ...... 6288").
- Monthly total = RFR ÷ 12 when clean: 6 288 ÷ 12 = **524 €/mois** → put 524 in « Autres prestations » + 524 in « Montant total ».
- Fill 0 in salaire / autres revenus pro / allocations chômage / allocations familiales when the avis shows none.
- « Fait à » = where signed (user choice: Givors for the CSS dossier). « Le » = date of signature.

## CSS dossier — documents

Per user (2026-08): la CSS demande l'attestation de ressources **+ la déclaration d'impôts** (avis d'imposition 2025 = revenus 2024). The avis comes as a real PDF (online-only in the espace, or retrieved by user during OTP lockout). The attestation is filled to match it exactly.

## Delivery

- Copy the filled PDF to `~/Downloads/attestation_de_ressources_<Name>_remplie.pdf` and deliver via MEDIA:.
- Leave the signature line blank unless a real signature asset exists (see SKILL.md Pitfalls).
