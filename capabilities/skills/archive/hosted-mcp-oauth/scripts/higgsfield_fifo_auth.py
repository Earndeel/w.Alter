#!/usr/bin/env python3
"""Higgsfield OAuth — FIFO-based callback for remote headless environments.

Run this script when Higgsfield MCP tokens are expired and you're on a headless
VM/SSH session where a browser can't redirect to the local callback port.

The user opens the printed AUTH_URL in their local browser, authorizes, then
pastes the resulting redirect URL (localhost:PORT/callback?code=...&state=...)
into the FIFO via `echo 'URL' > /tmp/higgsfield_code`.

On success, tokens are saved to ~/.hermes/mcp-tokens/higgsfield.json (matching Hermes' native MCP token path).
"""
import os, sys, json, asyncio, hashlib, base64, secrets, urllib.parse, select
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TOKEN_DIR = Path(os.path.expanduser("~/.hermes/mcp-tokens"))
TOKEN_DIR.mkdir(parents=True, exist_ok=True)
PORT = 48461
REDIRECT_URI = f"http://localhost:{PORT}/callback"
FIFO_PATH = "/tmp/higgsfield_code"
VERIFIER_PATH = "/tmp/higgsfield_verifier"

class OAuthResult:
    def __init__(self):
        self.code = None

result = OAuthResult()

async def main():
    # 1. Clear old fifo and create new one
    if os.path.exists(FIFO_PATH):
        os.unlink(FIFO_PATH)
    os.mkfifo(FIFO_PATH)
    os.chmod(FIFO_PATH, 0o666)

    # 2. Metadata
    async with __import__("httpx").AsyncClient() as c:
        r = await c.get("https://mcp.higgsfield.ai/.well-known/oauth-authorization-server")
        r.raise_for_status()
        meta = r.json()

    # 3. Register client
    async with __import__("httpx").AsyncClient() as c:
        r = await c.post(meta["registration_endpoint"], json={
            "client_name": "Hermes Agent",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        })
        r.raise_for_status()
        client_data = r.json()
    (TOKEN_DIR / "higgsfield.client.json").write_text(json.dumps(client_data, indent=2))
    client_id = client_data["client_id"]

    # 4. PKCE — save verifier to temp file
    cv = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    cc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).rstrip(b"=").decode()
    state_val = secrets.token_urlsafe(32)
    Path(VERIFIER_PATH).write_text(json.dumps({"code_verifier": cv, "state": state_val, "client_id": client_id}))

    # 5. Authorize URL
    auth_url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id,
        "redirect_uri": REDIRECT_URI, "state": state_val,
        "code_challenge": cc, "code_challenge_method": "S256",
        "resource": "https://mcp.higgsfield.ai/",
        "scope": "openid email offline_access",
    })

    print(f"AUTH_URL:{auth_url}", flush=True)

    # 6. HTTP callback handler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path).query
            p = urllib.parse.parse_qs(q)
            result.code = p.get("code", [None])[0]
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(b"<h1>OK</h1>")
        def log_message(self, f, *a): pass

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    server.timeout = 0.25

    # 7. Open FIFO (non-blocking for polling)
    fifo = os.open(FIFO_PATH, os.O_RDONLY | os.O_NONBLOCK)

    # 8. Poll loop: HTTP server + FIFO
    stdin_buf = b""
    for i in range(1200):  # 5 min
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
            # Parse any complete lines
            text = stdin_buf.decode("utf-8", errors="ignore")
            for line in text.split("\n"):
                line = line.strip()
                if ("?code=" in line or "code=" in line) and "oauth2/authorize" not in line:
                    query = line.split("?", 1)[1] if "?" in line else line
                    if query.startswith("?"):
                        query = query[1:]
                    try:
                        params = urllib.parse.parse_qs(query)
                        result.code = params.get("code", [None])[0]
                    except Exception:
                        pass
                    if result.code:
                        break

        await asyncio.sleep(0.25)

    server.server_close()
    os.close(fifo)
    os.unlink(FIFO_PATH)

    if not result.code:
        print("TIMEOUT", flush=True)
        sys.exit(1)

    print("CODE_RECEIVED", flush=True)

    # 9. Exchange code for tokens
    verifier_data = json.loads(Path(VERIFIER_PATH).read_text())
    async with __import__("httpx").AsyncClient() as c:
        r = await c.post(meta["token_endpoint"], data={
            "grant_type": "authorization_code",
            "code": result.code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier_data["code_verifier"],
        })
        if r.status_code != 200:
            print(f"TOKEN_ERROR:{r.status_code}:{r.text}", flush=True)
            sys.exit(1)
        tokens = r.json()

    (TOKEN_DIR / "higgsfield.json").write_text(json.dumps(tokens, indent=2))
    print("SUCCESS", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
