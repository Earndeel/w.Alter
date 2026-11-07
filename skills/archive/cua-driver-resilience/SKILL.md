---
name: cua-driver-resilience
description: "Use when CuaDriver/AX capture or window targeting degrades."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [computer-use, cua-driver, accessibility, ax, capture, macos, resilience]
    category: desktop
    related_skills: [computer-use, mac-computer-use-ssh, ssh-mac-remote-control]
---

# CuaDriver resilience and AX-first validation

Use this skill when Hermes drives a desktop through CuaDriver and a capture is
black, partial, geometrically wrong, stale, or inconsistent with the reported
TCC permissions. It covers the driver/AX route, not generic browser scraping
and not the legacy v7 screen server except as a passive diagnostic fallback.

The invariant is simple: **never turn a permission boolean or a non-empty
payload into proof that the pixels and target are usable**. Capture integrity,
AX usability, and target identity are three separate verdicts.

## 1. Separate the three contracts

Treat these as independent:

1. **TCC authority** — `accessibility` and `screen_recording` indicate that the
   CuaDriver daemon has the relevant authorization identity.
2. **Capture integrity** — `screenshot_frame_valid`, `screenshot_error`, and
   capture coverage indicate whether the returned pixels match the requested
   window.
3. **AX target validity** — the current window exists, its AX tree is fresh,
   and its element indices/tokens belong to that snapshot.

`screen_recording=true` with `screen_recording_capturable=null` means “the
permission is granted but the direct capability probe was not run”; it is not a
successful screenshot verdict. Do not trigger a direct probe merely to fill in
the field when the probe can open a macOS consent dialog. Prefer a normal,
non-prompting `get_window_state` and inspect its explicit frame verdict.

## 2. Read-only diagnosis first

Before changing code or interacting with the user's desktop:

1. Call `check_permissions` with prompting disabled and direct probing disabled.
2. Call `list_windows` with `on_screen_only=true`.
3. Select a real application window, not the driver's own authorization
   window. CuaDriver may intentionally refuse operations targeting itself.
4. Call `get_window_state` for that exact `(pid, window_id)` and request a
   screenshot only when the validation requires pixels.
5. Record only structured facts: frame validity, error code, element count,
   bounds, and whether an image was present. Do not persist screenshots or
   credentials in the skill/reference.

A read-only call with `include_screenshot=false` can return
`screenshot_frame_valid=null`; that is expected and cannot prove pixel health.
For an AX-first route, prefer this flag deliberately and do not create a
temporary screenshot file in the CLI fallback. Request pixels only for SOM,
vision, scoped-region perception, or a pixel action that has a valid capture
basis.

## 3. Normalize driver response shapes

CuaDriver/MCP/CLI bridges have emitted the same semantic response in several
containers:

- `structuredContent` containing `elements`, `tree_markdown`, and screenshot
  diagnostics;
- direct top-level fields from the native CLI;
- a CLI wrapper with `structuredContent` plus `data`/`images`.

The backend must read all supported envelopes through one normalizer. Do not
assume `data` exists, and do not treat a result as empty just because its
image is absent.

For `get_window_state`:

- preserve a top-level or structured `elements` list;
- preserve `screenshot_error`, `screenshot_frame_valid`, and coverage even when
  no PNG exists;
- use `tree_markdown` when present;
- only fall back to parsing markdown when the structured `elements` key is
  absent. An explicit `elements=[]` is a meaningful “no elements” verdict;
  parsing an `AXWindow` line into a fake actionable element hides the failure.

Keep this normalization behavior covered by hermetic fixtures for both direct
and `structuredContent` envelopes. See
`references/cua-driver-capture-integrity.md` for the observed response shape.

## 4. Make capture integrity explicit and fail closed

The capture result should expose optional, additive fields such as:

- `capture_valid: bool | None`;
- `capture_error: dict | None`;
- `capture_coverage: dict | None`.

