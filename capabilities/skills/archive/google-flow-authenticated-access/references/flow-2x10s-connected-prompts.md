# Flow 2×10s connected-ad prompt pattern

Use this when a longer vertical advertisement must be built from two paid
10-second Flow generations and then assembled into one 20-second master.

## Delivery model

| Clip | Narrative role | Continuity handle |
|---|---|---|
| A (0–10 s) | Hook, product/mechanism, offer setup | End on a stable motion, eyeline, gesture, fan rotation, or camera push that B can resume |
| B (10–20 s) | Benefit/proof, secondary offer, CTA/end card | Begin from A's exact final frame and complete the sales arc |

Generate A first. Export and QA its actual MP4 before spending credits on B.
Attach the validated A video itself as B's continuity reference; a source still
cannot preserve A's final motion, timing, narrator or room tone.

## Prompt approval and run settings

Save each exact prompt to `/tmp`, show both prompts to Monsieur, and wait for
explicit approval. Confirm the live model, `Vidéo · 10s`, `crop_9_16`, `1x`,
and the displayed per-clip credit cost immediately before each paid submit.
Prompt body and scene direction should be English; approved dialogue remains
verbatim French in a dedicated block. Type the paid prompt as one single-line
string even if it is displayed with paragraphs for review.

## Choose the right shot grammar

Do not impose `one continuous shot` as a universal rule.

- **Dynamic commercial/reference ad:** use three or four motivated shots per
  clip, usually one meaningful visual change every 1.5–3 seconds. Specify the
  exact cut times and avoid contradictory `no cuts` language.
- **UGC presenter testimonial:** a continuous take can be appropriate when the
  brief explicitly needs natural phone-camera delivery and lip sync.

A prose-only prompt without timed shot roles tends to collapse into a static
presenter or one generic product shot.

## Script division and native speech

Split dialogue at a natural semantic boundary, balancing real spoken duration
rather than word count alone. Each clip must contain a self-contained verbatim
voice block with speaker, accent, dry studio quality, pace and start/end window.
When exact native speech matters:

- prefer one continuous grammatical sentence inside each clip;
- keep music roughly 20–24 dB below speech and prohibit vocal-like instruments;
- prohibit filler, repetitions and extra introductions/conclusions;
- ASR-transcribe A and compare to approved copy before creating B;
- treat wrong speech as a failed QA gate even when video/audio streams are valid.

See `flow-native-voice-motion-graphics.md` for the detailed pattern.

## Reference hierarchy

For A, attach the cleanest product/identity reference. If the user requests the
same advertising art direction as a source video, also attach a sanitized 9:16
style board containing only approved palette, type hierarchy, price/CTA shape,
highlight treatment and particle motifs. Remove source timecodes, official
logos, legal marks, unwanted products and forbidden objects.

For B, attach A itself as the primary continuity reference. Reuse the style board
only if needed and clearly state that A controls people/location/camera/audio
while the board controls screen-space graphics.

## Generated typography is conditional

Default to deterministic post-production for exact brand/legal copy. Do **not**
apply an unconditional `no generated text` rule when Monsieur explicitly asks
for Flow-native advertising graphics. In that mode:

- allow-list every permitted phrase;
- specify palette, condensed display type, price hierarchy, CTA shape and safe
  zone concretely;
- forbid all other words, real institutional logos, seals and malformed text;
- require one caption row only if karaoke is requested;
- inspect every visible word at 2 fps after export.

Native generated typography has a higher retry risk; surface that trade-off
before spending credits.

## Visual-risk design

Negative prompts are not enough for objects strongly associated with the
subject. If roofs repeatedly gain solar panels, frame the facade below the eaves
so no roof is visible. Exclude risky regions compositionally rather than adding
longer negative lists. Apply the same principle to signage, showroom logos and
reflective surfaces.

## B continuity language

State explicitly that B is a direct continuation of A and lock:

- same people and identity;
- same wardrobe and props;
- same location, time of day, lighting and grade;
- same camera height, focal feel and screen direction;
- same narrator timbre, pace, room tone and music bed;
- exact initial pose/motion inherited from A's final frame.

Do not merely say `same style`; enumerate the continuity variables.

## Post-generation gates

For A and B independently:

1. detect a genuinely new media redirect ID against the pre-submit baseline;
2. export it with authenticated `/tab/fetch-binary`;
3. full-decode and `ffprobe` duration, dimensions, codecs and audio;
4. ASR-transcribe native dialogue;
5. inspect a regular 2 fps contact sheet and full-resolution splice frames;
6. reject forbidden objects, malformed text, fake marks, anatomy defects and a
   continuity reset unless Monsieur explicitly accepts the test defect.

Assemble only the two validated source IDs. Use filter concat plus controlled
H.264/AAC re-encoding when raw concat produces timestamp warnings, then rerun
`ffprobe` and inspect the splice. A queued card, play icon or agent message is
not a 20-second deliverable.
