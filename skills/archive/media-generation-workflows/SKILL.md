---
name: media-generation-workflows
description: "Use for generating, editing, and QA of AI media."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [media, video, image, generation, postproduction, workers, qa]
---

# Media Generation Workflows

Use this class-level umbrella for AI image/video generation, isolated media workers, landing-page assets, post-production, and release QA. Treat provider submission, durable orchestration, rendering, technical validation, visual/audio review, and delivery as separate gates.

## Always-on rules

- Resolve the exact provider, model ID, endpoint, modality, reference inputs, duration, ratio, resolution, audio, output path, and budget before starting a billable job.
- Validate the live provider contract and account entitlement; never infer a working model from a marketing label, stale catalog, generic credit flag, or a successful HTTP response.
- Keep provider calls behind narrow adapters with explicit credentials and correlation IDs; never expose tokens, signed URLs, task manifests, or private asset paths in prompts, logs, public directories, or final messages.
- Persist job IDs, input/output hashes, stage receipts, retry lineage, and terminal states; poll the original job after an interruption instead of submitting a duplicate. Reconcile browser-driven jobs against stable, project-scoped media IDs: an empty lazy-loaded gallery is not an empty baseline, and a rotating CDN URL is not a new asset.
- Treat `submitted`, `success`, `Ready`, or a generated URL as intermediate evidence only; download the actual artifact and verify it before delivery.
- Preserve originals and use separate output paths for edits; report provider failure, incomplete artifact, technical failure, visual failure, audio failure, and brief non-compliance separately.
- Diagnose provider generation and local tracking independently. A monitor exception does not explain a provider rejection, and repairing the monitor does not produce the missing clip; keep the provider cause unverified unless its own evidence identifies it.
- Treat recipient access as a delivery gate. If Monsieur cannot see a clip, inspect the actual attachment or preview target and resolve where its path is interpreted before repeating the link or claiming delivery; a server-side file and an accepted preview-open command do not prove recipient playback.
- Label individual clips as partial deliverables until every requested clip and post-production stage passes QA; state the missing stage plainly rather than allowing successful parts to imply a finished ad.

## Browser-driven job recovery

1. Read the latest manifest and separate completed media, active attempts, prior failures, and references; preserve submission receipts before changing state.
2. Inspect the exact live project and reconcile its inventory with known completed IDs. Use the browser's observed response data when lazy tiles or opaque CDN URLs hide identity; exclude uploads, templates, and other projects.
3. Correlate a candidate with the intended job or prompt and its submission baseline before accepting it. Deduplicate by stable media ID; neither the first UUID nor one newly visible thumbnail establishes ownership. A disappearing progress bar, a new gallery tile, or a `Ready` label is not completion evidence by itself: open the exact candidate, read its current media source or equivalent stable handle, download the bytes, and run `ffprobe` plus a full decode. Compare against the pre-submit inventory so an older completed tile cannot satisfy a new job.
4. If no correlated output exists, report the missing output and provider evidence without inventing a cause. Repair and test local tracking separately; any paid retry remains subject to the creative and budget gate.
5. Merge only the attempt's owned result fields into the latest manifest so concurrent reference and QA changes survive, then validate and deliver the actual artifact.

See `references/browser-job-reconciliation.md` for lazy-gallery diagnostics, the observed Flow response layout, and regression cases. See `references/flow-ugc-selfie.md` for the reusable headless Flow procedure, reference binding, prompt gates, and final-master audio checks.

## Reference-conditioned generation