Use this decision table:

| Driver evidence | `capture_valid` | Action |
|---|---:|---|
| `screenshot_frame_valid=true` | `true` | image may be delivered if otherwise usable |
| `screenshot_frame_valid=false` | `false` | omit image from multimodal payload; expose error |
| explicit `screenshot_error` without boolean | `false` | same; do not retry blindly |
| no diagnostic (old driver) with an image | `None` | retain legacy behavior, but label unknown |
| no diagnostic and no image | `None` | use the existing transport fallback path |

An invalid image must never be sent to the vision model as if it were a
verified screen. A known frame error is not the same as an empty bridge
response: do not re-fetch through another transport merely because the image
is missing. Retry only for an imageless response with no explicit integrity
verdict.

AX and pixels can fail independently. If an AX/SOM capture has
`capture_valid=false` but still contains a non-empty structured AX tree, keep
the tree available for semantic diagnostics, but tell the caller that pixels
are invalid. If it has no AX elements, clear the active target so a subsequent
click cannot reuse a locked or stale context. Do not clear a valid target for a
`vision` capture solely because vision mode intentionally omits AX elements.

## 5. Select windows by identity and substance

`z_index` is useful but not sufficient. macOS applications can expose a
small title-bar/toolbar helper window above the real application surface. A
higher-z row with bounds such as `1440x44` can produce `px_frame_mismatch`,
while the lower-z main window (`1440x900`) is valid.

Selection rules:

1. Remove explicit off-screen rows for live capture.
2. Preserve the exact `(pid, window_id)` when the caller intentionally pinned
   a target; never silently substitute a different window.
3. Preserve window `bounds` during normalization. If geometry is known and a
   substantive on-screen surface exists, prefer windows with meaningful
   dimensions (for example, at least a normal content-height and width) over
   chrome strips.
4. Keep the old ordering behavior when geometry is absent; old driver payloads
   must not be penalized for missing metadata.
5. If every candidate is off-screen or invalid, return “no target” and clear
   active targeting. Never recycle the first stale row.
6. After every state-changing action, use a fresh capture. Element indices and
   opaque tokens belong to one snapshot only.

Do not solve a wrong-window diagnosis by switching to pixel coordinates. Fix
target identity first; coordinate fallback is only valid after a fresh,
verified surface has been selected.

## 6. Safe live validation

When a real interaction is required, use a disposable session identifier:

1. `start_session({"session": "<new-id>"})` rather than reusing an ended ID.
2. `list_windows(on_screen_only=true)` and choose the main application window
   using app identity plus bounds.
3. Capture with pixels and require `screenshot_frame_valid=true` before acting.
4. Pick a harmless, reversible control that is not personal content, payment,
   authentication, permission, or browser research. Record its index/label.
5. Click via AX element index/token, capture again, and verify the expected
   state transition.
6. Restore the original state, capture once more, and verify the restoration.
7. Always call `end_session`, including after an aborted validation.

If the pre-action capture is `px_frame_mismatch`, stop before the click. If
CuaDriver refuses its own authorization window, treat that as a safety
boundary and retarget the application window; do not bypass it.

## 7. CuaDriver 0.17 action contract

The CLI/MCP bridge is strict about snapshot binding. A current `get_window_state`
returns both a `snapshot_id` such as `s0000001f` and an opaque
`element_token` such as `s0000001f:2`.

- Prefer `element_token` from the current snapshot, together with the exact
  `pid`, `window_id`, and session.
- Alternatively pass `element_index` **and** the same `snapshot_id` from which
  that index came. A bare `element_index` is refused with
  `snapshot_id_required`; a field named `token` is not the accepted parameter
  for the strict CLI.
- After every attempted mutation, take a fresh state snapshot before retrying
  or selecting another element. Repeated numeric indices do not make a token
  reusable: labels, visibility, and target binding may have changed.

