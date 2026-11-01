# Kie.ai / Hermes CLI Reproduction Notes

## What was verified
- `api_mode: anthropic_messages` with `base_url: https://api.kie.ai/claude` is accepted by Hermes' Anthropic transport.
- A direct Python `AIAgent` run works when streaming is disabled (`agent._disable_streaming = True`).
- `hermes chat -p kie-claude` still fell back when Hermes treated the Kie.ai response as empty/malformed even though the HTTP request returned `200 OK`.

## Useful reproduction commands
```bash
# Hermes CLI repro
hermes chat -p kie-claude -q "Say hello in exactly 3 words" -v

# Direct non-stream check (works)
python3 - <<'PY'
import sys
sys.path.insert(0, '/root/.hermes/hermes-agent')
from cli import HermesCLI
from run_agent import AIAgent
cli = HermesCLI(model='claude-opus-4-6', provider='custom', base_url='https://api.kie.ai/claude', api_key='…')
agent = AIAgent(base_url='https://api.kie.ai/claude', api_key='…', provider='custom', api_mode='anthropic_messages', model='claude-opus-4-6', quiet_mode=True)
agent._disable_streaming = True
print(agent.run_conversation('Say hello in exactly 3 words')['final_response'])
PY
```

## Current diagnosis
- The original `AssertionError` was tied to the streaming parser.
- Disabling streaming avoids the assertion.
- Hermes CLI still appears to reject/ignore the returned non-stream response (`Model: None, Usage: None`) and activates fallback, so the remaining bug is in response validation/normalization on the CLI path, not auth or endpoint reachability.

## Practical takeaway
If you revisit Kie.ai support later, start by checking whether the CLI path needs a Kie.ai-specific response normalization or a provider-specific non-stream fast path rather than more transport tweaks.