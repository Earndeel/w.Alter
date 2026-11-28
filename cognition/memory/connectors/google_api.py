"""Minimal Google OAuth/REST helper for Walter Memory connectors (read-only scopes, no SDK).

Authorization: Walter's grant `google-memory` (walter-secrets, card in the instance's accounts/): it holds the OAuth
client and the refresh token (gmail.readonly + calendar.readonly) and is the only one renewing the access token.
First consent: `python3 connectors/google_api.py exchange '<callback url>'` writes the grant's token file.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

import httpx

GRANT = "google-memory"


def _grants():
    from walter_secrets import grants   # walter-secrets public library, via the shared runtime
    return grants


def _client() -> dict:
    return json.loads(_grants().access(GRANT, "client"))


class Google:
    def __init__(self):
        self.http = httpx.Client(timeout=60)

    def _access(self) -> str:
        return _grants().access(GRANT)   # fresh access token; renewed by walter-secrets only

    def get(self, url: str, **params) -> dict:
        for attempt in range(5):
            r = self.http.get(url, params={k: v for k, v in params.items() if v is not None},
                              headers={"Authorization": f"Bearer {self._access()}"})
            if r.status_code in (429, 500, 502, 503) or (r.status_code == 403 and "rateLimit" in r.text):
                time.sleep(2 ** attempt); continue
            if r.status_code == 410:
                raise SyncTokenExpired(r.text[:200])
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}


class SyncTokenExpired(RuntimeError):
    pass


def exchange(callback_url: str) -> None:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(callback_url).query)
    token = _grants().location(GRANT)
    pending = token.with_name(".oauth_pending_gmail.json")
    p = json.loads(pending.read_text())
    if q.get("state", [""])[0] != p["state"]:
        sys.exit("state mismatch")
    c = _client()
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": q["code"][0], "client_id": c["client_id"], "client_secret": c["client_secret"],
        "redirect_uri": p["redirect_uri"], "grant_type": "authorization_code", "code_verifier": p["verifier"]})
    r.raise_for_status()
    d = r.json()
    if not d.get("refresh_token"):
        sys.exit("no refresh token returned")
    old = os.umask(0o077)
    token.write_text(json.dumps({"refresh_token": d["refresh_token"], "access_token": d["access_token"],
                                 "expires_at": time.time() + d["expires_in"], "scope": d.get("scope")}))
    os.umask(old)
    pending.unlink()
    print("ok, scopes:", d.get("scope"))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "exchange":
        exchange(sys.argv[2])
    else:
        sys.exit("usage: google_api.py exchange '<callback url>'")
