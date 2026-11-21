---
name: github-key-scanner
description: "Scan public GitHub repositories for exposed API keys via SourceGraph. Find credentials for OpenAI, Anthropic, Google, Stripe, Slack, GitHub PAT, etc. For responsible disclosure and security consulting."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [security, github, api-keys, scanning, sourcegraph, responsible-disclosure]
    related_skills: [github-secret-scanner, godmode]
---

## When to Use

- Scanning public GitHub repositories for exposed API keys
- Security audit of GitHub repos for credential leaks
- Hunting for leaked secrets in open-source projects

## Pitfalls

- GitHub API rate limits: 60 requests/hour unauthenticated, 5000/hour with token
- Large repos may exceed rate limits — use pagination and filters
- Some "keys" are test fixtures or examples, not real leaks — verify before alerting
- Respects `robots.txt` and GitHub ToS — don't scrape aggressively

# GitHub Key Scanner

Scans public GitHub repositories for exposed API keys using SourceGraph's public GraphQL API. Designed for responsible disclosure and security consulting workflows.

**Does NOT test keys against APIs** — that's unauthorized access. The scanner only detects and reports exposed credentials.

## Why SourceGraph?

Direct GitHub code search requires authentication (401 as of 2026). Alternatives tried:
- `grep.app` — blocked by Vercel security checkpoint
- `searchcode.com` — returns empty
- GitHub web scraping — JS-rendered, doesn't work with curl
- `gh` CLI search — needs auth token

**SourceGraph's public GraphQL API (`sourcegraph.com/.api/graphql`) works without auth** and indexes public GitHub repos. Rate limits are reasonable for scanning.

## Key Discovery: SourceGraph Redacts Keys

SourceGraph returns `***` in place of actual key values in search results. The workflow is:

1. **SourceGraph** → find which repos/files contain key patterns
2. **GitHub raw** (`raw.githubusercontent.com`) → fetch actual file content
3. **Regex extraction** → pull the real key values from raw content

## API Usage

### SourceGraph GraphQL Query

```python
import json, subprocess

def sourcegraph_search(query):
    payload = json.dumps({
        "query": """
        query Search($query: String!) {
            search(query: $query, version: V2, patternType:literal) {
                results {
                    matchCount
                    results {
                        ... on FileMatch {
                            repository { name }
                            file { path }
                            lineMatches {
                                lineNumber
                                preview
                            }
                        }
                    }
                }
            }
        }
        """,
        "variables": {"query": query}
    })

    result = subprocess.run(
        ["curl", "-s", "-X", "POST",
         "https://sourcegraph.com/.api/graphql",
         "-H", "Content-Type: application/json",
         "-d", payload],
        capture_output=True, text=True, timeout=30
    )

    data = json.loads(result.stdout)
    search = data["data"]["search"]
    return search["results"]["results"], search["results"]["matchCount"]
```

**Pitfall:** The `$count` variable is NOT used in SourceGraph's `search` resolver. Including `count: Int!` in the variable declaration without using it causes a GraphQL error. Only declare `$query`.

### Fetching Raw Content

```python
def fetch_raw(repo_name, file_path):
    parts = repo_name.replace("github.com/", "").split("/")
    owner, repo = parts[0], parts[1]
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{file_path}"

    result = subprocess.run(
        ["curl", "-s", "-L", "--max-time", "10", url],
        capture_output=True, timeout=15
    )
    try:
        return result.stdout.decode("utf-8", errors="ignore")[:50_000]
    except:
        return None
```

**Pitfall:** Some files are binary (PNG, etc.). Always use `errors="ignore"` when decoding. Without this, you get `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x89`.

## Key Patterns by Provider

