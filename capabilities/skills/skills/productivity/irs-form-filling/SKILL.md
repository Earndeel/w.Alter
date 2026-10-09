---
name: irs-form-filling
description: Fill IRS forms (SS-4, 8832, 2553, etc.) as XFA PDFs from irs.gov — field mapping, pymupdf filling, Google Drive upload.
version: 1.0.0
author: W.Alter
tags: [IRS, tax, LLC, EIN, forms, PDF, XFA]
metadata:
  hermes:
    tags: [IRS, tax, LLC, EIN, forms, PDF]
---

# IRS Form Filling

Fill official IRS PDF forms programmatically for non-US residents and entities.

## Trigger Conditions
- User needs IRS forms filled (SS-4 for EIN, 8832 for entity classification, 2553 for S-corp election, etc.)
- User is setting up a US LLC and needs tax documentation

## Prerequisites
- `pymupdf` (`pip install pymupdf`) — handles XFA form fields
- Google Workspace auth with Drive scope (see `google-workspace` skill)

## Steps

### 1. Download the latest form from IRS
```bash
curl -sL "https://www.irs.gov/pub/irs-pdf/fss4.pdf" -o /tmp/SS4.pdf
# fss4 = Form SS-4. Pattern: f{form_number}.pdf
# Other forms: f8832.pdf, f2553.pdf
```

**⚠️ ALWAYS download fresh.** Forms change annually. Never use a cached/stale version.

### 2. Inspect form fields
```python
import pymupdf

doc = pymupdf.open("/tmp/SS4.pdf")
for page in doc:
    for w in page.widgets():
        name = w.field_name.split(".")[-1].replace("[0]", "")
        print(f"  {name} | type={w.field_type_string} | y={round(w.rect.y0,1)} | x={round(w.rect.x0,1)}")
```

IRS XFA forms use nested names like `topmostSubform[0].Page1[0].f1_2[0]`.
Always split on `.` and take the last segment for short names.

### 3. Map fields by position
Fields are sorted top-to-bottom, left-to-right by Y then X coordinate.
Cross-reference with the official form's line numbers:
- Print the field list with Y positions
- Open the form visually to confirm mapping
- Common SS-4 mapping: see `references/ss4-field-mapping.md`

### 4. Fill and save
```python
import pymupdf

doc = pymupdf.open("/tmp/SS4.pdf")
values = {"f1_2": "COMPANY NAME", "f1_5": "Owner Name", ...}

for page in doc:
    for w in page.widgets():
        short = w.field_name.split(".")[-1].replace("[0]", "")
        if short in values:
            w.field_value = values[short]
            w.update()

doc.save("/tmp/SS4_filled.pdf")
```

### 5. Verify visually
```bash
# Convert first page to image for review
python3 -c "
import pymupdf
doc = pymupdf.open('/tmp/SS4_filled.pdf')
page = doc[0]
pix = page.get_pixmap(dpi=150)
pix.save('/tmp/SS4_preview.png')
"
```
Show the preview image to the user before uploading.

### 6. Upload to Google Drive
Use `google-workspace` skill. Upload to entity-specific folder (create if needed).

## Non-US Resident EIN (SS-4 specific)
- Line 7b (SSN/ITIN): write **FOREIGN**
- No online application available (requires SSN/ITIN)
- Two options:
  1. **Fax** SS-4 to +1-855-215-1627 (4-6 weeks)
  2. **Call** IRS International: +1-267-941-1099 (6AM-11PM EST, Mon-Fri) — **EIN issued immediately**
- Have entity name, state, formation date, responsible party name ready

## Pitfalls
1. **Stale forms**: IRS updates forms periodically. Always `curl` fresh from irs.gov.
2. **XFA field names**: UTF-16 encoded in some tools. Use pymupdf which decodes them.
3. **Checkbox values**: Set to `Yes` or the specific checkbox export value, not `True`/`On`.
4. **Field mapping**: Don't guess — verify by converting to image. Wrong field = wrong form.
5. **Google Drive scopes**: Must have `drive` scope. Re-auth if needed: `GSETUP --auth-url --services all`.
