# Kie.ai Streaming Diagnostics

## Symptom: "No output" on Claude models via Kie.ai

User selects a Kie.ai Claude model, sends a message, gets no response. Turn ends silently or with a generic error.

## Diagnostic Steps (in order)

### 1. Check routing in logs
```bash
grep "OpenAI client created" ~/.hermes/logs/agent.log | tail -3
```
**Correct:** `provider=kie base_url=https://api.kie.ai/claude model=claude-opus-4-7`
**Broken:** `provider=custom base_url=https://api.kie.ai model=claude-opus-4-7` → routing not applied, URL has no `/claude` suffix.

### 2. Check for stream drop signatures
```bash
grep -E "(Streaming failed|interrupted_during_api_call|RemoteProtocolError|incomplete chunked read)" ~/.hermes/logs/errors.log | tail -5
```
**Signature:** `Streaming failed before delivery: RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)`
**Or:** `interrupted_during_api_call` in turn-end reason with no content delivered.

### 3. Check Cloudflare headers in upstream logs
```bash
grep "upstream.*cf-ray\|cf-cache-status" ~/.hermes/logs/agent.log | tail -3
```
Format: `upstream=[cf-ray=<ID>-<IATA> cf-cache-status=DYNAMIC server=cloudflare]`
The IATA code after the ray ID shows which CF edge served the request (BKK = Bangkok).

### 4. Test non-streaming (always works)
```bash
python3 -c "
import os, requests
r = requests.post('https://api.kie.ai/claude/v1/messages',
    headers={'Authorization': f'Bearer {os.environ[\"KIE_API_KEY\"]}', 'anthropic-version': '2023-06-01', 'User-Agent': 'Mozilla/5.0'},
    json={'model':'claude-opus-4-7','max_tokens':50,'messages':[{'role':'user','content':'Say hi'}]},
    timeout=30)
print(f'HTTP {r.status_code}')
print(r.json().get('content',[{}])[0].get('text','')[:100])
"
```
If this returns HTTP 200 with content → the issue is streaming-only.

### 5. Test streaming (may fail)
```bash
python3 -c "
import os, requests
r = requests.post('https://api.kie.ai/claude/v1/messages',
    headers={'Authorization': f'Bearer {os.environ[\"KIE_API_KEY\"]}', 'anthropic-version': '2023-06-01', 'User-Agent': 'Mozilla/5.0'},
    json={'model':'claude-opus-4-7','max_tokens':50,'stream':True,'messages':[{'role':'user','content':'Say hi'}]},
    timeout=30, stream=True)
print(f'HTTP {r.status_code}')
for i, line in enumerate(r.iter_lines(decode_unicode=True)):
    if line: print(line[:120])
    if i > 5: break
"
```
If this stalls, times out, or raises `RemoteProtocolError` → Cloudflare is killing the SSE stream.

## Root Cause

Cloudflare's edge (especially in SEA region) sometimes drops SSE (Server-Sent Events) streams. The Anthropic Messages API uses chunked transfer encoding — CF closes the TCP connection before the stream completes. This is NOT a Kie.ai application issue; it's a Cloudflare infrastructure behavior.

## Observations (2026-06-10)
- Non-streaming requests to the same endpoint always succeed
- CF `cf-cache-status=DYNAMIC` on all requests (not cached, pass-through)
- The `chunked: true` upstream response is normal for SSE
- Retry helps occasionally (CF may route to a different edge)
- Hermes auto-retries stream failures up to 3 times before giving up

## Workarounds
1. **Hermes auto-retry** (built-in): agent retries 3 times on stream drop
2. **Non-streaming fallback (IMPLEMENTED v1.6):** `agent/conversation_loop.py` forces `_use_streaming = False` when `base_url` contains `api.kie.ai` and `api_mode` is `anthropic_messages`. Response arrives as a single HTTP 200 block. See SKILL.md Fix 5 for the exact code.
3. **VPN/region change**: different CF edge may not exhibit the issue

## Notes
- Thinking/reasoning: Kie.ai proxy filters `thinking` parameters. Never returned regardless of streaming mode. Provider-side limitation.
- The non-streaming fix means no incremental token delivery — user sees full response after ~15-20s generation completes.
