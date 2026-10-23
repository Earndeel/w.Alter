---
name: github-workflow-mastery
description: "Mastery of GitHub development lifecycle: auth, repo management, issue triage, PR workflow, and code review."
version: 1.0.0
author: Orchestra Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Git, PR, Workflow, Code Review, Issues, Auth, CLI]
---

# GitHub Workflow Mastery

A unified, professional-grade class-level skill for managing the complete software development lifecycle on GitHub. Covers authentication, repository creation/forking, issue triage, branching, pull requests, conventional commits, and automated or manual code reviews.

---

## 1. Authentication & environment Setup

To interact with GitHub securely using `git` and the GitHub CLI (`gh`), establish authentication using an HTTPS token or SSH keys.

### GitHub CLI login
Always prefer using the official GitHub CLI (`gh`) for automated tasks:
```bash
# Authenticate using an interactive prompt or non-interactively with a token
echo "$GITHUB_TOKEN" | gh auth login --with-token
```

### Scripted environment
Load helper script `scripts/gh-env.sh` to configure local Git settings such as user identity and credentials.
Always configure Git before attempting commits or PRs:
```bash
git config --global user.name "Hermes Agent"
git config --global user.email "hermes@nousresearch.com"
```

---

## 2. Repository management

Creating, cloning, and managing remote repositories programmatically.

### Cloning and Forking
```bash
# Clone a repository using gh
gh repo clone owner/repo

# Fork a repository to your own account
gh repo fork owner/repo --clone=true
```

### Managing Remotes
When working with forks, configure `upstream` and `origin` appropriately:
```bash
# Add upstream remote
git remote add upstream https://github.com/upstream-owner/repo.git

# Sync fork with upstream main/master
git fetch upstream
git checkout main
git merge upstream/main
```

---

## 3. Issue management & triage

Managing project tracking, bug reports, and feature requests.

### Creating and Querying Issues
```bash
# List open issues with a specific label
gh issue list --label "bug"

# View a specific issue
gh issue view 123

# Create an issue using templates
gh issue create --title "Bug: Crash in memory sync" --body-file "templates/bug-report.md" --label "bug,high-priority"
```

*See `templates/bug-report.md` and `templates/feature-request.md` for standardized forms.*

---

## 4. Pull request workflow

Follow the strict, clean branching and PR creation lifecycle to maintain git log integrity.

### Commit Guidelines & Branching
- Always create a descriptive feature branch (e.g., `feature/auth-refactor` or `bugfix/issue-123`).
- Use **Conventional Commits**:
  - `feat: add Google login button`
  - `fix: clear memory memory leaks in sync`
  - `docs: update setup instructions`

### Creating Pull Requests
```bash
# Push branch to remote origin
git push -u origin branch-name

# Create draft PR or open PR
gh pr create --draft --title "feat: add Google login support" --body-file "templates/pr-body-feature.md"
```

*Standardized PR templates are available at `templates/pr-body-feature.md` and `templates/pr-body-bugfix.md`.*

---

## 5. Code review & feedback

Guidelines for performing robust PR code reviews and generating high-quality developer feedback.

### Fetching and Inspecting PRs
```bash
# Checkout a PR locally for inspection
gh pr checkout 456

# View the diff of a PR
gh pr diff 456
```

### Submitting Reviews
Always provide positive, constructive, and actionable feedback. Group your feedback using `references/review-output-template.md`.
```bash
# Approve a PR
gh pr review 456 --approve --body "Excellent changes! All tests passing locally."

# Request changes with comments
gh pr review 456 --request-changes --body-file "references/review-output-template.md"
```

---

## Support Directory Map
- `references/github-api-cheatsheet.md`: GitHub REST and GraphQL API shortcuts.
- `references/conventional-commits.md`: Standards and examples for clean commit histories.
- `references/ci-troubleshooting.md`: Debugging GitHub Actions CI pipeline failures.
- `references/review-output-template.md`: Structured markdown outline for code reviews.
- `templates/pr-body-feature.md` / `templates/pr-body-bugfix.md`: Standard pull request bodies.
- `templates/bug-report.md` / `templates/feature-request.md`: Unified issue report templates.
- `scripts/gh-env.sh`: Standard Git environment initializer.
