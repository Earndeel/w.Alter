# Browser media preview and codec fallback

Use this reference when a generated video is reachable in a desktop/web preview but the player is blank, has no controls, or will not start.

## Decision procedure

1. Preserve the verified master; never transcode over the only copy.
2. Serve a local wrapper from the directory containing the media and verify the HTML plus every source with `curl` or an equivalent HTTP client. Record status, `Content-Type`, and `Content-Length`.
3. Probe the same browser engine that matters for playback. For each `<video>`, collect:
   - `canPlayType('video/mp4; codecs="avc1.64001f, mp4a.40.2"')`
   - `canPlayType('video/webm; codecs="vp9,opus"')`
   - `readyState`, `networkState`, `videoWidth`, `videoHeight`, `duration`, `currentSrc`
   - `video.error.code` and `video.error.message`, when present
4. Treat only a finite duration, non-zero dimensions, `readyState >= 3`, and no media error as playback evidence. A visible wrapper title, a successful HTML request, or a preview-pane text read is not enough.
5. If MP4 support is empty or the engine reports `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, encode a browser fallback while retaining the MP4 master:

```bash
ffmpeg -y -i input.mp4 \
  -c:v libvpx-vp9 -crf 32 -b:v 0 -deadline good -cpu-used 4 -row-mt 1 \
  -c:a libopus -b:a 128k -f webm output.webm
```

6. Put WebM first and MP4 second in the wrapper. Include `controls`, `playsinline`, `preload="auto"`, explicit dimensions/aspect ratio, and a poster so the page remains visually useful before playback:

```html
<video controls playsinline preload="auto" poster="poster.jpg" width="360" height="640">
  <source src="variant.webm" type="video/webm">
  <source src="variant.mp4" type="video/mp4">
</video>
```

   Read back the emitted HTML or inspect the DOM before testing playback; the `type` attributes must contain literal markup, not backslashes leaked from a programming-language string escape. `networkState=3` with an empty `currentSrc` means no `<source>` candidate was accepted, so repair the wrapper syntax before changing codecs, URLs, or servers.

7. Reopen the updated wrapper with a cache-busting query parameter. Re-run the browser probe and verify that `currentSrc` resolves to the intended fallback and that the encoded WebM itself passes `ffprobe` and a complete decode.
8. Deliver both the production MP4 and the compatibility WebM when the recipient may need the original file. Verify remote copies by hash; do not claim recipient playback from transport or page reachability alone.

## Common interpretation

| Observation | Meaning | Action |
|---|---|---|
| HTML 200, labels visible, media error absent from the text-only preview | Wrapper is reachable; playback is unproven | Run the browser probe |
| `canPlayType(MP4) == ''`, WebM is `probably` | Target engine lacks that MP4 codec | Encode VP9/Opus and list it first |
| `readyState == 4`, dimensions and duration are valid | Browser loaded the media | Ask the recipient to press play or verify via GUI; keep the master |
| Poster appears but `readyState == 0` | Poster works, media does not | Inspect source URL, range responses, and codec error |
| Hashes differ after remote delivery | Copy is not verified | Re-transfer; never report delivery success |
