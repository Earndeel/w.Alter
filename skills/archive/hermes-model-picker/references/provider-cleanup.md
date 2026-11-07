# Protocol-aware provider cleanup example

A vendor may legitimately need more than one `/model` entry when its endpoints speak incompatible protocols.

## Classification example

| Entry role | Transport | Keep separate? |
|---|---|---|
| Claude/Gemini family | `anthropic_messages` | Yes |
| GPT Responses family | `codex_responses` | Yes |
| Local intermediary duplicating the direct Claude route | Same as direct route | Usually remove after dependency check |

## Verification checklist

- Exactly the intended provider IDs remain after parsing the configuration.
- Display names identify model family or capability, not merely the vendor.
- Every provider retains the correct endpoint and transport mode.
- `models` parses as a list, never as a JSON-looking string.
- Run the built-in configuration validator.
- Refresh caches or restart the picker only if stale runtime state remains.

The durable lesson is to consolidate by protocol and role, not by vendor name alone.