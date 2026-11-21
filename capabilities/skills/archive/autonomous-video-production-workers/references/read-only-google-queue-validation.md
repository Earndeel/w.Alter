# Read-only Google queue validation

## Live source and fallback

Use the authenticated Google APIs to read spreadsheet metadata and values. A Drive `files.get` success does not prove the Sheets values API is enabled. If `sheets.googleapis.com` returns `SERVICE_DISABLED` while Drive access works, export the live Google-native spreadsheet through Drive as XLSX and parse the workbook's actual sheet names and cells. Report the source as `drive_xlsx_export_fallback`; do not treat this as permission to write through Drive.

The fallback must preserve:

- the spreadsheet ID and metadata;
- both tab names;
- actual first-row headers;
- row numbers, including blank rows;
- checkbox booleans;
- reference/result values needed for pending detection.

## Pending and inconsistency rules

For `VIDEO REQUESTS`:

```text
pending = non-empty REFERENCE VIDEO AND FINISHED is not true
inconsistent = FINISHED is true AND RESULT is empty
```

Default selection is ascending spreadsheet row number. The validation output should include `pending_rows`, `pending_count`, `inconsistent_finished_rows`, and `writes_performed: false`.

Expected headers:

```text
FINISHED | REFERENCE VIDEO | MODIFICATIONS / INSTRUCTIONS | BRAND ASSETS | RESULT
ASSET PACK | DRIVE FOLDER | NOTES
```

## No-write gate

The validation path may call only metadata/read/export operations. It must not call Sheets `update`, `append`, `clear`, Drive upload, checkbox mutation, or RESULT/FINISHED writes. Never run a production command merely to prove connectivity.

## Troubleshooting

If both Sheets values and Drive export fail, report the exact API service/permission error and stop the production validation. Do not fabricate a queue count from a static configuration or from an old export.
