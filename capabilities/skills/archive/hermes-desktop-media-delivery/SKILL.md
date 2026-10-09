---
name: hermes-desktop-media-delivery
description: Use when media won't show or download in Hermes Desktop.
---

# Hermes Desktop media delivery

A MEDIA tag delivers a REFERENCE, not bytes. The renderer must resolve that
reference against the session backend before anything appears. Every symptom
Monsieur reports as "invisible" or "can't download" is the same failure seen at
two different points of one chain.

## The chain (trace it in this order)

1. `agent/prompt_builder.py` - the `desktop` platform block PROMISES inline
   rendering. No Python adapter intercepts MEDIA on desktop; the renderer owns it.
2. `apps/desktop/src/lib/chat-messages/parts.ts` - `renderMediaTags` rewrites the
   media tag into a `#media:` markdown link. Streamed text is re-rendered per delta.
3. `apps/desktop/src/components/assistant-ui/markdown-text.tsx` - `MarkdownLink`
   to `mediaPathFromMarkdownHref` to `MediaAttachment`.
4. `MediaAttachment` calls `resolveMediaPlaybackSrc` for the video src and
   `useOpenMediaFile` for the download. BOTH resolve the same gateway path.

Read `apps/desktop/src/lib/media.ts` before theorising - it is the whole surface.

## Rules

- **Check the server before the renderer.** Serve the file with curl and read
  status, content-type, content-disposition and Range/206 behaviour. A healthy
  backend plus a broken card isolates the fault to path resolution in the app.
- **Look for app traffic in the gateway access log before blaming auth.** Zero
  requests from the app to /api/files or /api/fs means the app never asked - it is
  reading a local path and failing before any network call. Do not debug tokens.
- **A zero-request log usually means local mode.** When connection mode is not
  `remote`, `mediaStreamUrl` hands `hermes-media://stream/` to `readLocal`, which
  reads the app's OWN disk. A gateway path like /root/output does not exist
  there, so nothing renders and nothing downloads. Ask Monsieur to confirm the
  connection is still declared remote.
- **Read the component's own error text as a hypothesis list.** `OpenMediaFailedNote`
  prints "missing, unreadable, or too large" - three named causes, test each.
- **Check `_FS_DATA_URL_MAX_BYTES` in `hermes_cli/web_server.py` before blaming
  size.** It is 16 MiB, while `_MANAGED_FILE_MAX_BYTES` is 100 MiB. Clips of 3-10
  Mo sit under the data-URL cap, so "too large" is often NOT the cause.
- **Deliver media inline in the conversation FIRST.** Monsieur's accepted state is
  "see it and download it in the conv". An external URL or a hand-rolled player
  page is a stopgap to mention after, never the delivered answer.
- **Send both MP4 and WebM.** WebM plays where MP4 does not (local Chromium lacks
  H.264/AAC). State which is the master and which is the fallback.

## Pitfalls

- `MEDIA_LINE_RE` needs the tag on its own line; an inline tag falls back to
  `MEDIA_TAG_RE`.
- `/api/files` and `/api/fs/list` are LISTINGS and must never accept a query token -
  a listing in a Referer broadcasts the bearer. Widen only read-only byte routes.
- A 404 on /api/files means the wrong port. The gateway (8642/8644) does not serve
  those routes; the dashboard web server does. Never read a 404 as auth.
- Query-token auth exists because a video src, an anchor download and OS-shell-opened
  links have NO header channel. That is a design fact, not sloppiness.
- `mediaExternalUrl` rewriting a gateway-owned path to file URL yields a dead link
  on any machine that is not the gateway - that is the "can't download" symptom.

## Verification

Prove delivery, never assert it. Start a probe dashboard with a known
`HERMES_DASHBOARD_SESSION_TOKEN`, then curl the matrix and check all of it.

- media via query token to 200 with correct MIME, `inline` for stream and
  `attachment` for download
- `Range: bytes=N-M` to 206 with the right slice and no header set
- listings /api/files and /api/fs/list, plus /api/files/read and POST upload to 401
- no token at all to 401 on every media route

Run `tests/hermes_cli/test_web_server_files.py`, and `npx tsc -p . --noEmit` in
`apps/desktop` after touching `media.ts`.

## Regression framing

Monsieur reports breakage against a remembered working state ("avant ca marchait
niquel"). Answer the regression question explicitly - what changed between the
working and broken state. Git history on the chain above is the fastest answer; a
run-forever gateway serving pre-update modules is the second most likely one.

**Read co-symptoms before treating media as an isolated bug.** An app that also
drops older conversations from its session list is in a degraded STATE - version
skew between the desktop binary and the backend, or a lapsed remote connection.
Fix the state first; a media-only patch then appears to do nothing.
