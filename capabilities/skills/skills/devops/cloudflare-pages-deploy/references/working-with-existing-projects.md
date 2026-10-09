# Working with Existing Cloudflare Projects

When a user says "the project exists" or "it's already deployed", follow this workflow to discover and integrate with existing infrastructure rather than creating duplicates.

## Discovery Workflow

### 1. Search Session History
```python
session_search(query="project_name", limit=5)
```
Look for previous deployments, architecture discussions, or project structure details.

### 2. Search Filesystem
```bash
find /root/projects -type d -name "*project*" -o -name "*similar_name*"
```
Common locations: `/root/projects/`, `/tmp/`, current working directory.

### 3. List Cloudflare Pages Projects
```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects" \
  -H "Authorization: Bearer {token}" | jq '.result[] | {name, subdomain, domains}'
```

### 4. Read Project Structure
Once found, inspect:
- `wrangler.toml` or `wrangler.json` — bindings, environment vars
- `pages/` directory — existing HTML/JS/CSS
- `workers/` directory — API endpoints, auth handlers
- Database migrations or schema files

## Integration Patterns

### Landing Page with Existing Auth
When adding a landing page to a project with authentication:
1. Read the auth system (custom PBKDF2, Clerk, OAuth, etc.)
2. Identify signup/login routes (e.g., `/signup.html`, `/api/auth/sign-up/email`)
3. Link CTA buttons to existing auth flows: `<a href="/signup.html">`
4. Verify CORS settings in Workers if landing page calls API

### Preserving Existing Infrastructure
- **DO NOT** create new D1 databases, R2 buckets, or Workers if they already exist
- **DO** add new Pages deployments to the existing project name
- **DO** reuse existing environment variables and bindings
- **DO** read the migration files to understand the data model

## Deployment to Existing Project

```bash
cd /path/to/project/pages
CLOUDFLARE_API_TOKEN="*** CLOUDFLARE_ACCOUNT_ID="{id}" \
  npx wrangler pages deploy . --project-name "{existing_project_name}"
```

**Critical**: Use the exact project name from step 3. Deploying to a new project name creates a duplicate with a different `*.pages.dev` subdomain.

## Common Pitfalls

### Project Name Mismatch
User says "fakerich.ai" but project is named "fakereach" on disk/Cloudflare. Always verify the actual project name via API or filesystem before deploying.

**Discovery strategy:**
- Search for both the domain name AND variations (fakerich → fakereach, fakerich-ai)
- Check filesystem: `find /root/projects -name "*fake*"`
- Check Cloudflare API: list all Pages projects and match by subdomain
- The disk name may differ from the Pages project name (e.g., `/root/projects/fakereach/` deploys to `fakerich-ai` Pages project)

### Auth Cookie Domain Mismatch
If the existing auth system sets cookies with a specific domain (e.g., `Domain=fakereach.lucas-jouvencon.workers.dev`), the landing page must use the same domain or the cookies won't be sent. Check the `Set-Cookie` headers in the auth code.

### CORS Restrictions
Existing Workers may have `ALLOWED_ORIGINS` hardcoded. If your landing page is on a different domain, add it to the CORS list or the API calls will fail.

### Static Assets Path
Existing projects often use `/assets/` or `/static/` for CSS/JS/images. Match this convention rather than introducing new paths.

## Verification After Integration

1. **Deploy landing page** to existing Pages project
2. **Test auth flow**: Click signup button → verify redirect to existing signup page
3. **Test API calls**: If landing page makes API calls, verify CORS and auth work
4. **Check cookies**: After login, verify session cookie is set and accessible

## Example Discovery Session

```
User: "Refait la landing page, le projet existe sur Cloudflare"

Agent workflow:
1. session_search("fakerich") → found previous landing page session
2. find /root/projects -name "*fake*" → found /root/projects/fakereach/
3. Read workers/api/src/auth.ts → understood PBKDF2 + HMAC auth
4. Read pages/signup.html → found existing signup flow
5. Generated images, built landing page
6. Deployed with --project-name fakerich-ai (matching existing project)
7. Linked CTA to /signup.html (existing route)
```

Result: Landing page integrated with existing auth system, no duplicate infrastructure.
