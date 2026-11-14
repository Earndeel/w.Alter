# Hermes runtime and authenticated-surface depth

Use these checks after the umbrella's target, account, authorization, and side-effect boundaries are fixed.

## Target and process boundary

Record the active `HERMES_HOME`, profile, checkout, interpreter, configuration source, process owner, endpoint, browser session, account or tenant, task identity, and rollback input. Re-read them after the change. Keep profile-local skills, plugins, cron references, auth stores, sessions, and derived memory isolated. Restart only the owner of changed code or configuration, then verify process identity, loaded configuration, endpoint, session continuity, and a real Hermes-path canary.

### Delayed background notifications

1. Match a notification to its exact process handle and stage before changing task status; a source-generation heartbeat is not a final-render status.
2. If it contradicts a later result, retrieve that process's current status through `process_manage` with `action='poll'`. Use the verified terminal outcome over delayed or lower-sequence heartbeats, because delivery order need not match execution order.
3. Reuse the terminal outcome for subsequent older notifications from the same handle; do not restart generation, rerender, or resend the master merely to answer stale progress. Give one concise correction when needed, and avoid repeated status commentary that adds no new result.

## Strict existing-session and addon audits

Use this procedure when only existing configuration may be inspected and searches, playback, downloads, or account/addon changes are outside scope.

1. Load the relevant connector and identify the smallest existing source: a known current tab, an already-connected device, or an exact saved profile. Keep discovery scoped to that service; do not inventory every module, browser, or project to answer a bounded configuration question. Check a CLI's documented contract before invoking it: a help-looking argument is not a guarantee of a non-mutating help path.
2. Prefer an already-authorized local read when it answers the question without an external request. For an existing SSH route, use `BatchMode=yes`, a bounded `ConnectTimeout`, `ClearAllForwardings=yes`, and the configured trusted host key. Run the parser on the source host and return only its allowlisted projection; do not copy or print the raw configuration. A saved file is snapshot evidence, not proof of a usable authenticated session.
3. For an Android Stremio shared-preferences XML file, parse the XML element named `profile`, then JSON-decode its text and read the nested `addons` list. The notation `profile.addons` describes this nested field; it is not necessarily an XML preference key. Read only the profile field, not library, stream-history, or player-state fields. The verified schema extraction is:

   ```python
   import json
   import xml.etree.ElementTree as ET

   root = ET.fromstring(raw_xml)  # existing bytes, held only in local memory
   node = next((e for e in root if e.attrib.get("name") == "profile"), None)
   profile = json.loads(node.text) if node is not None and node.text else None
   addons = profile.get("addons") if isinstance(profile, dict) else None
   # Missing/wrongly typed addons means schema unavailable, not an empty account.
   ```

4. Inspect each addon's `manifest.resources` locally: a stream resource may be the string `stream` or an object with `name == "stream"`. Match manifest names to a small canonical allowlist before returning them; do not emit arbitrary custom names, manifest IDs, descriptions, or transport addresses. Return an unnamed/unrecognized addon indicator when a name cannot be safely projected rather than silently dropping it.
5. Check integration configuration without calling the addon. A service name in a label is weaker than a selected provider with a nonempty required setting. Addon transport paths may contain URL-encoded options or a URL-safe-base64 JSON object: decode only these bounded configuration segments locally, inspect keys/values in memory, and emit booleans only. TorBox selection with a nonempty required setting proves saved configuration, not key validity, cached availability, successful playback, or present use.
6. Distinguish private-tracker evidence from aggregator presence. An aggregator name, a torrent-capable addon, or the absence of recognizable private-tracker markers cannot establish whether private trackers are used behind another service. Report explicit configured evidence if present; otherwise say not established. Do not query an indexer, request sources, follow magnets, or probe playback to improve confidence in a configuration-only audit.
7. Verify evidence boundaries before closing: record when the source was observed and any source-reported synchronization timestamp; describe filesystem modification time only as file metadata. A cached profile, a live device read, and an authenticated account response have different freshness and authority. If no permitted live-session check succeeded, report current access as unconfirmed, not impossible. Once the bounded finding is supported, stop rather than expanding into credential recovery or infrastructure diagnosis.

For a names-only result, use compact prose: access status; relevant addon names with snapshot/live evidence; integration configuration versus actual-use uncertainty; private-tracker evidence status. Never include account identifiers, addon URLs, credentials, passkeys, or personal media names, even as supporting citations.

## Read-only networked Android and HDMI-CEC power diagnostics

Use this branch for a TV dongle that appears off or fails to wake. Load the device-maintenance connector first, then separate host reachability, ADB authorization, Android wakefulness, display state, CEC traffic, and keep-alive locks. A reachable shell does not establish a lit screen, and a powered device can have its display asleep.

### Locate and identify without waking