- For adaptations based on a client conversation, load `reference-video-fidelity` and establish the creative contract before writing generation prompts: retrieve the original attachment and relevant client messages, attribute each requirement to its actual speaker, distinguish video requests from adjacent campaigns or static-image requests, and transcribe material voice notes. Map each approved benefit, qualification, role and CTA to the exact proposed dialogue and a purposeful visual action; keep reference-only claims and unverified financial mechanisms out of the script. An assistant's suggested duration or wording is not client approval, and adding eligibility language must not erase the offer that makes the application desirable.
- Inspect every supplied reference before generation and preserve a source-to-target mapping; use actual image/video bytes or an explicit provider input handle, never a filename mentioned in prompt text.
- Record source dimensions and hashes, mode, provider/model, output hash, and a binding receipt; block with a structured input-binding error when the adapter cannot bind the source.
- Classify the requested adaptation as literal shot/content recreation or style/grammar adaptation before writing prompts. Keep identity, composition, motion, style, dialogue, exclusions, and camera grammar explicit. For a style-only UGC adaptation, prioritize camera POV and performance grammar over importing every source object or role; resolve visible-device testimonial versus direct selfie POV before writing image and video prompts.
- For multi-shot work, define continuity anchors, shot timing, internal cuts, source-content end, padding, and post-trim behavior; a short generic prompt is not a lossless reconstruction spec.
- When a supplied reference is selfie UGC and the brief asks for its style, default to one primary speaker filming with the front-facing smartphone camera: close or medium selfie framing, direct eye contact and a visible speaking mouth throughout, handheld micro-movement, practical location, and conversational native delivery. Make capture ownership explicit in the provider prompt (the speaker holds the phone in one hand) and include observable cues such as arm-length perspective, a visible forearm or phone edge where natural, irregular non-mechanical movement, imperfect reframing, and autofocus/exposure drift. Never rely on “handheld” or “à main levée” alone, because generators may turn it into a polished third-party shot. Ban voice-over, colleague-operated camera or camera operator for selfie shots, tripod/gimbal/dolly/drone, cinematic depth of field, perfectly centered framing, polished-presenter blocking, technical B-roll, baked-in captions, UI, logos, and readable signage unless explicitly requested, and allow only restrained jump cuts.
- Before paid creative generation, inspect the actual bound source frames and remove irrelevant app UI, subtitles, logos, or ad chrome from a style reference by cropping or masking; show the cleaned source beside the proposed literal/style mapping and obtain prompt approval. If the target is style-only, make the first paid job one representative selfie clip, compare the downloaded artifact to the reference, and generate the remaining set only after that grammar passes. Treat that representative render as a motion test as well as a composition test: assess native-cadence video or a measured camera trajectory, not a contact sheet alone. If one paid attempt still produces a tripod-like result, stop escalating synonyms for “handheld” and use a bounded deterministic post-production motion pass only when the brief permits it.
- Treat generated typography, logos, legal claims, product labels, certification marks, and URLs as untrusted pixels; replace them deterministically or reject them when exact copy matters.

## Provider and adapter branches

### Nous-native BFL/FLUX video

- For a request explicitly routed through Hermes/Nous, use the separate `bfl_flux3_*` tools and do not substitute generic FAL, Kie, or direct vendor routes.
- Authenticate the Nous provider without printing tokens; do not pre-gate native access on a generic paid-credit or FAL coverage flag because the gateway owns entitlement.
- Read the native prompting guide, submit explicit mode/duration/resolution/ratio/audio settings once, poll the same job with the result tool, download locally, and validate with `file`, `ffprobe`, full decode, contact-sheet review, and ASR when dialogue is material.
- Treat a gateway refusal, quota decision, moderation response, or model-unavailable response as authoritative; a retry is not a recovery path unless the error is explicitly transient.

### Higgsfield MCP

- Discover models with the live model-exploration tool before generation; preserve exact IDs and use numeric durations.
- Put generation arguments under the required `params` wrapper; a schema error is an argument-shape failure, not a reason to guess another model.
- Treat the server's trial/entitlement error as authoritative and check credits before billable work. When transport is down, reconnect once or use the approved direct JSON-RPC path with correct `Accept` headers and bearer auth.
- Renew headless OAuth through the provider CLI plus an SSH callback tunnel when needed; do not loop on broken generic reauth, guessed OAuth endpoints, or anti-bot browser login.

### OpenRouter image generation

- Resolve exact image models from the dedicated image catalog and endpoint record, not only the general model list; load the model-ID lookup before using a named ID.
- Use the dedicated image endpoint when the provider contract says the output modality is image, pass only advertised parameters, respect the live reference-count limit, and use a single composite board when multiple references must be represented.
- Require non-streaming image bytes, decode them locally, validate format/dimensions/aspect ratio, inspect the actual pixels, and deliver the verified local file rather than a claimed URL.
- If a safety filter rejects accidental reference content, sanitize irrelevant material and wording once without changing the intended scene; report a persistent block instead of attempting a bypass.

### Landing-page and campaign media

