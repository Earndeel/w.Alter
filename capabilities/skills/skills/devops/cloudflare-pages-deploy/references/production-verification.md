# Verify an existing static Pages deployment

- Read back the exact deployment with `GET /accounts/{account_id}/pages/projects/{name}/deployments/{id}` and the project with `GET /accounts/{account_id}/pages/projects/{name}`. Require production environment, successful deploy stage, expected commit metadata, and `canonical_deployment.id` equal to the new deployment id. A successful upload alone does not establish that production changed.
- Compare SHA-256 of every deployed static asset with its source bytes, at both the stable production URL and the immutable deployment URL. Derive the asset count from the source directory instead of assuming a total. Preserve binary data when fetching images and other non-text files.
- Treat Python urllib HTTP 403 as a client-specific observation, not proof that the production site is inaccessible. If the browser loads the site, retry verification using curl before diagnosing a deployment failure or changing Cloudflare settings. Read curl status and Content-Type separately from response bytes.
- Exercise the live app in a fresh isolated browser session, including its normal demonstration unlock flow when documented. Do not alter the owner's stored application data. Query known DOM nodes or use optional chaining; a nonexistent splash element can make a verification expression fail even though the app is working.
- Close only the test tab that you created. Do not close the owner's tabs or kill browser processes.
- Run the repository's documented tests and report actual totals; keep source files unchanged for a deployment-only request.
