# Media and file delivery chain

Depth for the media/file delivery branch. Follow the chain to find which stage owns a
symptom before changing code.

## Resolution chain

```
assistant text contains MEDIA:/abs/path
  -> per-surface interception (see below)
  -> markdown link  #media:<urlencoded path>
  -> markdown link renderer
       mediaPathFromMarkdownHref(href)
       mediaKind(path)  = image | audio | video | file
         'file' (or .md doc) -> preview / file-card pipeline
         image|audio|video   -> MediaAttachment
  -> MediaAttachment
       resolveMediaPlaybackSrc(path) -> <video>/<audio> src     [visibility]
       useOpenMediaFile(path)        -> download / open action  [download]
```

Both the player and the download action resolve **independently**. One can work while the
other is dead, so test both.

## Which layer intercepts `MEDIA:`

| Surface | Interception | Consequence |
|---|---|---|
| desktop / web UI | renderer (markdown link -> attachment component) | file must be resolvable by the client at view time |
| chat platforms (Telegram, Discord, iMessage, SimpleX, ...) | platform adapter, uploads natively | voice extensions may be sent as voice notes |
| CLI, TUI | **none** | the tag prints as literal text; state the absolute path or a URL instead |

Before emitting a `MEDIA:` tag, confirm the active surface actually intercepts it. On a
non-intercepting surface the tag leaks a raw host path and delivers nothing.

## URL builders and their traps

| Builder | Intended use | Trap |
|---|---|---|
| gateway `download` route | save to disk / open in shell | `attachment` disposition; right for download, wrong as a player `src` |
| gateway `stream` route | inline playback | must be Range-capable (`206`, `Accept-Ranges`); use this for `src` |
| whole-file data URL | small inline preview fallback | hard byte cap and non-seekable; anything larger fails silently |
| `file://` | local mode only | **dead link whenever the path lives on a remote gateway** |
| custom app protocol | client-local or proxied streaming | needs the desktop bridge; unregistered in a plain browser surface |

### Query-token allowlist

Media elements and shell-opened links cannot set the session header, so byte-delivery GET
routes must also accept `?token=`. Widen the allowlist to cover the stream, download and
image-byte routes — not only one of them — and never to listing or text-read routes: a token
broadcast through `Referer` on a listing would leak a directory.

## Symptom -> cause

| Observed | Meaning | Where to look |
|---|---|---|
| Nothing at all appears | reference not converted or not routed | surface interception; `mediaKind()` classification; link encode/decode round-trip |
| Label + dead "Open" button | reference resolution failed and the UI degraded on purpose | the URL builder for that path; `file://` trap; local-vs-remote connection mode |
| Player shows but cannot seek / stalls on big files | non-Range, size-capped source | switch playback to the stream route |
| Player works, download does not | download action resolves differently from `src` | the download/open action's URL builder |
| Works in one client, not another | surface does not intercept, or client binary predates the fix | interception table; rebuild / restart requirement |
| Server returns the bytes fine via curl but the user sees nothing | transport layer only is proven | check the client actually issued a request (below) |

## Decisive diagnostic: did the client ever ask?

Grep the gateway access log for **client-originated** requests to the media/byte routes
(exclude your own probes by user-agent). Interpret before touching anything:

- **zero requests** -> the client failed before the network: reference resolution, path
  resolution, or connection mode (for example reading a gateway path from its own local
  disk). Auth, size caps and MIME are not involved.
- **401** -> credential transport (header vs URL token) or expired session.
- **404** -> wrong route/port: the request reached a listener that does not serve the file
  API. Confirm which port exposes the file routes before debugging auth.
- **200/206** -> server side is proven good; the fault is client rendering or codec support.

This one check separates half the failure space and is worth running first.
