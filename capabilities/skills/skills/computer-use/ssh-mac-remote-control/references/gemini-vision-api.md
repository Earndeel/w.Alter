# Gemini Vision API via curl

Direct vision analysis when Hermes auxiliary vision model fails (e.g., routing bug with unsupported primary model).

## Setup
```bash
API_KEY=$(vault get gemini/api_key)
MODEL="gemini-3.1-flash-lite"
```

**Pitfall:** `gemini-2.0-flash-lite` is a DIFFERENT model. Use `gemini-3.1-flash-lite` to match Hermes config.

## Single image analysis
```bash
python3 << 'PYEOF'
import base64, json, urllib.request, subprocess

key = subprocess.run(["vault", "get", "gemini/api_key"], capture_output=True, text=True, cwd="/root").stdout.strip()

with open("/tmp/image.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={key}"
payload = {
    "contents": [{"parts": [
        {"text": "Describe what you see in this image."},
        {"inline_data": {"mime_type": "image/png", "data": img_b64}}
    ]}]
}

req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=30)
data = json.loads(resp.read())
print(data["candidates"][0]["content"]["parts"][0]["text"])
PYEOF
```

## List available models
```bash
python3 -c "
import json, urllib.request, subprocess
key = subprocess.run(['vault', 'get', 'gemini/api_key'], capture_output=True, text=True, cwd='/root').stdout.strip()
url = f'https://generativelanguage.googleapis.com/v1beta/models?key={key}'
data = json.loads(urllib.request.urlopen(url, timeout=15).read())
for m in data.get('models', []):
    if 'flash' in m['name'].lower():
        print(m['name'], '->', m.get('supportedGenerationMethods', []))
"
```

## Pitfalls
- Vision tool in Hermes may try the primary model instead of auxiliary model when primary doesn't support vision — this is a routing bug. Direct API call is the workaround.
- Image must be base64-encoded with correct MIME type (image/png, image/jpeg).
- Max image size ~20MB for inline_data. For larger images, use File API.