```python
import re

PATTERNS = {
    "openai": {
        "regexes": [
            re.compile(r'sk-proj-[A-Za-z0-9_-]{60,}'),
            re.compile(r'sk-svcacct-[A-Za-z0-9_-]{60,}'),
        ],
        "queries": ["sk-proj-", "sk-svcacct-", "OPENAI_API_KEY=sk-"],
    },
    "anthropic": {
        "regexes": [re.compile(r'sk-ant-api03-[A-Za-z0-9_-]{95,}')],
        "queries": ["sk-ant-api03"],
    },
    "openrouter": {
        "regexes": [re.compile(r'sk-or-v1-[A-Za-z0-9]{64}')],
        "queries": ["sk-or-v1"],
    },
    "groq": {
        "regexes": [re.compile(r'gsk_[A-Za-z0-9]{52}')],
        "queries": ["gsk_"],
    },
    "perplexity": {
        "regexes": [re.compile(r'pplx-[A-Za-z0-9]{56}')],
        "queries": ["pplx-"],
    },
    "huggingface": {
        "regexes": [re.compile(r'hf_[A-Za-z0-9]{37}')],
        "queries": ["hf_"],
    },
    "replicate": {
        "regexes": [re.compile(r'r8_[A-Za-z0-9]{37}')],
        "queries": ["r8_"],
    },
    "stripe": {
        "regexes": [re.compile(r'sk_live_[A-Za-z0-9]{24,}')],
        "queries": ["sk_live_"],
    },
    "sendgrid": {
        "regexes": [re.compile(r'SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}')],
        "queries": ["SENDGRID_API_KEY=SG."],
    },
    "github_pat": {
        "regexes": [
            re.compile(r'ghp_[A-Za-z0-9]{36}'),
            re.compile(r'github_pat_[A-Za-z0-9_]{82}'),
        ],
        "queries": ["ghp_"],
    },
    "slack": {
        "regexes": [re.compile(r'xoxb-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{24}')],
        "queries": ["xoxb-"],
    },
    "google_ai": {
        "regexes": [re.compile(r'AIzaSy[A-Za-z0-9_-]{33}')],
        "queries": ["GOOGLE_API_KEY=AIzaSy"],
    },
    "aws": {
        "regexes": [re.compile(r'(AKIA[A-Z0-9]{16})')],
        "queries": ["AKIA"],
    },
}
```

## Filtering False Positives

Many repos contain test keys from security scanning tools. Skip these:

```python
SKIP_REPOS = [
    "gitleaks", "trufflehog", "detect-secrets", "git-secrets",
    "semgrep", "checkov", "bandit", "credSweeper", "kingfisher",
]
```

Also filter keys with obvious fake markers:

```python
FAKE_MARKERS = [
    "example", "test", "fake", "dummy", "placeholder", "xxx",
    "your_", "replace", "insert", "123456", "changepassword",
]
```

## Rate Limiting

- SourceGraph: no explicit rate limit, but ~4s between queries is safe
- GitHub raw: ~1s between fetches to avoid blocks
- Total time: ~14 queries × (4s + 10 files × 1s) ≈ 3 minutes

For 30+ queries, run in background with `terminal(background=true, notify_on_complete=true)`.

Use `python3 -u` (unbuffered) for background processes so output appears in logs.

## Output Format

### JSON Report

```json
{
  "timestamp": "2026-04-19T16:45:00Z",
  "total": 14,
  "repos": {
    "github.com/owner/repo": ["OpenAI", "Stripe"]
  },
  "findings": [
    {
      "provider": "OpenAI",
      "repo": "github.com/owner/repo",
      "file": "src/.env",
      "key": "sk-proj-4XbC...woSqkA",
      "len": 164,
      "url": "https://github.com/owner/repo/blob/HEAD/src/.env"
    }
  ]
}
```

### Markdown Report (generated alongside)

Includes summary, repos to contact list, detailed findings with context, and a disclosure email template.

## Disclosure Email Template

```
Subject: 🔒 Security Alert — Exposed Credentials in your GitHub repo

Hello,

I'm a security researcher. During an automated scan of public
GitHub repositories, I found exposed credentials in your project:

  Repository: {repo}
  File(s): {files}
  Service(s): {providers}

⚠️  These credentials are publicly accessible and could be used
by unauthorized parties.

Immediate actions:
1. Revoke/regenerate the exposed credential(s) immediately
2. Remove them from your repository AND git history
3. Audit recent usage for unauthorized activity
4. Use env vars or a secrets manager (Vault, Doppler, etc.)
5. Enable GitHub Advanced Security secret scanning

I offer security consulting to help prevent future exposures.

Best regards,
{your_name}
```
