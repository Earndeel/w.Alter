# Visible provider-watermark removal from generated video

Use this workflow only for a user-owned/generated asset when the requested change is a **visible overlay** (for example, a fixed Gemini/Flow sparkle). Preserve the original and keep scene-generated text/logos separate from the provider watermark unless the user explicitly asks to remove those too.

## Procedure

1. **Inspect before editing**
   - Run `ffprobe` on the source and record duration, dimensions, streams, codec, and frame rate.
   - Extract representative frames from the beginning, middle, end, and any suspected transition.
   - Build a labeled contact sheet and inspect the full frame plus the affected corner with vision.
   - Identify the watermark's fixed coordinates and determine whether it disappears before an outro/logo card. A time-limited filter is safer than masking the entire video.

2. **Test the removal method on stills first**
   - A broad `delogo` rectangle can leave a conspicuous rectangular smear, especially over hands, foliage, or textured metal.
   - Prefer FFmpeg `removelogo` with a bitmap mask shaped around the overlay (not a large rectangle). A four-point sparkle mask with a small margin is usually less destructive.
   - Use the `enable` timeline expression when the provider watermark ends before generated scene text/logo content, for example:
     ```bash
     -vf "removelogo=f=/path/to/mask.png:enable='lt(t,18.65)'"
     ```
   - Compare source/result crops at both watermark-heavy frames and the first frame after the cutoff. Reject the result if a rectangular patch or obvious scene damage remains.

3. **Render a separate copy**
   ```bash
   ffmpeg -hide_banner -loglevel warning -i source.mp4 \
     -map 0:v:0 -map 0:a? \
     -vf "removelogo=f=/path/to/mask.png:enable='lt(t,CUTOFF)'" \
     -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
     -c:a copy -movflags +faststart output_watermark_removed.mp4
   ```
   Keep the source untouched and use a new filename. Do not claim that invisible provenance markers such as SynthID were removed; this procedure addresses visible pixels only.

4. **Validate the actual output**
   - Run `ffprobe` again and require a real video stream, unchanged dimensions/aspect ratio, expected duration, and readable audio when present.
   - Inspect a full-frame contact sheet and affected-area contact sheet. Check for watermark remnants, inpainting artifacts, frame corruption, and accidental damage to generated text/logo content.
   - Compute a SHA-256 hash before transfer.

5. **Transfer and verify on the Mac**
   - Prefer the direct Tailscale route if a localhost SSH tunnel/alias rejects the key or has stale forwarding.
   - Copy to a new Desktop filename with `scp`; refuse to overwrite an existing target unless explicitly requested.
   - On macOS, verify with native commands:
     ```bash
     scp -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes source.mp4 \
       lucasjouvencon@<mac-tailscale-ip>:/Users/lucasjouvencon/Desktop/output_watermark_removed.mp4
     ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes \
       lucasjouvencon@<mac-tailscale-ip> \
       "stat -f '%z %N' /Users/lucasjouvencon/Desktop/output_watermark_removed.mp4; \
        shasum -a 256 /Users/lucasjouvencon/Desktop/output_watermark_removed.mp4"
     ```
   - Do not hardcode a Linux path such as `/usr/bin/ffprobe` in a macOS verification command; use `command -v ffprobe` or rely on the already verified local media metadata.

## Session-tested pattern

For a 720×1280 portrait clip with a fixed four-point sparkle centered near `(600,1160)`, a mask bounding box around `(569,1129)`–`(632,1192)` and a cutoff just after the last watermark frame worked better than a 65×65 `delogo` rectangle. The exact coordinates and cutoff are media-specific; re-inspect every new asset rather than copying them blindly.

## Quality rule

A successful API/export status is not proof of a clean edit. The deliverable is only complete after pixel-level visual QA, media metadata validation, hash verification, and (when requested) remote transfer verification.