1. Inspect the maintenance helper's source before invoking it. Do not run an `ensure`, restore, playback, TV-on/off, or status wrapper that reconnects, writes a wake lock, changes settings, or launches an activity; its name does not establish observational behavior.
2. Use the authorized Mac as the LAN vantage point. Inspect its live interface and route, then test only known candidate addresses and the ADB port. Do not reuse a remembered DHCP address as current identity or widen to unrelated LAN devices. Read-only macOS command patterns, through the trusted SSH route, are:

   ```bash
   /sbin/ifconfig en0
   /sbin/route -n get "$candidate"
   /usr/sbin/lsof -nP -iTCP:5037 -sTCP:LISTEN
   /usr/bin/nc -z -G 1 "$candidate" 5555
   ```

   Replace the interface with the observed active LAN interface. An open port identifies a candidate, not the dongle.
3. Inspect `adb devices -l` only after checking that the existing ADB server is running; avoid implicitly starting or restarting it in a strict no-change audit. An empty list means this server has no listed device transport, not that the dongle is off. Where the maintenance implementation already provides an authenticated direct ADB transport, reuse it with the existing authorized key and read-only shell requests. Keep private-key bytes inside the source process. Do not enroll a new key or provoke an authorization prompt to finish a read-only task; report authorization as a limit if it cannot be established quietly.
4. Confirm identity with scoped `getprop ro.product.model`, `getprop ro.product.device`, and `getprop ro.build.version.sdk`. Treat a displayed Android version as a separate claim from the API level; vendor firmware may disagree. Do not return raw property dumps containing identifiers or unrelated data.

### Collect the evidence before interpreting it

Through the already-authorized transport, collect these reads; `$target` and `$package` must come from live identity and the maintenance connector, not remembered defaults:

```bash
adb -s "$target" shell dumpsys power
adb -s "$target" shell dumpsys hdmi_control
adb -s "$target" shell dumpsys activity services "$package"
adb -s "$target" shell dumpsys package "$package"
adb -s "$target" shell dumpsys wifi
adb -s "$target" shell dumpsys deviceidle
adb -s "$target" shell settings get system screen_off_timeout
adb -s "$target" shell settings get secure sleep_timeout
adb -s "$target" shell settings get global hdmi_control_enabled
adb -s "$target" shell settings get global hdmi_control_auto_wakeup_enabled
adb -s "$target" shell settings get global hdmi_control_auto_device_off_enabled
adb -s "$target" shell getprop persist.sys.hdmi.keep_awake
adb -s "$target" shell date -u
adb -s "$target" shell getprop persist.sys.timezone
adb -s "$target" shell cat /proc/uptime
```

Project outputs on the source side: retain power fields, relevant CEC history, package versions/update times, service foreground state, named locks and exemptions; discard Wi-Fi names, addresses, identifiers, and unrelated package or activity contents. Read logs with `logcat -d`, never clear them. Find the actual logging tag in the service source rather than assuming its Java class name is the tag. A filtered log with no matches does not establish that the service never ran.

### Interpret each layer separately

- Compare `mWakefulness`, `Display Power: state`, `mIsPowered`, `mLastSleepReason`, and `mLastSleepTime`. `Asleep` plus display `OFF` and a working shell supports display/framework sleep, not electrical power loss. A sleep reason of `hdmi` is stronger evidence for the last transition than an idle-timeout setting.
- Decode CEC direction and opcode, not just the label. `0F:36` is a broadcast Standby from logical address 0, normally the TV. Correlate that received frame with the power-manager sleep entry before attributing the transition. An enabled auto-wakeup setting expresses policy, not receipt of a wake command or a successful wake. An inactive source is a separate observed state.
- State the CEC history's retention boundary. No later wake frame in a bounded history means only that none is present in the retained evidence; it does not prove that the TV never transmitted one. Do not probe by injecting CEC, toggling power, or pressing a key in read-only mode.
- Verify KeepAlive's package presence, stopped state, foreground service, actual `PARTIAL_WAKE_LOCK`, Wi-Fi lock, and idle exemption independently. Inspect its implementation: a CPU/Wi-Fi keep-alive can work correctly while the display sleeps. Do not describe such a service as a screen-wake guarantee or treat a kernel wake-lock permission denial as proof the lock is absent.
- Record vendor-property values exactly, but do not infer a causal mechanism or change history from a property name such as `keep_awake`. Require implementation evidence or a historical readback before calling it the regression.
- Sample UTC wall time, device timezone, and uptime near the power dump. Label any sleep-time reconstruction as an estimate; use matching clock domains and corroborating wall-clock logs before presenting it as exact. Timezone conversion alone cannot repair clock jumps, suspend accounting differences, or device-clock drift.

### Check changes and close narrowly

Read installed package versions and last-update times, then inspect scoped `GIT_OPTIONAL_LOCKS=0 git log`, `git show`, and diffs for the launcher, keep-alive service, TV-on/off helpers, and restore path. Compare a preserved original source with the current source when available. Search for power/window flags, wake-lock acquisition, CEC calls, sleep commands, and package removal. An IP-only or artwork-only diff is not power-management evidence. Source capabilities and repository commits do not prove deployment or execution; keep those claims separate.

Finish with the supported diagnosis first, then exact decisive fields, code-change evidence, and unresolved limits. Keep the long command transcript out of the answer unless requested. State whether a screen observation, power-cycle reproduction, wake-command receipt, deployed-binary comparison, or permission-limited kernel read remains unverified. Do not notify another channel merely because a diagnostic finished.

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
