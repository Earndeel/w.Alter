# UGC walking testimonial: camera grammar and temporal QA

## Two distinct visual modes

Resolve the camera grammar before writing either prompt. They are not interchangeable:

### Visible-device walking testimonial (default for “woman walking, holding phone at arm’s length and talking”)

- third-person / observer camera watches an adult woman walking;
- her arm is extended and the smartphone is visibly held at arm’s length;
- she talks naturally toward the phone as if recording a testimonial;
- the street, walking rhythm, arm movement, and phone remain coherent for the whole shot.

### Direct front-camera selfie POV

- the viewer sees the woman directly through the phone camera;
- the phone body and filming device are off-screen;
- use this only when the brief explicitly says “front-camera POV”, “selfie face caméra”, or “no visible phone”.

Do not silently replace the visible-device mode with POV. The exact distinction matters more than the generic word “selfie”.

## Prompt consistency

Never mix the two grammars between the image and I2V prompts. A reference image that shows a phone in a hand combined with a video prompt saying “the viewer sees the phone camera view” or “never show the phone” causes temporal jumps: the video may begin as phone-in-hand and switch to direct face-camera footage.

For visible-device mode, use consistent language such as:

- `third-person handheld shot of an adult woman walking`;
- `smartphone clearly visible in her extended hand`;
- `she talks naturally toward the phone while walking`;
- `same camera position and same visible device throughout, one continuous take`;
- `no second phone, no mirrored phone screen, no phone-within-phone composition`.

For POV mode, explicitly prohibit the device in both the keyframe and video prompt, and do not describe a third-person observer shot.

## Frame-level QA before integration

A provider `success` status is not visual validation. Inspect the actual video at `0s`, `1s`, middle, and near the end. Confirm:

- the requested camera grammar persists at every sampled time;
- walking motion is real, not a static portrait with a moving background;
- face, limbs, phone, arm, and background remain coherent;
- no phone-within-phone composition, text, logo, watermark, or temporal jump appears.

If the clip starts in one grammar and switches to another, regenerate with consistent prompts. Do not trim away the phone/device merely to hide a defect when the brief explicitly requested a visible phone: that removes the requested semantic element. Trimming is acceptable only after the user accepts the retained shot mode and the result still satisfies the brief.

## Poster and landing integration

Extract the poster from a clean frame of the final accepted video. Do not use a discarded or contradictory reference image as the poster. After integration, verify MP4/WebM duration and codecs, media readiness, responsive overflow, browser errors, and explicit deployment approval. See the main skill’s Kie/landing procedure for the command-level checklist.
