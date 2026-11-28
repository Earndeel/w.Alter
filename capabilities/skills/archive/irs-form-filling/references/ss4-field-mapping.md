# SS-4 Field Mapping (IRS Form SS-4)

Based on `fss4.pdf` downloaded from irs.gov. Field names are pymupdf short names.

## Page 1 — Main Form

| Field | Type | Position | SS-4 Line | Description |
|-------|------|----------|-----------|-------------|
| f1_1 | Text | top-right | Header | EIN (assigned by IRS — leave blank) |
| f1_2 | Text | y=94 | Line 1 | Legal name of entity |
| f1_3 | Text | y=118, left | Line 2 | Trade name / DBA |
| f1_4 | Text | y=118, right | Line 2 | Trade name continuation |
| f1_5 | Text | y=142, left | Line 3 | Executor / administrator / care of name |
| f1_6 | Text | y=166, left | Line 4a | Mailing address (street) |
| f1_7 | Text | y=142, right | Line 4b | City, state, ZIP |
| f1_8 | Text | y=166, right | Line 4c | Country (if foreign) |
| f1_9 | Text | y=190 | Line 5a | Street address (if different from 4a) |
| f1_10 | Text | y=214, left | Line 5b | City, state, ZIP (if different) |
| f1_11 | Text | y=214, right | Line 6 | County and state of principal business |
| f1_12 | Text | y=240, right | Line 6 | continuation |
| c1_1 | CheckBox | y=241 | Line 7a | Entity type: Estate/Trust |
| c1_1[1] | CheckBox | y=241 | Line 7a | Entity type: other |
| c1_2 | CheckBox | y=254 | Line 7a | Entity type checkboxes (continued) |
| f1_13 | Text | y=276, left | Line 7a | Other entity type (specify) |
| f1_14 | Text | y=276, right | Line 7b | SSN / ITIN / EIN of responsible party |
| f1_15 | Text | y=288, right | Line 7b | continuation |
| c1_3 | CheckBox | y=278+ | Line 8a | Entity type checkboxes (LLC, Corp, etc.) |
| f1_18 | Text | y=336 | Line 8b | State where LLC formed |
| f1_19 | Text | y=348, left | Line 9 | Reason for applying |
| f1_20 | Text | y=348, right | Line 10 | Date business started |
| f1_21 | Text | y=370, left | Line 11 | Closing month of accounting year |
| f1_22 | Text | y=370, right | Line 12 | Principal activity |
| f1_24 | Text | y=384, right | Line 13 | Principal product or service |
| c1_4 | CheckBox | y=398+ | Line 14 | Applied before? Yes/No |
| f1_25 | Text | y=396, left | Line 15 | Date paying wages |
| f1_26 | Text | y=408, left | Line 16 | Highest number of employees |
| f1_27 | Text | y=396, right | Line 16 | continuation |
| f1_30 | Text | y=444 | Line 17 | Form 944 / 943 questions |
| f1_31 | Text | y=466, left | Line 18 | Third party designee name |
| f1_32 | Text | y=466, right | Line 18 | Designee phone |
| f1_33 | Text | y=526, left | Signature | Signature area |
| f1_34 | Text | y=526, mid | Signature | Title |
| f1_35 | Text | y=526, right | Signature | Date |
| f1_36 | Text | y=552, right | Signature | Phone number |
| f1_38 | Text | y=610 | Bottom | Additional info |
| f1_39 | Text | y=636 | Bottom | Fax number |

## LLC-Specific Tips
- Line 8a: Check the LLC checkbox (usually c1_3 with index for "Limited Liability Company")
- Line 8b: State where LLC was formed
- Line 9: Common values — "Started new business" (c1_4 index 0) or "Changed entity type" (c1_4 index 3)
- Line 11: December for calendar year
- Line 7b: For non-US residents without SSN/ITIN, write "FOREIGN"

## Checkbox Export Values
IRS checkboxes vary. Use pymupdf to check available values:
```python
for w in page.widgets():
    if w.field_type_string == "CheckBox":
        print(f"{w.field_name}: button_states={w.button_states()}")
```
