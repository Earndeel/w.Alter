# ACL Debug Log — Session 2026-07-05

Real errors encountered while configuring Tailscale ACL for remote Mac access (walter-access package). Tailscale admin console at login.tailscale.com/admin/acl.

## Attempt 1 — proto + dst duplicate
```jsonc
{"src": ["tag:w-alter"], "dst": ["tag:w-alter-clients"], "proto": "tcp", "dst": ["22", "5900"]}
```
Error: `duplicate name "dst" in object (lines 22:4 and 24:4)`

## Attempt 2 — proto field
Fixed duplicate, changed ports to `"ports"`:
```jsonc
{"src": ["tag:w-alter"], "dst": ["tag:w-alter-clients"], "proto": "tcp", "ports": ["22", "5900"]}
```
Error: `json: unknown field "proto"`

## Attempt 3 — srcPosture + unknown posture
Removed proto, added `srcPosture`:
```jsonc
{"src": ["tag:w-alter"], "dst": ["tag:w-alter-clients"], "ip": ["*"], "srcPosture": ["posture:anyMac"]}
```
Error: `grant rule referenced unknown posture "posture:anyMac"` — posture was commented out in the JSON

## Attempt 4 — unknown tag
Removed srcPosture entirely:
```jsonc
{"src": ["tag:w-alter"], "dst": ["tag:w-alter-clients"], "ip": ["*"]}
```
Error: `src=tag not found: "tag:w-alter"` — tag existed in grant but NOT in tagOwners

## Attempt 5 — tagOwners + tag added, connectivity broke
Added `tagOwners` with both tags in the SAME edit that replaced `* → *` with explicit grants. 
Result: ACL saved without error, but w-alter wasn't tagged yet → all connectivity lost. User couldn't reach me, had to revert to default ACL.

## Resolution — two-phase approach
**Phase 1**: Add ONLY `tagOwners` declarations, keep `* → *` grant. Save. Safe.
**Phase 2**: Tag w-alter via API (`POST /device/{id}/tags`). Then replace `* → *` with explicit grants.

## Final working grant
```jsonc
{"src": ["tag:w-alter"], "dst": ["tag:w-alter-clients"], "ip": ["*"]}
```
No `proto`, no `ports`, no `srcPosture`. Just src + dst + ip. Simple and works.