- Inspect existing HTML/CSS and routes before changing media slots; preserve semantic alt text, public-path conventions, fallbacks, and explicit deployment approval.
- Stage generated files outside the public directory, parse documented nested result fields exactly, validate dimensions/streams/duration before conversion, and never recursively choose the first URL in a provider response.
- Provide a poster and explicit browser-compatible `<source>` fallback. Serve a local wrapper and test the actual rendering engine with `canPlayType`, `readyState`, `videoWidth`, `duration`, and `video.error`; page text, HTTP 200, and `desktop_preview.read` prove reachability only, not playback. Write literal valid HTML attributes in the wrapper (for example `type="video/webm"`); do not leave programming-language backslashes inside already-quoted attributes, because malformed `<source>` tags can produce `networkState=3`/`NETWORK_NO_SOURCE` with an empty `currentSrc` even when the page and media return 200. If H.264 returns empty support or `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, encode VP9/Opus WebM (`ffmpeg -i input.mp4 -c:v libvpx-vp9 -crf 32 -b:v 0 -c:a libopus -b:a 128k output.webm`), list WebM before MP4, preserve both outputs, and reopen the wrapper with a cache-busting query after updating it. Keep decorative loops muted, and verify the served page at desktop and mobile viewports for media readiness, overflow, console errors, asset status, and visual hierarchy.
- Keep client-bound batches staged until the exact set is approved; a successful upload or provider task is not delivery authorization.

See `references/browser-media-preview.md` for the codec probe, wrapper pattern, fallback encode, and delivery checks.

## Isolated production workers

- Create specialized Hermes workers without bundled skills, unrelated memory, messaging, browser, delegation, cron, or personal credentials unless the workflow explicitly needs them; verify effective tools rather than trusting a YAML fragment.
- Keep `SOUL.md` short, put semantic production authority in the canonical skill, and put deterministic queue/media/provider execution behind narrow runtime adapters.
- Use stable queue identities such as `GSHEET_<spreadsheet-id>_ROW_<row-number>` and durable per-job stage state; conversational turns are not production databases.
- Validate queues read-only first. If a Sheets values API is unavailable but authenticated Drive export works, parse the live XLSX fallback, preserve headers/row numbers/booleans, report the source, and perform no writes.
- Keep completion fail-closed: final QA passes → final file exists and decodes → upload → stable delivery URL → write result → read back result → mark finished → read back finished and result. Any failure preserves state and leaves completion unset.
- Keep semantic decomposition lossless: every source cut, reference authority, dialogue policy, asset binding, provider constraint, QA decision, and repair target must survive stage boundaries; more files do not prove more coverage.
- For a generate-then-postproduce request, make generation handoff a gate, not a completion claim: require downloaded source paths, submission IDs, exact dialogue, actual ASR, creative QA and remaining defects before starting the edit. If generation is blocked or only prompts exist, report that phase as incomplete and never substitute rejected earlier clips under the new version. Preserve an explicit next-stage handoff so a worker finishing its phase does not silently end the full commission.

## Post-production

- Resolve the requested asset and ordered creative roles from the brief/source of truth, not filenames such as `final`, `continuation`, or `last`.
- Probe every input and inspect start/middle/end frames before assembly; preserve framing and resolution unless a crop/resize is approved.
- Keep audio explicit in every filter graph and map both streams; normalize timestamps, frame rate, timebase, pixel format, sample aspect ratio, and audio layout before concat/xfade.
- For a fixed visible overlay on user-owned/generated media, prefer the smallest shape-aware mask with a time gate, preserve the source, and compare original/result crops over moving backgrounds and scene transitions. This addresses visible pixels only, not invisible provenance markers.
- After concat and any audio mix, run ASR on the encoded clean master—not only on individual clips—and compare it to the approved script before generating subtitles; trim or reject duplicated phrases, model-credit lines, hidden narration, and silent or voiced tails that individual-clip checks can miss. Derive word-synchronized subtitles from that approved master ASR, add master-timeline offsets only after the final edit is fixed, and distinguish audio-copy compliance from visible lip-sync compliance. If ASR cannot run, mark transcript and caption alignment as unverified; never claim that prompt text alone proves the generated speech.
- Before paying to regenerate a clip with an isolated spoken addition, test a reversible synchronous audiovisual jump cut when the surrounding approved words can survive intact. Do not trust overlapping ASR word boundaries: inspect actual pauses and phonetics, use frame/sample-aligned EDL bounds, then run independent ASR on the encoded repair and focused native-cadence audiovisual QA across the join and complete ending. Preserve the source and initial rejection; distinguish mandatory client requirements from assistant-authored movement preferences so an absent optional reveal does not automatically invalidate an otherwise usable repair. Treat a generic audit claiming no cuts as unreliable when the known EDL contains a cut.
- Keep edit durations in one edit-decision timeline and derive ASR bounds, offsets, subtitle bounds, expected frame counts and QA sampling from it; trimming a silent tail must not leave stale fixed-duration assertions or shift subsequent words.
- Select karaoke QA frame timestamps strictly inside each rounded ASS event interval: clamp the nearest midpoint frame between `ceil(start*fps)` and `ceil(end*fps)-1`, and assert membership. Ceil-rounding the midpoint can sample the next word for a one-frame event and falsely report a missing highlight. If an event contains no delivery frame, fix its timing before claiming it renders.
- Verify rendered karaoke rather than only subtitle event counts: sample every active-word interval in the encoded master, compare its caption region against the clean master to isolate highlight pixels, and inspect a complete word contact sheet for clipping and punctuation. When revising readability, enlarge the ASS style and place its baseline in the lower third while enforcing a measured maximum line width; never trust a font-size change without checking the rendered pixel bounds. If a brief specifies a pixel size such as 56px, validate at the delivery resolution and inspect full-resolution frames rather than trusting a downscaled contact sheet. If the caption pass copies audio, compare the extracted encoded audio packets against the ASR-approved clean master; matching packets bind transcript QA to the delivered soundtrack, not lip-sync quality.
- Keep a clean, no-overlay base and render every subtitle or audio revision from it; never burn revised captions onto an already captioned master, because the old pixels survive and create duplicates. For narration/music revisions, preserve the clean master and render versioned derivatives; use an original or cleared instrumental, keep the bed below narration with sidechain compression rather than a static volume guess, and use the same final soundtrack for clean and karaoke variants. With FFmpeg `amix`, set `normalize=0` deliberately or measure the result because the default can attenuate the voice; target an explicit social loudness range (roughly -19 to -23 LUFS unless the brief says otherwise), check true peak, and compare a ducked music stem in voice and non-voice windows. Solo the sources, reject phase-cancelled diagnostic stems as release beds, regenerate or shorten overlong copy rather than stacking speed changes, and audition the encoded master in addition to loudness/peak checks.
- In an FFmpeg graph, `asplit` any source consumed by both a sidechain/analysis branch and the final mix: a labeled output is single-consumption, so reusing it without a split can make the graph fail or silently omit a branch. When an edit reads and writes the same media path, render to a temporary output and atomically replace the destination after success; FFmpeg does not support safe in-place filtering.
- Treat end cards as a separate release gate: use verified deterministic copy/assets, inspect full-resolution text and legal marks, and replace only the defective card when the rest of the ad is coherent.

## Media QA and release

1. Record the selected inputs and source hashes.
2. Run `ffprobe` for container, stream, dimensions, frame rate, duration, frame count, audio, and size; run a complete decode.
3. Review the full timeline with contact sheets and native-cadence checks around cuts, overlays, presenters, end cards, and acceptance-critical details.
4. Measure audio by meaningful segments, run ASR when copy matters, and listen when subjective quality matters.
5. Check scene/action/identity/product continuity, generated text/logos, crop safety, browser fallback, and target-page integration.
6. Classify the result as ready, needs targeted fix, blocked, or reject; retain evidence and re-verify every changed stage.
7. Exercise the recipient-access gate separately from media QA: check the exact attachment, served resource, or verified receiving-device file, and test playback where available. If only file presence or transport is verified, state that limit rather than claiming the user can watch it.

A technically decodable MP4 is not automatically a usable creative. Report measured values, visible observations, interpretation, unverified constraints, and the exact artifact delivered.

## Economics and safety

Compare hosted and self-hosted routes using current prices, GPU throughput/memory, queue time, storage/egress, engineering, monitoring, retry cost, and failure cost. Validate a short real generation before committing to a larger deployment, and never run paid generation during setup smoke tests.
