# Referenced UGC portrait benchmark — July 2026

Session-specific evidence for choosing among Kie.ai image-to-image models. Revalidate prices and model contracts before future production use.

## Controlled setup

- Same two input images for every model: one character sheet and one emotion sheet.
- Same five composition concepts, with only moderation-compliant wording adjustments where a provider rejected a frame.
- Kie conversion shown during the run: `1 credit ≈ $0.005 USD`.
- Quality was assessed from a labelled contact sheet, not provider claims.

## Observed cost and behavior

| Model slug | Settings | Credits/success | Approx. USD | Observed completion | Quality notes |
|---|---|---:|---:|---|---|
| `seedream/5-pro-image-to-image` | basic/1K, 9:16, PNG | 7.5 | $0.0375 | 5/5 | Strongest sensual composition and lighting; some facial variance. |
| `nano-banana-2` | 1K, 9:16, PNG | 8 | $0.0400 | 4/5 initial; replacement succeeded | Excellent skin and realism; body may become over-sculpted; upstream Google moderation. |
| `nano-banana-2-lite` | 9:16 | 4 | $0.0200 | 5/5 after compliant prompt set | Best budget option; stable identity, slightly more synthetic detail. |
| `gpt-image-2-image-to-image` | aspect ratio `auto` | 6 | $0.0300 | 2/5 in initial batch | High quality when successful, but slow and operationally unreliable for this sensual brief; two moderation failures and one upstream timeout were zero-credit. |
| `grok-imagine/image-to-image` | documented I2I fields only | 4 | $0.0200 | 5/5 | Best quality/cost/reliability compromise; fast, coherent, occasionally smooths faces. |

## Practical ranking for this class of brief

1. Seedream 5 Pro for maximum creative quality and stronger sensual direction.
2. Grok Imagine for production throughput and value.
3. Nano Banana 2 for realism when Google moderation is acceptable.
4. Nano Banana 2 Lite for low-cost compliant variants.
5. GPT Image 2 only when its specific visual quality justifies latency and rejection risk.

## Durable lessons

- Every provider accepted both reference URLs in one request, but each uses a different field name; follow the verified contract table.
- Moderation failures often cost zero, but never assume this—read `creditsConsumed` from each terminal task.
- A five-image deliverable may require six submissions when one filtered concept is replaced. Report successful-image cost separately from submission count.
- For comparisons, use actual task billing and a contact sheet. File size alone is not a quality metric.
- Persist task IDs before polling: an interrupted foreground process must not make completed provider-side jobs unreachable.

## Controlled emotion-sheet test

A five-expression Grok run held framing, black tank top, bedroom background, and warm side-light constant while requesting neutral, laughter, surprise, sadness, and anger from specified emotion-sheet cells. All five broad emotions were recognizable and overall identity remained coherent. That result initially looked like a full pass, but inspection against the source sheet showed the laughter frame had generated a wider, whiter, more regular dentition. Correct verdict: broad emotion transfer passed; dental identity did not.

### Cross-model smile comparison

The same two reference sheets and one dental-identity prompt were then sent once to each non-Grok model. All four tasks succeeded. Visual ranking against a crop of the source smile:

1. `gpt-image-2-image-to-image` — closest smile asymmetry, tooth exposure, and lip geometry; teeth remained too white and regular.
2. `seedream/5-pro-image-to-image` — strong overall facial identity, but veneer-like uniform teeth.
3. `nano-banana-2` — coherent face, but smile too wide with excessive lower-tooth exposure.
4. `nano-banana-2-lite` — weakest dental identity; visibly different tooth scale, arrangement, and color.

None reproduced the dentition exactly. Do not convert this session ranking into a permanent universal model ranking: generation is stochastic and contracts/models evolve. Re-run a controlled sample when dental fidelity is production-critical.

### Evaluation protocol for open smiles

Place the source smile crop as the first tile in the contact sheet, followed by outputs at comparable face scale. Evaluate separately:

- visible upper/lower tooth count;
- widths and shapes of central/lateral incisors and canines;
- spacing, alignment, and gum exposure;
- color and degree of artificial whitening;
- smile width, asymmetry, lip contour, and cheek compression;
- whole-face identity after expression-induced deformation.

A generic broad smile is not evidence that the model used the emotion sheet faithfully. Report emotion transfer, whole-face identity, and dental/subfeature identity as separate findings.

## GPT Image 2 follow-up: yield, identity drift, and timing

A later five-frame sensual UGC batch with safer non-explicit wording completed 5/5 at 6 credits per image, showing that the initial 2/5 result was prompt/run-specific rather than a permanent provider yield. However, two outputs—especially a reclined, red-lit composition—drifted materially in facial structure. Treat unusual pose, wet-hair state, strong colored light, and foreshortening as identity-risk factors; compare jaw width, nose, eye geometry, and facial proportions before acceptance.

Seven successful GPT Image 2 tasks from the same session reported provider `costTime` values of 127, 143, 155, 127, 134, 272, and 239 seconds: mean 171 seconds, median 143 seconds, range 127–272 seconds. Independent submissions had near-identical `createTime` values, confirming parallel provider execution even when the foreground collector appeared slow.

For continuity, the selected fifth output was appended as a third reference alongside the original character and emotion sheets. The prompt declared it the primary reference for current face rendering, sofa, wardrobe, lighting, camera texture, and mood, while varying only pose and emotion. One of three initial continuations succeeded; two returned transient internal errors at zero credit. Their task IDs remained valid after the local collector was interrupted, so recovery must query those IDs before any resubmission and preserve output numbering.
