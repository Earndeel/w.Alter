# Supplied brand asset preparation

## Purpose

Reusable recipe for turning a user-supplied raster logo into a faithful web asset family without asking a generative model to redraw typography or Chinese characters.

## Deterministic workflow

1. **Inspect the master first.** Load the supplied image with `vision_analyze`; record dimensions, background color, visual zones, and any shadows/anti-aliasing worth preserving.
2. **Build a background mask.** For a uniform white background, use a luminance/color-distance mask with a soft edge. Do not hard-crop by eye only: inspect the alpha bounding box and keep deliberate padding.
3. **Crop by semantic region.** Derive separate crops for the full logo, the symbol/mark, and the wordmark. Use row/column pixel projections or manually verified region bounds; never let an adjacent symbol bleed into the wordmark crop.
4. **Recompose only from approved pixels.** If the UI needs a horizontal lockup, resize and align the exact mark and wordmark crops on a transparent canvas. Do not redraw the logo, change its colors, or use AI regeneration when glyph fidelity matters.
5. **Generate target assets.** Export lossless PNGs (or a separately reviewed vector) for the full lockup, mark, wordmark, horizontal lockup, and square favicon. Keep the original master outside the public directory.
6. **Inspect every output.** Use `vision_analyze` on each crop and a zoomed header screenshot. Specifically check for white-background halos, clipped strokes, stray pixels from neighboring regions, wrong aspect ratio, and favicon legibility.
7. **Integrate by surface.** Use the horizontal lockup in a spacious desktop brand rail, the mark alone on compact/mobile surfaces, and the square mark for the favicon. Set meaningful `alt` text on the visible brand image and use a stable public path under `/brand/`.
8. **Verify after deployment.** Run the production build, fetch every public asset and check status/content type/non-zero bytes, then run desktop/mobile Playwright smoke checks and visual screenshot QA. A successful upload alone is not proof that the right logo is being served.

## Minimal Pillow pattern

```python
from PIL import Image
import numpy as np

rgb = np.array(Image.open("master.png").convert("RGB"))
nearest_bg = rgb.min(axis=2)                 # white-background shortcut
alpha = np.clip((250 - nearest_bg) * 255 / 30, 0, 255).astype("uint8")
rgba = np.dstack([rgb, alpha])

# Replace these with vision-verified semantic regions.
def crop(region):
    x0, y0, x1, y1 = region
    return Image.fromarray(rgba[y0:y1, x0:x1], "RGBA")

crop((..., ..., ..., ...)).save("public/brand/irene-mark.png")
```

For non-white backgrounds, replace the shortcut with per-pixel distance from the sampled background color and verify edge quality at 200–400% zoom. Avoid lossy JPEG intermediates.

## Concrete session reference

The supplied Irene Laoshi master was `1254×1254`. A useful first segmentation was mark bbox `(352, 232, 911, 771)` and wordmark bbox `(129, 760, 1136, 1013)`. The wordmark crop needed to start around `y=790` to exclude the bottom of the book icon; this is the class of bleed that visual inspection catches and naive cropping misses. The resulting reviewed family was:

- `irene-full.png` — `1070×855`
- `irene-mark.png` — `620×610`
- `irene-wordmark.png` — `1065×260`
- `irene-horizontal.png` — `1341×350`
- `irene-favicon.png` — `512×512`

These dimensions are evidence for that master, not defaults for future logos.

## Language-direction companion gate

When the product brief is corrected to a source → target pair such as **English → Mandarin**, update the source-language meanings, prompts, search placeholder, metadata, and QA selectors together. Keep the brand asset itself unchanged; show the pair in the product UI rather than modifying the approved logo artwork to carry product copy.
