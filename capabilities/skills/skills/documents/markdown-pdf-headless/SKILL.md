---
name: markdown-pdf-headless
description: Use when converting Markdown or HTML to PDF on Monsieur's Ubuntu ARM VM with existing Chromium binaries, especially without installing dependencies or inside a restricted workspace.
---

## Verify available tools before choosing a pipeline

Install nothing when the task forbids it: no apt, pip, npm install, npx downloads or browser downloads.

Check the actual executable, architecture and import availability:

```bash
uname -m
file -L /usr/bin/chromium-browser
/usr/bin/chromium-browser --version
python3 -c 'import markdown'
python3 -c 'import fitz'
node -e "require('marked')"
npm ls -g --depth=0
```

Do not infer browser availability from `which`. During the demonstrated session, `/usr/bin/chromium-browser` was a transitional shell script requiring an absent snap. Puppeteer caches contained x86-64 executables despite directory names suggesting ARM; inspect binaries with `file -L` and run `--version`.

Discover existing alternatives:

```bash
find /root/.cache/puppeteer /root/.cache/ms-playwright -maxdepth 4 -type f \( -name chrome -o -name chrome-headless-shell -o -name headless_shell \) 2>/dev/null
```

The tested working executable was:

```text
/root/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux-arm64/chrome-headless-shell
```

Recheck its existence, architecture and version on each machine. It identified itself as Google Chrome for Testing; if the requirement concerns strictly free distribution rather than the Chromium engine, report this distinction before declaring compliance.

## Produce HTML with an explicit Markdown support boundary

Look for the session's existing converter and wrapper under `/user/Lucas/workspace/e2e/scratch/chromium/`: `md2html.py`, `md2pdf.sh`, and `verify_pdf.py`. Read them before reuse; these are session artifacts, not installed interfaces.

Use an already installed Markdown library when suitable. If none exists, implement only the requested subset with Python stdlib. Escape source text and code, declare UTF-8, and include print CSS for page size, margins, table headers and code wrapping. Exercise headings, lists, tables, fenced code, accents and links. Document unsupported syntax; do not present a small handwritten converter as CommonMark compliant.

## Print within the writable workspace

Use a fresh writable directory for browser state. Restricted sessions may deny `/dev/shm` and the default Chromium configuration directory even when running as root. Redirect HOME only for the browser command; do not change the shell's HOME.

After setting `CHROME` to a verified executable, and `HTML`, `PDF`, and `WORK` to absolute paths:

```bash
mkdir -p "$WORK/home" "$WORK/config" "$WORK/cache" "$WORK/tmp" "$WORK/profile"
HTML_URI=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve().as_uri())' "$HTML")
timeout 90 env HOME="$WORK/home" XDG_CONFIG_HOME="$WORK/config" XDG_CACHE_HOME="$WORK/cache" TMPDIR="$WORK/tmp" \
  "$CHROME" --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --disable-crash-reporter --disable-breakpad \
  --user-data-dir="$WORK/profile" --no-pdf-header-footer \
  --print-to-pdf="$PDF" "$HTML_URI"
test -s "$PDF"
```

Use `--no-sandbox` only where required by the root execution environment, with trusted local input. Keep rendering bounded by a timeout. The tested full browser `chromium-1208` hung, while headless-shell 1248 produced the PDF promptly. Do not repeatedly retry the hung binary. Avoid broad `pkill -f`; clean up only processes owned by this invocation.

Keep `--no-pdf-header-footer`: omitting it stamped the local `file://` path into the output.

## Validate the resulting document

Use installed PyMuPDF (`fitz`) to open the PDF, count pages, extract text, inspect links, page dimensions and fonts. Check actual expected strings, including accents, table cells and code. Generate a multipage fixture and verify every section and code block survives pagination. Render a preview when image viewing is available; otherwise report that visual inspection was unavailable and use geometric checks without claiming visual confirmation.

Do not equate exit status with success: require a nonempty PDF that opens and contains the expected content. Do not promise byte-identical PDFs from one observed pair of matching outputs. Remove only temporary profiles and files created by the current invocation.
