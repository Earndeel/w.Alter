# Direct Gemini API Call Pattern

When `delegate_task` or the Hermes provider routing fails, call Gemini API directly via urllib. Use this when a specific Gemini model is requested (e.g., "utilise gemini 3.1 pro").

## API Key
```bash
export GEMINI_API_KEY=$(vault get gemini/api_key 2>/dev/null)
```

## Call Pattern
```python
import base64, json, urllib.request, os

api_key = os.environ["GEMINI_API_KEY"]
model = "gemini-3.1-pro-preview"  # or gemini-2.5-pro, etc.
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

# For text-only:
payload = {
    "contents": [{"parts": [{"text": "Your prompt here"}]}],
    "generationConfig": {"temperature": 0, "maxOutputTokens": 8192}
}

# For PDF/image analysis:
with open("/tmp/document.pdf", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

payload = {
    "contents": [{"parts": [
        {"text": "Your prompt here"},
        {"inline_data": {"mime_type": "application/pdf", "data": b64}}
    ]}],
    "generationConfig": {"temperature": 0, "maxOutputTokens": 8192}
}

data = json.dumps(payload).encode()
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=90)
result = json.loads(resp.read())
text = result["candidates"][0]["content"]["parts"][0]["text"]
```

## Available Models (as of May 2026)
- `gemini-2.5-pro` — stable
- `gemini-2.5-flash` — fast, cheaper
- `gemini-3.1-pro-preview` — latest, best quality
- `gemini-3.1-flash-lite` — fast, lightweight

## List Models
```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" | python3 -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin).get('models',[])]"
```

## Pitfalls
- API key is in vault (`gemini/api_key`), NOT in `.env` (which contains numbered lines that bash can't source)
- `maxOutputTokens` default is low — always set explicitly for long outputs
- PDF inline_data works with base64 encoding — no need to convert to images first
- Timeout: set urllib timeout to 90s+ for large PDFs with complex prompts
