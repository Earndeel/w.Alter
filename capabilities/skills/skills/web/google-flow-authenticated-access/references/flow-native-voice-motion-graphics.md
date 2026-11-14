# Flow-native voice and reference-style motion graphics

Use this reference when a Flow advertisement must generate its French voice and
advertising graphics natively rather than receiving all typography/TTS in post.
This is a higher-risk mode: voice copy, generated typography, legal claims and
visual continuity each remain independent QA gates.

## 1. Separate the references by purpose

Attach two deliberately different assets when both product fidelity and a
reference-derived art direction matter:

1. **Product/identity reference:** a clean crop with the exact equipment or
   actor geometry, no watermark, old end card, logo, or unwanted background.
2. **Sanitized graphic style board:** a deterministic 9:16 board that captures
   only the approved palette, display type, price hierarchy, CTA shape,
   highlight treatment and particle/transition motifs. Remove source timecodes,
   official logos, legal marks, unwanted products, solar panels, and any copy
   that should not reappear.

Tell Flow which attachment controls geometry and which controls screen-space
motion graphics. Explicitly forbid reproducing the style board as a static
full-screen image. Allow-list every phrase that may be rendered; “same style as
the reference” is not an on-screen-text specification.

A good style board is more reliable than another paragraph of adjectives. It
should show the actual approved colors and typography at readable size, but no
production notes, safe-zone guides, or words that are not allowed in the final
video.

## 2. Prompt hierarchy for exact native speech

Put the audio contract before the shot list and label it as the highest
priority. Use a dedicated verbatim block containing only the approved French
copy. For a 10-second clip:

- prefer one continuous grammatical sentence over an abrupt question followed
  by a noun phrase; sentence boundaries are common ad-lib points;
- state one speaker, neutral French accent, dry centered studio recording,
  precise articulation, one take, and an explicit start/end window;
- prohibit introductions, conclusions, repetitions and filler; if exact copy
  cannot be produced, request silence rather than invented words;
- keep the instrumental bed roughly 20–24 dB below speech, with no vocals,
  vocal-like synths, reverb wash, or musical accent at a sentence boundary;
- do not ask an on-camera actor to speak unless lip sync is part of the brief.

Do not overload the voice block with visual details. After export, transcribe
with a strong French ASR model and compare normalized tokens to the approved
line. Listen or inspect suspicious ASR spans; a technically valid AAC stream is
not evidence of correct dialogue. Do not submit clip B while A's spoken copy is
wrong unless Monsieur explicitly accepts that defect.

## 3. Reference-style native graphics

For a dynamic vertical ad, use three or four motivated shots per 10 seconds,
not a default continuous take. Give each shot one visual role and one limited
screen-space graphic role. A robust progression is:

1. product hero + product title;
2. offer/price + eligibility note;
3. human benefit + restrained accent;
4. CTA/end card (usually in B).

Describe the graphic system concretely: palette hex values, condensed uppercase
font category, price scale, outline color, CTA pill, particle density, hard cuts
and flash duration. If karaoke captions are explicitly requested, require one
lower-safe-zone row, exact spoken copy only, white uppercase with black outline,
and one active word in a single opaque highlight rectangle. Reject duplicated
caption rows, malformed accents, invented words and text attached to physical
surfaces rather than screen space.

Exact legal/brand typography remains safer in deterministic post-production.
Native graphics are appropriate only when the user knowingly chooses the Flow
look and accepts the extra QA/retry risk. Never synthesize a government seal or
copy an institutional logo merely because it appears in the style reference.

## 4. Eliminate persistent forbidden objects compositionally

If a model repeatedly creates a forbidden object because of a strong semantic
association, stop extending the negative prompt. Remove the opportunity:

- frame a house facade below the eaves instead of showing a roof when solar
  panels are forbidden;
- use a tight product hero instead of a wide branded showroom;
- avoid reflective signage areas when random text is a known risk.

Positive framing constraints such as `roof completely outside the frame` are
more reliable than a long list of visual negatives. Verify this on a regular
contact sheet; prompt compliance is not pixel evidence.

## 5. Paid-submit and client-error recovery

Immediately before Create, verify `Agent=false`, the exact model, duration,
9:16 ratio, one variant, every intended attachment, and the complete one-line
prompt. Record the baseline media redirect IDs. Click Create once.

A client-side `Application error` after submission does not prove that the paid
request failed. Do not click again. Wait, reload the same project, and compare
actual `media.getMediaUrlRedirect?name=` IDs against the baseline. UI failure
text or a transient percentage is secondary; success requires a new media ID,
an authenticated `/tab/fetch-binary` MP4 response, and `ffprobe`. A failed-looking
card may later materialize a media ID, while reassuring prose may never do so.
Credits should be checked from the live profile dialog rather than assumed to
be refunded.

## 6. QA and bounded retries

For every clip:

1. export the exact new media ID through the authenticated context;
2. full-decode with FFmpeg and measure streams/duration with `ffprobe`;
3. ASR-transcribe the full native dialogue and compare to approved copy;
4. extract a 2 fps contact sheet when typography animates, plus full-resolution
   frames around the end/continuity handle;
5. inspect forbidden objects, product geometry, faces/hands, every visible word,
   graphic hierarchy and the A→B handoff.

Treat audio, pixels and continuity as separate PASS/FAIL columns. Allow one
controlled paid retry after naming the concrete defect and obtaining approval
for the additional credits. After that, stop the loop and offer explicit
choices: accept the test defect, repair in post, or stop Flow. Do not silently
launch B from a rejected A.

## 7. Report component provenance explicitly

Native generation and downstream verification are different operations. Keep a
small provenance ledger for every exported clip and state it plainly when
reporting the result:

| Component | Record the actual source |
|---|---|
| Visuals | Flow/Omni raw render, or named post-production operation |
| Voice | Omni native audio, named TTS provider, or replacement recording |
| Visible subtitles | Omni-rendered pixels, or deterministic post-production captions |
| Music | Omni native bed, supplied track, or replacement mix |
| Speech transcript | ASR model used for QA only |
| Text fixes | Exact post-production corrections, if any |

Do not describe an ASR transcript as the source of the voice or subtitles.
Whisper/Groq can verify the native speech while both the voice and karaoke text
remain generated inside Omni. Conversely, if captions are rebuilt from ASR in
post, say so explicitly rather than calling them native. Preserve the raw Flow
MP4 separately so provenance remains auditable after mixing or compositing.
