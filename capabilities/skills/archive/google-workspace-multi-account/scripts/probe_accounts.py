#!/usr/bin/env python3
"""Map every Google token directory in a Hermes home to its Gmail identity + scopes.

Read-only — prints only non-secret metadata (address, message/thread totals,
granted scopes). Never prints token contents. Verification gate BEFORE any
multi-account Gmail audit or routing decision.

Usage:
    python probe_accounts.py [HERMES_HOME]

Discovers:
    <home>/google_token.json                          (primary account)
    <home>/google-accounts/<slug>/google_token.json   (per-account tokens)
"""
import json
import pathlib
import sys

base = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path.home() / ".hermes"

homes = {"primary": base / "google_token.json"}
acct_root = base / "google-accounts"
if acct_root.is_dir():
    for slug in sorted(p.name for p in acct_root.iterdir()):
        tok = acct_root / slug / "google_token.json"
        if tok.exists():
            homes[slug] = tok

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REV = {
    "https://www.googleapis.com/auth/gmail.readonly": "gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send": "gmail.send",
    "https://www.googleapis.com/auth/gmail.modify": "gmail.modify",
    "https://www.googleapis.com/auth/calendar": "calendar",
    "https://www.googleapis.com/auth/drive": "drive",
    "https://www.googleapis.com/auth/spreadsheets": "sheets",
    "https://www.googleapis.com/auth/documents": "docs",
    "https://www.googleapis.com/auth/contacts.readonly": "contacts.readonly",
}

for name, tok in homes.items():
    if not tok.exists():
        print(f"[{name}] NO_TOKEN {tok}")
        continue
    try:
        data = json.loads(tok.read_text())
        scopes = sorted(
            REV.get(s, s.split("/")[-1]) for s in data.get("scopes", [])
        )
        creds = Credentials.from_authorized_user_file(str(tok))
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        prof = svc.users().getProfile(userId="me").execute()
        print(
            f"[{name}] address={prof.get('emailAddress')} "
            f"messages={prof.get('messagesTotal')} threads={prof.get('threadsTotal')}"
        )
        print(f"[{name}] scopes={sorted(scopes)}")
    except Exception as e:  # noqa: BLE001
        print(f"[{name}] ERROR {type(e).__name__}: {e}")

print("\nToken contents are never printed. Route Gmail ops by setting HERMES_HOME to the matching account dir per token.")
