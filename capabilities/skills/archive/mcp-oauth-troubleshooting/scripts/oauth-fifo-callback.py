#!/usr/bin/env python3
"""OAuth authorization_code + PKCE flow with FIFO-based callback delivery.

Use when:
- `process submit` stdin is unavailable (non-local Hermes backend)
- `curl` to a running listener isn't viable (custom script, no `hermes mcp login`)
- The OAuth provider accepts `http://localhost` redirects

How it works:
1. Registers a dynamic OAuth client, generates PKCE, saves verifier to disk
2. Starts an HTTP callback server on `localhost:<port>`
3. Opens a named pipe (FIFO) at `<fifo_path>` and polls both HTTP + FIFO
4. The agent echoes the user's callback URL into the FIFO via a separate terminal call
5. On code receipt (HTTP or FIFO), exchanges for tokens and saves them

Usage:
  python3 oauth-fifo-callback.py \\
    --server-url https://mcp.example.com/mcp \\
    --token-dir ~/.hermes/mcp-tokens \\
    --server-name myserver \\
    --port 48461

The FIFO path defaults to /tmp/oauth_fifo_<server-name>.
After the script prints AUTH_URL, give that URL to the user.
When the user provides the redirect URL, deliver it via:
  echo '<redirect-url>' > /tmp/oauth_fifo_<server-name>
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import select
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx


class OAuthResult:
    def __init__(self):
        self.code = None


async def get_metadata(server_url: str) -> dict:
    """Fetch OAuth authorization server metadata."""
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{server_url}/.well-known/oauth-authorization-server")
        r.raise_for_status()
        return r.json()


async def register_client(meta: dict, redirect_uri: str) -> dict:
    """Dynamic OAuth client registration."""
    async with httpx.AsyncClient() as c:
        r = await c.post(meta["registration_endpoint"], json={
            "client_name": "Hermes Agent",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        })
        r.raise_for_status()
        return r.json()


def generate_pkce() -> tuple[str, str, str]:
    """Returns (code_verifier, code_challenge, state)."""
    cv = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).rstrip(b"=").decode()
    state_val = secrets.token_urlsafe(32)
    return cv, cc, state_val


def parse_code_from_text(text: str) -> str | None:
    """Extract authorization code from a raw string (URL or query fragment)."""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "oauth2/authorize" in line:
            continue  # Skip authorize URLs, only accept callback URLs
        if "code=" not in line:
            continue
        query = line.split("?", 1)[1] if "?" in line else line
        if query.startswith("?"):
            query = query[1:]
        try:
            params = urllib.parse.parse_qs(query)
            code = params.get("code", [None])[0]
            if code:
                return code
        except Exception:
            pass
    return None


async def main():
    parser = argparse.ArgumentParser(description="OAuth PKCE flow with FIFO callback")
    parser.add_argument("--server-url", required=True, help="MCP server base URL")
    parser.add_argument("--token-dir", required=True, help="Hermes MCP token directory")
    parser.add_argument("--server-name", required=True, help="Short name for token filenames")
    parser.add_argument("--port", type=int, default=48461, help="Callback HTTP port")
    parser.add_argument("--fifo-path", default=None, help="Named pipe path (default: /tmp/oauth_fifo_<server-name>)")
    parser.add_argument("--scope", default="openid email offline_access", help="OAuth scopes")
    parser.add_argument("--resource", default=None, help="OAuth resource parameter")
    parser.add_argument("--timeout", type=int, default=300, help="Max wait seconds for callback")
    args = parser.parse_args()

    token_dir = Path(args.token_dir)
    token_dir.mkdir(parents=True, exist_ok=True)
    redirect_uri = f"http://localhost:{args.port}/callback"
    fifo_path = args.fifo_path or f"/tmp/oauth_fifo_{args.server_name}"
    verifier_path = f"/tmp/oauth_verifier_{args.server_name}.json"

    result = OAuthResult()

    # 1. Metadata
    meta = await get_metadata(args.server_url)

    # 2. Register client
    client_data = await register_client(meta, redirect_uri)
    (token_dir / f"{args.server_name}.client.json").write_text(json.dumps(client_data, indent=2))
    client_id = client_data["client_id"]

    # 3. PKCE — save verifier for token exchange
    cv, cc, state_val = generate_pkce()
    Path(verifier_path).write_text(json.dumps({
        "code_verifier": cv,
        "state": state_val,
        "client_id": client_id,
    }))

    # 4. Build authorize URL
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state_val,
        "code_challenge": cc,
        "code_challenge_method": "S256",
        "scope": args.scope,
    }
    if args.resource:
        params["resource"] = args.resource

    auth_url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
    print(f"AUTH_URL:{auth_url}", flush=True)

    # 5. HTTP callback handler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path).query
            p = urllib.parse.parse_qs(q)
            result.code = p.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>OK</h1>")

        def log_message(self, f, *a):
            pass

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    server.timeout = 0.25

    # 6. Set up FIFO
    if os.path.exists(fifo_path):
        os.unlink(fifo_path)
    os.mkfifo(fifo_path)
    os.chmod(fifo_path, 0o666)
    fifo = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)

    # 7. Poll loop
    stdin_buf = b""
    max_iterations = int(args.timeout / 0.25)
    for _ in range(max_iterations):
        try:
            server.handle_request()
        except Exception:
            pass
        if result.code:
            break

        # Check FIFO
        r, _, _ = select.select([fifo], [], [], 0)
        if r:
            try:
                chunk = os.read(fifo, 4096)
                if chunk:
                    stdin_buf += chunk
            except BlockingIOError:
                pass
            text = stdin_buf.decode("utf-8", errors="ignore")
            code = parse_code_from_text(text)
            if code:
                result.code = code
                break

        await asyncio.sleep(0.25)

    server.server_close()
    os.close(fifo)
    os.unlink(fifo_path)

    if not result.code:
        print("TIMEOUT", flush=True)
        sys.exit(1)

    print("CODE_RECEIVED", flush=True)

    # 8. Exchange code for tokens
    verifier_data = json.loads(Path(verifier_path).read_text())
    async with httpx.AsyncClient() as c:
        r = await c.post(meta["token_endpoint"], data={
            "grant_type": "authorization_code",
            "code": result.code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier_data["code_verifier"],
        })
        if r.status_code != 200:
            print(f"TOKEN_ERROR:{r.status_code}:{r.text[:500]}", flush=True)
            sys.exit(1)
        tokens = r.json()

    (token_dir / f"{args.server_name}.tokens.json").write_text(json.dumps(tokens, indent=2))
    Path(verifier_path).unlink(missing_ok=True)
    print("SUCCESS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
