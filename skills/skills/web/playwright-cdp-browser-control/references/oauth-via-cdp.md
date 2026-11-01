# OAuth Flows via CDP (Browser on Remote Machine)

When an OAuth provider requires browser interaction but the agent runs on a headless VPS:

## Pattern: CDP + Reverse Tunnel

1. **Start the OAuth process** on VPS (e.g., `hermes auth add xai-oauth --no-browser`)
   - Needs PTY (Python `pty.openpty()`) — many CLIs fail without it
   - Read output to get: callback URL, callback port (dynamic!)
2. **Reverse SSH tunnel** from user's Mac to VPS: `ssh -f -N -R <port>:127.0.0.1:<port> user@mac`
3. **Open auth URL** in user's browser via CDP: `page.goto(auth_url)`
4. **Click authorize** on consent page (detect language — French: "Autoriser", English: "Authorize")
5. **Callback flows** through tunnel → VPS process receives token

## Key Pitfalls

- **Callback port is dynamic** — never hardcode. Read from process output.
- **Don't clear cookies** before OAuth — the user's existing sessions (X, Google) are needed for SSO login flows.
- **Language detection** — consent pages may be in French ("Se connecter avec 𝕏", "Autoriser") or English ("Sign in with X", "Authorize"). Match broadly.
- **Multiple OAuth runs** create duplicate credentials. Clean with `hermes auth remove <provider> <index>`.

## Example: xAI OAuth

```
hermes auth add xai-oauth --no-browser
→ callback on 127.0.0.1:RANDOM_PORT
→ reverse tunnel: ssh -R RANDOM_PORT:127.0.0.1:RANDOM_PORT mac
→ open URL in Brave via CDP
→ user is logged into X → consent page → click authorize
→ token received, stored in hermes auth
```
