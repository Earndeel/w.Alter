# Previewing local media in Hermes Desktop

Use this when a user cannot open a locally generated MP4 or image from the Hermes Desktop chat or preview pane.

## Procedure

1. **Freeze and verify the artifact.** Resolve the exact local path, confirm it exists, and record size plus `ffprobe` metadata for video. Do not assume a `MEDIA:/tmp/...` path is readable by the renderer just because the file is readable in the terminal.
2. **Try the direct preview once.** Open the exact file with `desktop_preview` and read the result. A raw MP4/WebM may be reported as a file-identity tab rather than a playable element; treat that as a transport/rendering limitation, not as a corrupt video. A `MEDIA:/absolute/path` token is not proof that the renderer has created a player.
3. **Build a local wrapper beside the media.** Write a small HTML page with one `<video controls preload="metadata" src="...">` per requested variant, using relative filenames. Keep the wrapper local, include clear labels, and do not upload the media or expose it through a public URL.
4. **Serve and prove the wrapper.** Pick an unused high port—inspect listeners rather than killing or reusing an occupied port—then start a temporary `python3 -m http.server <port> --bind 127.0.0.1` from the artifact directory. Before opening it in Hermes, verify the HTML and every referenced media variant with `curl -f` or `urllib`, including the exact `Content-Type` (`video/webm`/`video/mp4`) and `Content-Length`.
5. **Open the URL in the actual preview pane.** Use `desktop_preview.open` with the local HTTP URL, then `desktop_preview.read`; the returned visible page text should contain the wrapper title and each version label. This proves the preview reached the intended page, not that the user has watched the full video.
6. **Recover from a namespace mismatch.** If terminal `curl` succeeds but the preview reads a 404 or otherwise cannot see the loopback server, do not relaunch Hermes or guess ports repeatedly. Bind a short-lived server to the machine's private Tailscale address only, e.g. `python3 -m http.server <port> --bind <tailnet-ip>`, verify it locally, and open `http://<tailnet-ip>:<port>/<wrapper>.html` in `desktop_preview`. This is the tested fallback when the preview browser and terminal do not share `localhost`.
7. **Leave the preview usable, then clean up deliberately.** Keep the temporary server alive while the user needs the pane; stop only the server process/session created by this workflow afterward. Never kill broad process patterns or the user's Hermes app. State explicitly if only page reachability and file integrity were verified; do not claim full GUI playback from `desktop_preview.read` alone.

## Minimal wrapper

```html
<video controls preload="metadata" src="variant-a.mp4"></video>
<video controls preload="metadata" src="variant-b.mp4"></video>
```

Use a private, temporary route for the media. A Tailscale-bound listener is preferable to `0.0.0.0`; do not publish the video merely to make a desktop preview work.

## Failure classification

- **Direct file tab:** renderer identified the file but did not create a player; use the wrapper.
- **Terminal works, preview 404s:** preview and terminal are in different network namespaces; use a private interface address.
- **Wrapper text appears in preview:** page routing works; playback and audio still require the user's play action or an independent GUI/video check.
- **Hash/ffprobe/decode failure:** fix the media artifact before debugging Hermes UI.
