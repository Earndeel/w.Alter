---
name: sagora-web-install-validation
description: Use when modifying or validating Sagora's application-installation UI across web browsers, Android, iOS and Android TV.
---

# Sagora installation UI validation

## Locate the implementation and preserve existing work

Work in `/apps/sagora`. Inspect the worktree before changing anything:

```bash
cd /apps/sagora
git status --short
rg -n 'install-app|Download APK|Get the app|Check for updates' code/packages/web/src
rg -n 'name:' code/packages/web/src/lib/hosts/shell/desktop.ts
rg -n 'setDownloadListener|onCreateWindow|ACTION_VIEW|DownloadManager' code/packages/android -g '*.kt'
```

Relevant files include:
- `code/packages/web/src/components/layout.tsx`: navigation placement.
- `code/packages/web/src/components/install-app-drawer.tsx`: installation drawer.
- `code/packages/web/src/lib/install-app.ts`: installation state and APK URLs.
- `code/packages/web/src/components/party/qr-code.tsx`: existing QR implementation.
- `code/packages/web/src/locales/fr.po`, `en-GB.po`, `messages.pot`: translations.
- `code/packages/android/bridge/src/main/kotlin/io/github/viren070/aiostreams/bridge/WebApp.kt`: native WebView capabilities.

Create a fresh backup directory before editing. Do not reuse an old session's temporary release scripts:

```bash
cd /apps/sagora/code/packages/web
backup=$(mktemp -d /tmp/sagora-install.XXXXXX)
cp --parents src/components/layout.tsx src/components/party/qr-code.tsx src/locales/{fr.po,en-GB.po,messages.pot} "$backup"
```

Back up installation files too when they already exist. Inspect the repository's current build and release instructions rather than inventing a deployment command.

## Implement platform-aware behavior

- Check the actual host discriminator. The desktop shell uses `host.name === 'desktop'`, not `'desktop-app'`.
- Keep Android package selection explicit: `arm64-v8a`, `armeabi-v7a`, and `x86_64`.
- Verify generated APK URLs against the current release endpoint; do not guess filenames.
- Inspect native WebView download and external-link handling before assuming an APK anchor works inside the Android app.
- Provide the appropriate browser installation guidance on iOS and desktop instead of presenting Android packages as their primary action.
- Preserve the Android TV remote-control navigation and focus behavior. Put the installation entry immediately above Settings when that placement is requested.
- Update translations alongside UI changes.

## Validate staged assets before publication

Use Playwright to test desktop, Android mobile, iOS and the TV-shell layout separately. A responsive browser simulation does not establish that a physical TV was tested.

Useful selectors from Sagora:

```python
page.locator('[data-ui=home-rows]')
page.locator('[data-ui=mobile-nav] [data-name=account]')
page.locator('[data-ui=tv-rail]')
page.get_by_role('dialog')
```

- Wait for authenticated content and interactive hydration, not merely initial HTML. During this session, mobile menu interactions disappeared before the drawer opened; retrying `click()` versus `tap()` alone did not establish correctness.
- On mobile, open the account menu before locating the installation action if it is absent from the main navigation.
- Assert that the drawer opens, the platform-specific actions are visible, and all expected APK links respond.
- Exercise TV keyboard/remote navigation and confirm focus returns sensibly after closing the drawer.
- Treat a Playwright timeout as a failed or inconclusive check, never as proof that a platform works.

## Avoid PWA-test state contamination

An installation-prompt mock can cause the installation drawer or its available actions to change after the simulated install action.

- Test fallback instructions and APK alternatives before consuming a mocked installation prompt, or use a fresh browser context for each branch.
- Do not keep clicking controls from the pre-install state after the mock has changed application state.
- Separate mocked prompt behavior from a real browser's installability checks.

## Publish and verify without interrupting playback

- Use the repository's verified backup/build/publish procedure, with required authorization.
- Repeat smoke checks against the published site, not only staged assets.
- If public-site tests time out, inspect authentication, loading state and screenshots before blaming the new UI. A direct local-origin test can isolate the issue, but does not substitute for a successful public-origin check.
- If the physical TV is playing media, do not reload or restart it merely to expose the new navigation entry. Report that the entry requires a subsequent app launch or reload and distinguish this from live-device verification.
- Report passed checks, failed checks and untested branches separately. Do not claim all mobile installation flows passed when the recorded checks timed out.
