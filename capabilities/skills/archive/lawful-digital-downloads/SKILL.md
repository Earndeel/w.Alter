---
name: lawful-digital-downloads
description: "Use when downloading digital works. Verify rights."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [web, downloads, copyright, books, music, media]
---

# Lawful Digital Downloads

Use this skill for requests to obtain a book, track, film, game, software package, or other published digital work, especially when the user asks for a free copy.

## Procedure

1. **Resolve the work first.** Use `walter_browse` with a search query to identify the exact title, creator, edition, and format. Do not assume that an ambiguous name refers to music, a book, or a particular edition.
2. **Check legitimate availability.** Inspect the official publisher/store page, public-domain or open-license source, and library or controlled-lending source where relevant. Use `walter_browse` on candidate pages and read access/rights metadata; a search result, filename, or “free download” label is not enough.
3. **Classify the access mode.** Separate direct authorized download, public-domain/open-license file, controlled digital lending, preview-only access, and paid/DRM access. A borrow or preview is not a downloadable free copy.
4. **Download only an authorized public file.** Once the source and license are clear, use the available download path; for a direct file, `curl --fail --location --output <path> <url>` is acceptable. Verify the artifact with `test -s <path>` and `file <path>` before reporting success. Never bypass DRM, login, lending limits, paywalls, or access controls.
5. **Report the real outcome.** If no lawful free copy exists, say so directly, do not provide mirrors or repositories with unclear rights, and give the shortest legal alternative: library lending, controlled borrow, official purchase, or a legitimate preview. Never claim that a download happened merely because a page or URL was found.

## Pitfalls

- Treat repositories, GitHub files, and pages titled “free download” as unauthorized unless the license or publisher authorization is explicit; search indexing does not establish redistribution rights.
- Treat an Internet Archive item marked access-restricted or print-disabled as lending/preview access, not as a free direct download; the presence of scans or metadata does not change the access mode.
- Keep a request for “free” within lawful sources; do not widen it into piracy when the official route is paid or controlled lending.
- Preserve the exact title, creator, and edition while searching; similar names and OCR metadata can silently lead to the wrong work.
- Keep the final response concise: state whether a lawful free file was actually delivered, then give one legal next step if it was not.
