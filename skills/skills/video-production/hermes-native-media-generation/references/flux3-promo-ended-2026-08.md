# FLUX 3 via Nous — promo ended (verified 2026-08-21)

A `bfl_flux3_text_to_video` submission (5 s, 720p, 16:9, no audio) on 2026-08-21 was refused by the gateway with:
"The free Flux 3 promotional period has ended, so Flux 3 video generation is not available through Nous right now. Retrying will not help, and neither will the other Flux 3 tools."

Interpretation:
- This is a promo-end refusal, not a credit/quota/401 problem. Retrying or re-authenticating does not help; do not burn turns resubmitting.
- The routing rules in `flux3-bfl-nous-gateway.md` still hold: never pre-gate locally on plan/credits, submit once, surface the gateway message verbatim.
- Post-promo FLUX 3 access: BFL direct pay-as-you-go (Draft 720p $0.06/s t2v/i2v, Standard $0.17/s, 1080p $0.29/s, v2v $0.12/$0.41 per s) or OpenRouter `black-forest-labs/flux-3-video` ($0.17/s 720p, $0.29/s 1080p, continuation $0.41/$0.53 per s). Dated evidence matrix: `research-evidence-verification` skill → `references/flux3-video-provider-pricing.md`.