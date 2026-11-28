#!/usr/bin/env python3
"""Least-privilege Gmail OAuth helper for per-account mailbox analysis."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_REDIRECT = "http://localhost/"


def home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def client_path() -> Path:
    return home() / "google_client_secret.json"


def token_path() -> Path:
    return home() / "google_token.json"


def pending_path() -> Path:
    return home() / "google_oauth_pending.json"


def redirect_uri() -> str:
    return os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", DEFAULT_REDIRECT)


def require_client() -> None:
    if not client_path().exists():
        raise SystemExit(f"Missing OAuth client: {client_path()}")
    home().mkdir(parents=True, exist_ok=True)


def auth_url() -> None:
    require_client()
    flow = Flow.from_client_secrets_file(
        str(client_path()), scopes=SCOPES, redirect_uri=redirect_uri(), autogenerate_code_verifier=True
    )
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    pending_path().write_text(json.dumps({
        "state": state,
        "code_verifier": flow.code_verifier,
        "redirect_uri": redirect_uri(),
        "scopes": SCOPES,
    }, indent=2))
    print(json.dumps({"auth_url": url, "scopes": SCOPES}, ensure_ascii=False))


def extract_callback(value: str) -> tuple[str, str | None]:
    if not value.startswith("http"):
        return value, None
    query = parse_qs(urlparse(value).query)
    if "error" in query:
        raise SystemExit(f"OAuth error: {query['error'][0]}")
    if "code" not in query:
        raise SystemExit("The callback URL has no code parameter")
    return query["code"][0], (query.get("state") or [None])[0]


def auth_code(value: str) -> None:
    require_client()
    if not pending_path().exists():
        raise SystemExit(f"Missing pending OAuth session: {pending_path()}")
    pending = json.loads(pending_path().read_text())
    code, returned_state = extract_callback(value)
    if returned_state and returned_state != pending.get("state"):
        raise SystemExit("OAuth state mismatch; start a fresh auth-url flow")
    flow = Flow.from_client_secrets_file(
        str(client_path()), scopes=pending.get("scopes", SCOPES),
        redirect_uri=pending.get("redirect_uri", redirect_uri()),
        state=pending["state"], code_verifier=pending["code_verifier"],
    )
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow.fetch_token(code=code)
    creds = flow.credentials
    payload = json.loads(creds.to_json())
    payload["scopes"] = list(creds.granted_scopes or SCOPES)
    payload["requested_scopes"] = SCOPES
    token_path().write_text(json.dumps(payload, indent=2))
    pending_path().unlink(missing_ok=True)
    print(json.dumps({"status": "authenticated", "token": str(token_path())}, ensure_ascii=False))


def verify() -> None:
    if not token_path().exists():
        raise SystemExit(f"Missing token: {token_path()}")
    creds = Credentials.from_authorized_user_file(str(token_path()))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path().write_text(creds.to_json())
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    print(json.dumps({"emailAddress": profile.get("emailAddress"), "messagesTotal": profile.get("messagesTotal"), "threadsTotal": profile.get("threadsTotal")}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("auth-url")
    code_parser = sub.add_parser("auth-code")
    code_parser.add_argument("callback")
    sub.add_parser("verify")
    args = parser.parse_args()
    if args.command == "auth-url":
        auth_url()
    elif args.command == "auth-code":
        auth_code(args.callback)
    else:
        verify()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
