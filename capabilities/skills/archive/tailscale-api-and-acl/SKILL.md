---
name: tailscale-api-and-acl
description: Tailscale API (auth keys, device tagging, grants) and ACL syntax — safe edit patterns, field reference, and pitfalls.
category: devops
---

# Tailscale API & ACL

Tailscale API operations (auth keys, device tagging) and ACL policy management. Covers the API access token flow, grant syntax reference, and **safe ACL edit patterns** that won't break connectivity.

## API Flow

### Authentication
API access tokens (Settings → Keys → Generate API Access Token) authenticate via HTTP Basic Auth:
```bash
curl -u "tskey-api-XXXX:" "https://api.tailscale.com/api/v2/tailnet/-/..."
```
The colon after the token IS the password (empty) — required, not optional.

### Generate a reusable auth key
```bash
curl -X POST "https://api.tailscale.com/api/v2/tailnet/-/keys" \
  -u "tskey-api-XXXX:" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": {
      "devices": {
        "create": {
          "reusable": true,
          "ephemeral": false,
          "preauthorized": true
        }
      }
    }
  }'
```
Returns `{"id": "k...", "key": "tskey-auth-..."}`.

### List devices
```bash
curl "https://api.tailscale.com/api/v2/tailnet/-/devices" -u "tskey-api-XXXX:"
```

### Tag a device
```bash
curl -X POST "https://api.tailscale.com/api/v2/device/{deviceId}/tags" \
  -u "tskey-api-XXXX:" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["tag:my-tag"]}'
```
Tag MUST be declared in `tagOwners` in the ACL first, or the API returns:
`"requested tags [tag:X] are invalid or not permitted"`

### Delete an auth key
```bash
curl -X DELETE "https://api.tailscale.com/api/v2/tailnet/-/keys/{keyId}" -u "tskey-api-XXXX:"
```

## ACL Syntax — Reference & Pitfalls

### Valid grant fields
A grant object accepts these fields:
- `src` (array) — source users/tags/autogroups
- `dst` (array) — destination users/tags/autogroups
- `ip` (array) — IP ranges (use `["*"]` for all)
- `srcPosture` (optional) — device posture requirement

### ❌ INVALID fields (Tailscale rejects them)
- `"proto": "tcp"` — **NOT a valid grant field**. Protocol filtering is NOT done in grants.
- Duplicate keys (e.g. two `"dst"` in the same object) — JSON parse error.
- `"ports": ["22", "5900"]` — port filtering belongs elsewhere (host firewall / nodeAttrs), not in ACL grants.

### Tags must be declared BEFORE use
Any tag referenced in a grant (in `src` or `dst`) must be declared in `tagOwners`:
```json
"tagOwners": {
    "tag:w-alter":          ["autogroup:admin"],
    "tag:w-alter-clients":  ["autogroup:admin"]
}
```
Referencing an undeclared tag → `Error: src=tag not found: "tag:X"`

### Safe ACL edit pattern
When tightening ACLs (replacing `* → *` with explicit rules), follow this sequence:
1. **First** — add `tagOwners` declarations only (no grant changes). Save. This is safe and non-disruptive.
2. **Then** — tag the relevant devices via API.
3. **Finally** — replace the `* → *` grant with explicit rules. Now the tags exist, so the new rules resolve immediately.

**Why**: if you replace grants AND add tags in the same save, and the tags aren't applied to devices yet, the new restrictive grants apply before tags are on devices → all connectivity breaks.

### Minimal safe first edit
Just add `tagOwners` to the existing ACL. Everything else stays identical:
```jsonc
"tagOwners": {
    "tag:my-tag": ["autogroup:admin"]
}
```
The `* → *` grant remains in place. No connectivity change. Tags are now valid and can be used in future edits.

## Common error messages decoded
| Error | Cause | Fix |
|---|---|---|
| `requested tags [X] are invalid or not permitted` | Tag not in `tagOwners` | Add tag to `tagOwners` in ACL first |
| `src=tag not found: "tag:X"` | Tag referenced in grant but not declared | Declare in `tagOwners` |
| `duplicate name "dst" in object` | Two `"dst"` keys in same object | Merge into one array, or use correct field name |
| `json: unknown field "proto"` | `"proto"` is not a valid ACL field | Remove it; use host firewall for protocol filtering |
| `unknown posture "posture:X"` | Posture referenced but not defined | Either define the posture or remove `srcPosture` |

See `references/acl-debug-log.md` for the raw session trace of these errors and their resolution sequence.

## Device posture (for reference)
Postures are optional. If not needed, omit `srcPosture` entirely from grants. Postures must be defined in a `"postures"` block when used. For simple setups, skip them.