The dispatch result may be `effect: "unverifiable"` even when the mutation
landed. Treat that as an instruction to inspect, not as success or failure:
compare the expected AX label/value/frame in a fresh snapshot. If the expected
state is unchanged after a background action, escalate that same action once to
`delivery_mode: "foreground"`; verify the resulting state again. Foreground
can also remain `unverifiable`, so the read-back is the proof.

For disposable native-app probes, `launch_app` may report
`process_running=true` while `window_ready=false` and return no windows. Poll
`list_windows` against a readiness predicate, then require a substantive
on-screen window and a resolved AX tree before acting. `bring_to_front` returning
`activated=true` is not sufficient if `list_windows` still marks the window
off-screen or `get_window_state` returns `ax_window_unresolved`; fail closed,
clean up the disposable app through its native quit path when possible, end the
CuaDriver session, and restore the user's prior application.

See `references/live-ax-validation.md` for a sanitized execution record and
compact verification recipe.

## 8. Validate remote browser tasks by intent, not by process state

For a native request involving a named browser and a page-level selection:

1. Honor the browser named by the user. A remembered preference for another
   browser is not an override; Safari, Brave, Chrome, and Firefox are distinct
   targets.
2. If the task is only “launch the named browser at a URL,” prefer the
   deterministic remote URL-launch path when its transport is healthy, then
   verify the resulting browser window with `list_windows` and a fresh AX
   capture. A process listed as running without a substantive window is not
   completion.
3. Before selecting “the first video,” verify that the current page exposes an
   actual video card/link or an equivalent labelled target. An empty state such
   as “Try searching to get started” is evidence that there is no first video;
   do not click Home, Search, or an unrelated element to manufacture one.
4. Treat `effect: "unverifiable"` as a read-back requirement, not as permission
   to repeat the action. Capture fresh state first and retry only if the
   expected transition is absent and the escalation ladder authorizes it.
5. If pixels are invalid but AX is coherent, semantic actions can still be
   used for explicitly labelled, reversible controls; they do not establish
   visual content identity. Never claim a content selection from a toolbar or
   page title alone.

Keep this acceptance logic separate from browser scraping: the user's visible
native-browser request is a Computer Use task, while public-web extraction
should use the web front door. See `references/remote-browser-task-acceptance.md`
for the compact evidence pattern and sanitized reproduction notes.

## 9. Regression test matrix

Add behavioral tests, not source-shape tests:

- direct top-level `get_window_state` with AX elements and a frame error;
- structured-content response with the same diagnostics;
- explicit `elements=[]` does not fall back to an `AXWindow` markdown line;
- invalid frame metadata is surfaced and the image is omitted;
- known invalid capture does not invoke the CLI retry;
- invalid AX capture with no elements disarms the active target;
- all-off-screen candidates return no target;
- a higher-z chrome strip loses to a substantive main window when bounds are
  available;
- old payloads without bounds retain existing selection behavior.

Run the repository's CI-parity wrapper (`scripts/run_tests.sh`) for the
Computer Use files, then run the broader tool suite. Record the actual counts
and distinguish tests run before a final selector change from tests run after
it.

## Pitfalls

- Granted TCC is not proof of a valid frame.
- `screen_recording_capturable=null` is “not checked”, not “working”.
- A missing `data` key is not automatically a failed capture.
- An explicit empty structured element list must not be replaced by markdown
  pseudo-elements.
- Do not use an expired session ID; start a new one.
- Do not target the CuaDriver authorization window itself.
- Do not launch a consent-producing capture probe during unattended diagnosis.
- Do not use the user's Brave or Mac desktop for unrelated scraping/research;
  keep Computer Use scoped to the actual desktop task.
- Do not claim the final fix is verified until tests have run after the last
  selector or capture change.

## Supporting reference

See `references/cua-driver-capture-integrity.md` for the compact evidence
record, response fields, and a sanitized reproduction checklist.
