"""Minimal Google OAuth/REST helper for Walter Memory connectors (read-only scopes, no SDK).

Token: /root/.hermes/raw-vault/google-walter-memory.json (0600) — refresh token for lucas.jouvencon@gmail.com with
gmail.readonly + calendar.readonly, obtained with `python3 connectors/google_api.py exchange '<callback url>'`.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

CLIENT = Path("/root/.hermes/google-accounts/lucas-jouvenson/google_client_secret.json")
TOKEN = Path("/root/.hermes/raw-vault/google-walter-memory.json")
PENDING = Path("/root/.hermes/raw-vault/.oauth_pending_gmail.json")


def _client() -> dict:
    return json.loads(CLIENT.read_text())["web"]


class Google:
    def __init__(self):
        self.tok = json.loads(TOKEN.read_text())
        self.http = httpx.Client(timeout=60)

    def _access(self) -> str:
        if self.tok.get("expires_at", 0) - 60 < time.time():
            c = _client()
            r = self.http.post("https://oauth2.googleapis.com/token", data={
                "client_id": c["client_id"], "client_secret": c["client_secret"],
                "refresh_token": self.tok["refresh_token"], "grant_type": "refresh_token"})
            r.raise_for_status()
            d = r.json()
            self.tok.update(access_token=d["access_token"], expires_at=time.time() + d["expires_in"])
            old = os.umask(0o077); TOKEN.write_text(json.dumps(self.tok)); os.umask(old)
        return self.tok["access_token"]

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
    p = json.loads(PENDING.read_text())
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
    TOKEN.write_text(json.dumps({"refresh_token": d["refresh_token"], "access_token": d["access_token"],
                                 "expires_at": time.time() + d["expires_in"], "scope": d.get("scope")}))
    os.umask(old)
    PENDING.unlink()
    print("ok, scopes:", d.get("scope"))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "exchange":
        exchange(sys.argv[2])
    else:
        sys.exit("usage: google_api.py exchange '<callback url>'")
