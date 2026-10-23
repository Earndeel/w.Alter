#!/usr/bin/env python3
"""
Secret Key Scanner — SourceGraph + GitHub Raw
Finds exposed API keys in public GitHub repos.
For responsible disclosure / security consulting purposes.
Does NOT test keys against any API.
"""

import re
import json
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PATTERNS = {
    "openai": {
        "name": "OpenAI",
        "regexes": [
            re.compile(r'sk-proj-[A-Za-z0-9_-]{60,}'),
            re.compile(r'sk-[A-Za-z0-9]{48,}'),
        ],
        "sg_queries": ["sk-proj-", "sk-svcacct-", "OPENAI_API_KEY=sk-"],
    },
    "anthropic": {
        "name": "Anthropic / Claude",
        "regexes": [re.compile(r'sk-ant-api03-[A-Za-z0-9_-]{95,}')],
        "sg_queries": ["sk-ant-api03", "ANTHROPIC_API_KEY=sk-ant"],
    },
    "google_ai": {
        "name": "Google AI / Gemini",
        "regexes": [re.compile(r'AIzaSy[A-Za-z0-9_-]{33}')],
        "sg_queries": ["AIzaSy GOOGLE_API_KEY", "GOOGLE_API_KEY=AIzaSy"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "regexes": [re.compile(r'sk-or-v1-[A-Za-z0-9]{64}')],
        "sg_queries": ["sk-or-v1 OPENROUTER_API_KEY", "OPENROUTER_API_KEY=sk-or"],
    },
}

SKIP_REPOS = ["gitleaks", "trufflehog", "detect-secrets", "git-secrets"]
FAKE_INDICATORS = ["example", "sample", "fake", "dummy", "placeholder", "your_", "replace", "xxx"]


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
                            lineMatches { lineNumber preview }
                        }
                    }
                }
            }
        }
        """,
        "variables": {"query": query}
    })
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://sourcegraph.com/.api/graphql",
         "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True, timeout=30
    )
    if not result.stdout:
        return [], 0
    data = json.loads(result.stdout)
    search = data.get("data", {}).get("search", {})
    results = search.get("results", {})
    return results.get("results", []), results.get("matchCount", 0)


def fetch_raw(repo_name, file_path):
    parts = repo_name.replace("github.com/", "").split("/")
    if len(parts) < 2:
        return None
    url = f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/HEAD/{file_path}"
    result = subprocess.run(
        ["curl", "-s", "-L", "--max-time", "10", url],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0 and len(result.stdout) > 10 and "<!DOCTYPE" not in result.stdout[:100]:
        return result.stdout[:100_000]
    return None


def extract_keys(content, provider_key, all_keys):
    found = []
    for pattern in PATTERNS[provider_key]["regexes"]:
        for m in pattern.findall(content):
            if len(m) < 20 or m in all_keys:
                continue
            if any(x in m.lower() for x in FAKE_INDICATORS):
                continue
            all_keys.add(m)
            obf = m[:12] + "..." + m[-6:] if len(m) > 24 else m[:8] + "..."
            found.append({"obfuscated": obf, "length": len(m), "raw": m})
    return found


def run_scan(output_dir="/root/keyscanner/reports"):
    all_keys = set()
    results = []
    seen = set()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for pk, prov in PATTERNS.items():
        print(f"\n[*] {prov['name']}")
        for sq in prov["sg_queries"]:
            print(f"  [>] {sq[:50]}...")
            items, total = sourcegraph_search(sq)
            print(f"    {total} matches, {len(items)} files")

            for item in items:
                repo = item.get("repository", {}).get("name", "?")
                fpath = item.get("file", {}).get("path", "?")
                key = f"{repo}:{fpath}"

                if any(s in repo.lower() for s in SKIP_REPOS):
                    continue
                if key in seen:
                    continue
                seen.add(key)

                content = fetch_raw(repo, fpath)
                if not content:
                    continue

                for k in extract_keys(content, pk, all_keys):
                    results.append({
                        "provider": prov["name"], "provider_key": pk,
                        "repo": repo, "file_path": fpath,
                        "obfuscated_key": k["obfuscated"], "key_length": k["length"],
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                    })
                    print(f"    [!] {k['obfuscated']} in {repo}")
                time.sleep(1.5)
            time.sleep(5)

    # Save
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"scan_{ts}.json", "w") as f:
        json.dump({"timestamp": ts, "total": len(results), "findings": results}, f, indent=2)
    print(f"\n[✓] {len(results)} keys found. Saved to {out}/scan_{ts}.json")


if __name__ == "__main__":
    run_scan()
