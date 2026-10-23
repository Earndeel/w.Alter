---
name: domain-migration-with-deploy
description: Systematic domain URL migration across skills documentation and project code, followed by Cloudflare deployment verification
triggers:
  - "replace domain across skills and project"
  - "migrate walter-ai.cloud to new domain"
  - "update all URLs and deploy to Cloudflare"
  - "find-and-replace domain in skills + codebase"
setup: |
  This skill handles bulk domain replacement when migrating a service to a new domain.
  It covers searching skills docs, project code (excluding artifacts), performing replacements with verification, wrangler dry-run, and auth/secret status reporting before final deploy.
inputs:
  - old_domain: the domain to replace (e.g., "walter-ai.cloud")
  - new_domain: the replacement domain (e.g., "hermes-workspace.com")
  - project_path: path to the main project
  - skill_dirs: list of skill directories (default: all in ~/.hermes/skills/)
  - deploy_ready: boolean — whether to run wrangler dry-run and auth check
steps:
  1. Search for old_domain in all SKILL.md files across skills
  2. Replace in SKILL.md files using sed
  3. Search for old_domain in project (excluding node_modules/dist/build/__pycache__/.git)
  4. Replace in found project files
  5. Verify zero remaining occurrences of old_domain
  6. (If deploy_ready) Run `wrangler deploy --dry-run` after cleaning dist/
  7. (If deploy_ready) Run `wrangler whoami` and `wrangler secret list` to report auth/secrets status
outputs:
  - skills_updated: count of SKILL.md files modified
  - project_files_updated: count of project files modified
  - dry_run_success: boolean (if deploy_ready)
  - auth_status: "AUTHENTICATED" or "NEEDS_LOGIN" (if deploy_ready)
  - deploy_instructions: clear next-step commands
examples:
  - scenario: "Migrate from walter-ai.cloud to hermes-workspace.com"
    inputs:
      old_domain: "walter-ai.cloud"
      new_domain: "hermes-workspace.com"
      project_path: "/root/projects/scena-cloudflare"
      deploy_ready: true
pitfalls:
  - Exclude node_modules/dist/build/__pycache__/.git from replacements
  - Check wrangler.toml for hardcoded BASE_URL vars separately
  - Update cookie Domain in auth.ts if domain-specific
  - Clean dist/ before dry-run to force fresh bundle
  - Use grep -rln to get file list, then loop with sed -i
variations:
  - Add build step (npm run build) before deploy if project uses Vite/other bundlers
  - Multi-worker: repeat per worker directory
  - If using Cloudflare Pages, update pages/ configuration files too
---

## When to Use

- Migrating a service to a new domain (e.g. walter-ai.cloud → hermes-workspace.com)
- Need to bulk-replace URLs across skills documentation and project code
- Preparing a Cloudflare deployment after domain change

## Pitfalls

- Always exclude `node_modules/dist/build/__pycache__/.git` from replacements
- Check `wrangler.toml` for hardcoded `BASE_URL` variables separately
- Update cookie `Domain` in auth.ts if domain-specific
- Clean `dist/` before dry-run to force fresh bundle
- Verify zero remaining occurrences of old domain after replacement
