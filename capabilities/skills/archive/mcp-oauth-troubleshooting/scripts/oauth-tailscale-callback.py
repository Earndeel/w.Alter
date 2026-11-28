#!/usr/bin/env python3
"""Direct MCP OAuth flow — binds to Tailscale interface for callback.

Usage:
    1. Set TAILSCALE_IP and CALLBACK_PORT below
    2. Run: python3 oauth-tailscale-callback.py <server_name> <server_url>
    3. Open the printed authorization URL in your browser
    4. Authorize → callback hits this server via Tailscale IP → tokens saved

The script registers a dynamic OAuth client, generates PKCE, waits for the
callback, exchanges the code, and writes tokens + client info to:
    ~/.hermes/mcp-tokens/<server_name>.tokens.json
    ~/.hermes/mcp-tokens/<server_name>.client.json
"""
import asyncio, sys, json, hashlib, base64, secrets, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import httpx

# ── Config (EDIT THESE) ──────────────────────────────────────────────────
TAILSCALE_IP = "100.91.35.121"   # Hermes host Tailscale IP
CALLBACK_PORT = 48461            # Free port for callback listener
TOKEN_DIR = Path.home() / ".hermes" / "mcp-tokens"
# ─────────────────────────────────────────────────────────────────────────

REDIRECT_URI = f"http://{TAILSCALE_IP}:{CALLBACK_PORT}/callback"


async def get_metadata(server_url: str):
    """Fetch OAuth authorization server metadata."""
    base = server_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base}/.well-known/oauth-authorization-server")
        r.raise_for_status()
        return r.json()


async def register_client(meta: dict, server_name: str):
    """Dynamic OAuth client registration, saves client.json."""
    body = {
        "client_name": "Hermes Agent",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(meta["registration_endpoint"], json=body)
        r.raise_for_status()
        data = r.json()
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    (TOKEN_DIR / f"{server_name}.client.json").write_text(
        json.dumps(data, indent=2)
    )
    return data["client_id"]


def generate_pkce():
    """Generate PKCE verifier, challenge, and OAuth state."""
    cv = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    cc = (
        base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return cv, cc, secrets.token_urlsafe(32)


def wait_for_callback(port: int = CALLBACK_PORT):
    """Blocking callback server — waits for OAuth redirect."""
    result = {"code": None, "state": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query
            )
            result["code"] = params.get("code", [None])[0]
            result["state"] = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>OK - return to Hermes</h1>")

        def log_message(self, fmt, *args):
            pass  # suppress access logs

    server = HTTPServer(("0.0.0.0", port), Handler)
    server.timeout = 1
    for _ in range(300):  # 5 min max
        server.handle_request()
        if result["code"]:
            break
    server.server_close()
    return result["code"], result["state"]


async def exchange_code(
    meta: dict, client_id: str, code: str, code_verifier: str, server_name: str
):
    """Exchange authorization code for tokens, saves tokens.json."""
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(meta["token_endpoint"], data=body)
        r.raise_for_status()
        tokens = r.json()
    (TOKEN_DIR / f"{server_name}.tokens.json").write_text(
        json.dumps(tokens, indent=2)
    )
    return tokens


async def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <server_name> <server_url>", file=sys.stderr)
        sys.exit(2)

    server_name = sys.argv[1]
    server_url = sys.argv[2]

    print(f"=== {server_name} MCP OAuth (Tailscale bypass) ===", file=sys.stderr)

    meta = await get_metadata(server_url)
    print("✓ Metadata loaded", file=sys.stderr)

    client_id = await register_client(meta, server_name)
    print(f"✓ Client registered: {client_id[:12]}...", file=sys.stderr)

    code_verifier, code_challenge, state = generate_pkce()
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": server_url,
        "scope": "openid email offline_access",
    })
    auth_url = f"{meta['authorization_endpoint']}?{params}"
    print(f"\n📋 {auth_url}\n", file=sys.stderr)
    print(f"⏳ Waiting on {REDIRECT_URI}...", file=sys.stderr)

    code, _ = wait_for_callback()
    if not code:
        print("❌ Timeout — no callback received in 5 min", file=sys.stderr)
        sys.exit(1)

    print("✓ Code received, exchanging...", file=sys.stderr)
    tokens = await exchange_code(meta, client_id, code, code_verifier, server_name)
    print("✓ Tokens saved!", file=sys.stderr)
    print(json.dumps({
        "status": "ok",
        "has_access_token": "access_token" in tokens,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
