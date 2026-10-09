# ASCII media branch

Use this branch for ASCII video, terminal-style animation, and audio-reactive character art. Keep the visual concept and the technical render contract explicit; a technically valid encode can still be an incoherent or unreadable piece.

## Pipeline contract

Build every project as `INPUT → ANALYZE → SCENE → TONEMAP → SHADER/FEEDBACK → ENCODE`:

- Decode video, images, audio, lyrics, or synthetic time features without loading more than the render requires.
- Extract normalized audio/video features before rendering. Use band ratios as well as loudness so quiet and loud sections preserve the same musical character; smooth noisy features before driving motion.
- Give each scene a concept, a directional arc, a role in the whole video, and a distinct but compatible palette/effect configuration. Use multiple grid densities for depth, not one effect repeated everywhere.
- Keep scene functions module-level when using process workers; pass persistent particle/rain state explicitly and seed every random source when repeatability matters.
- Prefer adaptive percentile tone mapping and gamma to linear brightness multipliers; test readable text against a dark backdrop and do not apply kaleidoscope/mirror effects to text scenes.

## Rendering and performance

- Detect CPU, memory, ffmpeg availability, resolution, aspect ratio, and quality tier at startup; leave capacity for the OS and encoder.
- Vectorize field generation, cache fonts/coordinate arrays/bitmaps/background textures, cap particles, and parallelize independent clips rather than sharing mutable renderer state.
- Keep long-running ffmpeg stderr out of a pipe; redirect it to a file so the encoder cannot deadlock on a full buffer.
- Render segments to isolated temporary paths, concatenate only after every segment succeeds, and delete intermediates only after the final artifact passes verification.

## Audio, text, and synchronization

- Keep display text separate from TTS text so line breaks do not corrupt pronunciation; make TTS generation idempotent and mix speech and music with an explicit channel/loudness contract.
- Use integer frame indices and recompute timestamps from `frame / fps`; compare audio beat timestamps with visual brightness or marker timestamps to expose drift.
- Validate every palette glyph against the selected font and clip every value field to `[0, 1]`; these prevent blank glyph holes and renderer index errors.

## Verification

Before a full render, produce test frames at the start, middle, and end of representative scenes. Check mean brightness, text legibility, scene continuity, palette glyph coverage, shader/blend safety, frame count, audio/video duration, decodeability, and beat alignment. Report any unverified visual or audio gate instead of treating an encoder exit code as quality proof.
