# PDF Form Filling with Gemini Vision + PyMuPDF

## Workflow

1. Download PDF form from source
2. Convert to images (PyMuPDF) for visual analysis
3. Send to Gemini 3.1 Pro with field list + business data
4. Parse JSON response (text_fields + checkboxes)
5. Fill PDF via PyMuPDF widgets
6. Upload to Google Drive

## Gemini 3.1 Pro API

```python
import base64, json, urllib.request, os

# Get API key from vault
api_key = subprocess.run(["vault", "get", "gemini/api_key"], capture_output=True, text=True).stdout.strip()
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key={api_key}"

# Read PDF as base64
with open("/tmp/form.pdf", "rb") as f:
    pdf_b64 = base64.b64encode(f.read()).decode()

prompt = """You are analyzing [FORM NAME].
I need to fill this form for: [ENTITY DATA]
The PDF has these form fields: [FIELD LIST from PyMuPDF]
Tell me EXACTLY which fields to fill and with what values.
Output as JSON with two objects: "text_fields" mapping field_name to value, 
and "checkboxes" mapping field_name to "Yes"."""

payload = {
    "contents": [{"parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}}
    ]}],
    "generationConfig": {"temperature": 0, "maxOutputTokens": 8192}
}

req = urllib.request.Request(url, json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=60)
result = json.loads(resp.read())
text = result["candidates"][0]["content"]["parts"][0]["text"]
```

## PyMuPDF Form Field Discovery

```python
import pymupdf

doc = pymupdf.open("/tmp/form.pdf")
for page in doc:
    for w in page.widgets():
        print(f"  {w.field_name} | type={w.field_type_string} | y={w.rect.y0:.1f} | val={w.field_value}")
```

## PyMuPDF Form Filling

```python
doc = pymupdf.open("/tmp/form.pdf")
for page in doc:
    for w in page.widgets():
        name = w.field_name.split(".")[-1].replace("[0]", "")
        if w.field_type_string == "Text" and name in text_fields and text_fields[name]:
            w.field_value = text_fields[name]
            w.update()
        elif w.field_type_string == "CheckBox" and name in checkboxes:
            w.field_value = checkboxes[name]
            w.update()

doc.save("/tmp/form_filled.pdf", deflate=True, garbage=3)
```

## Key Lessons (SS-4 Form, 2026-05-24)

- Gemini 3.1 Pro correctly mapped 89 form fields to SS-4 line numbers from field coordinates alone
- The "Other (specify)" entity type checkbox (c1_3[6]) was correctly identified
- pymupdf checkbox values: use "Yes" or numeric export values (1, 2, 4, 9 etc. depending on the form)
- Field names are XFA paths like `topmostSubform[0].Page1[0].f1_2[0]` — extract the short name with `.split(".")[-1].replace("[0]","")`
- The `garble` xref errors from pymupdf are cosmetic — the filled PDF is still valid

## Pitfalls

- **Use the model the user requests** — don't substitute mixture_of_agents or a different model. If the user says "Gemini 3.1 Pro", use `gemini-3.1-pro-preview`.
- **Inject ONLY the necessary data** — don't dump all form fields. Give the model the business data and the field list, let it decide the mapping.
- **Verify visually** — after filling, convert back to image and check with vision_analyze.
