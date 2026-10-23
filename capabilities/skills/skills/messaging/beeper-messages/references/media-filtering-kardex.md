# Beeper Media Filtering — Kardex CL Test

When extracting Beeper media from the Mac filesystem, attachment `type=img` is not enough to know whether it is a real photo.

## Observed Patterns

- Many Instagram "images" saved by Beeper are actually GIF stickers, reaction images, or placeholders.
- View-once Instagram images often save only a generic placeholder GIF; the real image is not recoverable after the fact.
- Duplicate placeholders can be detected by identical hashes.
- Real saved photos are usually JPEG/PNG/WebP and typically larger than tiny sticker assets.

## Practical Filter

After copying files from the Mac:

1. Read file header bytes:
   - JPEG: `ff d8 ff`
   - PNG: `89 50 4e 47 0d 0a 1a 0a`
   - GIF: `47 49 46 38` (`GIF87a`/`GIF89a`)
   - WebP: `RIFF....WEBP`
2. Hash files to deduplicate placeholders.
3. Treat GIFs under ~50KB as likely stickers/placeholders unless explicitly needed.
4. Keep JPEG/PNG/WebP as candidate real photos.
5. Keep large GIFs only if animation/sticker content is relevant.

## CL Test Result

For CL/Annie, recent "images" included:
- 43KB duplicate GIF placeholders for view-once content.
- small GIF stickers (crying cat, popcorn, cozy potato).
- 52 real photos after filtering JPEG/PNG/WebP and excluding GIF stickers.

## Rule

Do not tell Monsieur “images recovered” until files are header-checked and classified. Report separately:
- real photos
- stickers/GIFs
- placeholders/view-once unrecoverable
- videos/audio pending analysis
