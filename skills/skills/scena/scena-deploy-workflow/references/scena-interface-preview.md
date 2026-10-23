# Scena Interface Preview Notes

Session-derived convention for the client-facing video workflow page.

## Naming

- Use **Scena Interface** for the client-facing create-video UI.
- Avoid **Scena Demo Studio** in visible UI; “demo” reads too technical/internal.
- Prefer canonical route `/interface`.
- Keep `/demo` only as a legacy alias if already linked externally.

## Visual Target

Minimal Higgsfield-like product surface:

- Dark minimal workspace, not marketing landing page.
- Left column: media mode tabs, `Create video`, brief textarea, asset dropzone, visible primary `Generate` button.
- Right column: output board/canvas with tiles such as Product, Reference, Storyboard, Final, Character sheet, Camera, Hook, Export.
- Provider/model/API key controls belong in an advanced/collapsible section, not the primary flow.
- Workflow chips should not duplicate the primary CTA label; use `Render` or similar for the final stage, not another `Generate`.

## Verification Markers

Static checks should include:

- `<title>Scena Interface — AI Video Engine</title>`
- `Scena Interface`
- `Create video`
- `Drop images or videos`
- `Output board`
- `api/saas/pipeline`
- `storyboard`
- `character sheet`
- `Seedance`
- `X-Scena-Demo-Mode` if preserving simulation/API safety mode

## Preview Before Production

For public Scena UI changes, deploy a Cloudflare Pages preview branch first:

```bash
cd /root/projects/scena-cloudflare
CLOUDFLARE_API_TOKEN=$(vault get cloudflare/api_token) \
  npx wrangler pages deploy pages/portal \
  --project-name=scena-portal \
  --branch interface-minimal \
  --commit-dirty=true
```

Then verify extensionless routes because Cloudflare Pages strips `.html`:

```bash
curl -s https://interface-minimal.scena-portal.pages.dev/interface | grep -Eo '<title>[^<]*</title>|Scena Interface|Create video|Render'
```

Only deploy to production after visual approval unless the user explicitly says to push live.
