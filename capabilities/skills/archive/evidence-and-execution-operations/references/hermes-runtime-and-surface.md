# Hermes runtime and authenticated-surface depth

Use these checks after the umbrella's target, account, authorization, and side-effect boundaries are fixed.

## Target and process boundary

Record the active `HERMES_HOME`, profile, checkout, interpreter, configuration source, process owner, endpoint, browser session, account or tenant, task identity, and rollback input. Re-read them after the change. Keep profile-local skills, plugins, cron references, auth stores, sessions, and derived memory isolated. Restart only the owner of changed code or configuration, then verify process identity, loaded configuration, endpoint, session continuity, and a real Hermes-path canary.

### Delayed background notifications

1. Match a notification to its exact process handle and stage before changing task status; a source-generation heartbeat is not a final-render status.
2. If it contradicts a later result, retrieve that process's current status through `process_manage` with `action='poll'`. Use the verified terminal outcome over delayed or lower-sequence heartbeats, because delivery order need not match execution order.
3. Reuse the terminal outcome for subsequent older notifications from the same handle; do not restart generation, rerender, or resend the master merely to answer stale progress. Give one concise correction when needed, and avoid repeated status commentary that adds no new result.

## Browser and human handoff

Use one canonical supervisor and browser session; serialize restarts and refresh semantic state after navigation or rerender. Bind coordinate evidence to the newest target geometry. During manual intervention, pause agent writes behind a session lock, revoke the lock before resuming, and re-check URL, tab, identity, health, screenshot, and target postcondition.

For React composers, type into the visible editable through real key events, verify visible text and attachment state immediately before submit, and take a fresh snapshot after every rerender. Match exact per-case approval text, close attachment pickers without disturbing the pending state, and poll the conversation or job when a stop icon means work is still in flight.

## Durable Computer Use and remote repair

Keep approvals, action dispatch, session lifecycle, capture, and result shaping in the host. Let an extension select only a named backend or capture strategy, check compatibility without a visible action, and fail closed with `no_target`, `needs_user_input`, or incompatibility instead of guessing. Before remote repair, verify host, cloud scope, service, mounts, and process owner; snapshot first, use a temporary least-privilege path, and remove temporary access after a real login, sync, decryption, or display check.

## Media and file delivery

Trace the recipient path as separate stages: reference interception, URL/path resolution, authenticated byte delivery, MIME and disposition, Range/seek, client rendering, and visible playback or download. A filesystem path, external player URL, stable URL, successful attachment call, or server-side `200/206` proves transport only. Never use `file://` for a remote gateway path. Use a Range-capable stream for playback, an attachment route for downloads, and query tokens only on read-only byte routes; keep listings and text reads header-only.

If the gateway sees zero client requests, diagnose reference resolution or connection mode before auth, size, or codec. If bytes work but the recipient cannot see or play them, inspect renderer and client capability. Rebuild a compiled client or restart the owning server after code changes before claiming the fix is live.

### Private retrieval fallback to an authorized Mac

Use this when Monsieur requests the deliverable but chat retrieval fails and existing SSH access to his Mac is already authorized. Restore access without changing media quality, restarting his application, or publishing a private artifact. This bypass does not diagnose the application's failure.

1. Verify the source exists, record its byte count, and compute SHA-256 through `terminal`; bind any existing QA receipt to those exact bytes. Never regenerate, compress, or transcode solely to fix a download problem.
2. Load `ssh-mac-remote-control` for the connection procedure. Inspect the live SSH configuration and use `tailscale status --json` to identify the intended online Mac, projecting only necessary peer fields. Do not reuse a remembered address or assume a localhost SSH tunnel reaches the client.
3. Probe the chosen SSH route with `BatchMode=yes` and a bounded `ConnectTimeout`. Read the remote `$HOME`, verify Downloads exists, and check destination absence. Keep optional CDP checks separate from this preflight: an absent debug endpoint neither disproves SSH access nor prevents file transfer. A responding CDP port on the server is not proof that the client's Hermes window is reachable.
4. Copy into a uniquely named hidden `.part` file inside the destination's Downloads directory. Check its SHA-256 before publishing it; keep staging and destination on the same filesystem.
5. Publish without clobbering: use a hard link from staging to the final filename, which fails atomically if that filename already exists, and remove staging only after the link succeeds. Read back the exact final path, size, and SHA-256 before reporting success. On collision, preserve the existing file and inspect it or choose a distinct filename; never overwrite blindly.

Command pattern, executed with `terminal` after substituting the verified route and paths; quote dynamic values with `shell_quote` or a subprocess argument list:

```bash
# Linux source: retain the actual digest and byte count.
sha256sum "$source"
stat -c 'bytes=%s' "$source"

# $part is a new absolute path under the Mac's verified Downloads directory.
scp -i "$key" -o BatchMode=yes -o ConnectTimeout=10 \
  "$source" "$mac_user@$mac_ip:$part"

# Remote macOS shell: $part, $dest, and $expected are explicit, safely quoted values.
actual=$(shasum -a 256 "$part")
test "${actual%% *}" = "$expected" || exit 3
ln "$part" "$dest" && rm "$part" && \
  shasum -a 256 "$dest" && stat -f 'bytes=%z path=%N' "$dest"
```

Use the configured trusted host key; where onboarding is explicitly allowed, `StrictHostKeyChecking=accept-new` still rejects a changed key. Do not disable host-key checking to make delivery appear successful.

6. Report the usable destination as **Downloads → filename** and state that the copy is byte-identical. Keep the digest in verification evidence rather than a long user-facing explanation. Claim only the verified local copy, not recipient playback, creative acceptance, or repair of the chat-download path.
