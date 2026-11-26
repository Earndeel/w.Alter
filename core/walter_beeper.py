"""Beeper's native channel: a small REST/WS client, not a runtime or a second message store.

Read credentials only through Walter Secrets. Message writes are exposed by the Engine's
existing MCP/policy path; this transport deliberately never retries a message send.
"""
from __future__ import annotations

import json
import subprocess
import time
import tomllib
import urllib.parse
from functools import lru_cache
from pathlib import Path

import httpx


class BeeperAPIError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"Beeper API HTTP {status}")  # never include headers, response bodies or message text


@lru_cache(maxsize=1)
def settings() -> dict:
    r = subprocess.run(["walter", "instance", "config", "core", "beeper.toml"],
                       capture_output=True, text=True, check=True, timeout=10)
    doc = tomllib.loads(Path(r.stdout.strip()).read_text())
    base = str(doc.get("api_url", "http://127.0.0.1:23374")).rstrip("/")
    u = urllib.parse.urlsplit(base)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("Invalid Beeper API origin")
    return {"api_url": base, "grant": doc.get("grant", "beeper-server"),
            "checkpoint_scope": doc.get("checkpoint_scope", "server"),
            "reconcile_days": int(doc.get("reconcile_days", 1)), "cutover_at": doc.get('cutover_at')}


class BeeperClient:
    def __init__(self, consumer: str = "memory", *, writable: bool = False,
                 config: dict | None = None, token: str | None = None, transport=None):
        self.config = dict(settings() if config is None else config)
        self.checkpoint_scope = self.config["checkpoint_scope"]
        self.cutover_at = self.config.get('cutover_at')
        self.consumer = consumer
        self.writable = writable and consumer == "engine"
        if token is None:
            try:
                from walter_secrets import grants
            except ModuleNotFoundError as exc:
                if exc.name != 'walter_secrets':
                    raise
                # Standalone MCP venvs use Secrets' declared CLI, the same named grant and reader.
                # Capture the value only inside this process; never include it in argv or errors.
                grant = subprocess.run(['walter-secret', 'grant', 'access', self.config['grant'], '--as', consumer],
                    capture_output=True, text=True, timeout=45)
                if grant.returncode or not grant.stdout.strip():
                    raise PermissionError('Beeper Secrets grant unavailable')
                token = grant.stdout.strip()
            else:
                token = grants.access(self.config["grant"], consumer=consumer)
        self.http = httpx.Client(base_url=self.config["api_url"],
            headers={"Authorization": f"Bearer {token}"}, timeout=60,
            transport=transport, trust_env=False, follow_redirects=False)

    def close(self):
        self.http.close()

    def get(self, path: str, **params):
        for attempt in range(4):
            try:
                r = self.http.get(path, params={k: v for k, v in params.items() if v is not None})
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < 3:
                        time.sleep(min(2 ** attempt, 8))
                        continue
                if not r.is_success:
                    raise BeeperAPIError(r.status_code)
                return r.json()
            except httpx.TransportError:
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))

    def chats(self) -> list[dict]:
        out, cursor, seen = [], None, set()
        while True:
            d = self.get("/v1/chats", limit=100, cursor=cursor, direction="before" if cursor else None)
            out.extend(d["items"])
            cursor = d.get("oldestCursor")
            if not d.get("hasMore") or not cursor:
                return out
            if cursor in seen:
                raise RuntimeError("Beeper repeated a chat pagination cursor")
            seen.add(cursor)

    def chat(self, chat_id: str) -> dict:
        return self.get("/v1/chats/" + urllib.parse.quote(chat_id, safe=""))

    def messages(self, chat_id: str, cursor: str | None = None, direction: str | None = None) -> dict:
        return self.get(f"/v1/chats/{urllib.parse.quote(chat_id, safe='')}/messages", cursor=cursor, direction=direction)

    def message(self, chat_id: str, message_id: str) -> dict:
        return self.get(f"/v1/chats/{urllib.parse.quote(chat_id, safe='')}/messages/{urllib.parse.quote(message_id, safe='')}")

    def send_text(self, chat_id: str, text: str, reply_to: str = "") -> dict:
        if not self.writable:
            raise PermissionError("Message writes require Walter Engine")
        if not chat_id.startswith("!") or not text.strip():
            raise ValueError("Full chat ID and non-empty text required")
        body = {"text": text}
        if reply_to:
            body["replyToMessageID"] = reply_to
        # NO automatic retry: a timeout after acceptance is ambiguous, and a second POST could send twice.
        r = self.http.post(f"/v1/chats/{urllib.parse.quote(chat_id, safe='')}/messages", json=body)
        if not r.is_success:
            raise BeeperAPIError(r.status_code)
        return r.json()

    def websocket(self):
        from websockets.sync.client import connect
        endpoint = self.get("/v1/info").get("endpoints", {}).get("ws_events", "/v1/ws")
        url = urllib.parse.urljoin(self.config["api_url"] + "/", endpoint)
        u, base = urllib.parse.urlsplit(url), urllib.parse.urlsplit(self.config["api_url"])
        if (u.hostname, u.port) != (base.hostname, base.port) or u.query or u.username or u.password:
            raise ValueError("Beeper advertised a WebSocket outside its API origin")
        url = urllib.parse.urlunsplit(("wss" if u.scheme == "https" else "ws", u.netloc, u.path, "", ""))
        return connect(url, additional_headers={"Authorization": self.http.headers["Authorization"]},
                       open_timeout=10, close_timeout=5, ping_interval=20, ping_timeout=20, max_size=8 << 20)


def read(operation: str, *, chat_id: str = "", query: str = "", cursor: str = "", direction: str = "before",
         limit: int = 20, consumer: str = "engine") -> dict | list:
    if direction not in ("before", "after"):
        raise ValueError("Invalid pagination direction")
    api = BeeperClient(consumer)
    try:
        params = {"cursor": cursor or None, "direction": direction if cursor else None}
        if operation == "status":
            return api.get("/v1/app/setup")
        if operation == "accounts":
            return api.get("/v1/accounts")
        if operation == "chats":
            return api.get("/v1/chats", limit=max(1, min(100, limit)), **params)
        if operation == "messages" and chat_id.startswith("!"):
            return api.messages(chat_id, cursor or None, direction if cursor else None)
        if operation == "search":
            return api.get("/v1/messages/search", query=query, limit=max(1, min(20, limit)),
                           chatIDs=[chat_id] if chat_id else None, **params)
        raise ValueError("Unsupported read operation or missing full chat ID")
    finally:
        api.close()


def engine_policy_enabled() -> bool:
    try:
        r = subprocess.run(["walter", "instance", "config", "core", "engine.toml"],
                           capture_output=True, text=True, check=True, timeout=10)
        doc = tomllib.loads(Path(r.stdout.strip()).read_text())
        return doc.get("dsh", {}).get("engine", {}).get("policy") == "enforce"
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def register(mcp, client: str, local_control: bool):
    from mcp.types import ToolAnnotations

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def beeper_read(operation: str = "chats", chat_id: str = "", query: str = "", cursor: str = "",
                    direction: str = "before", limit: int = 20) -> str:
        """Read Walter's native Beeper Server (status/accounts/chats/messages/search), no Mac needed.
        Use full !... chat IDs. Returns one page and cursors; search is literal. Never marks messages read.
        Outgoing messages use beeper_send_message through Walter Engine's permission/disclosure checks."""
        try:
            return json.dumps(read(operation, chat_id=chat_id, query=query, cursor=cursor,
                                   direction=direction, limit=limit), ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": type(exc).__name__,
                               "hint": "Check beeper-server and its Walter Secrets grant."})

    # No write surface for external dev clients, HTTP MCP, or an Engine without its existing policy plugin.
    if client not in ("engine", "dsh") or not local_control or not engine_policy_enabled():
        return

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def beeper_send_message(chat_id: str, text: str, reply_to: str = "") -> str:
        """Send/reply through native Beeper Server as Monsieur. Walter Engine permission and disclosure
        checks apply; child/command sessions are refused. Full !... chat ID required. No automatic retry:
        if the result is uncertain, inspect history before deciding whether to send again.
        Does not edit bridges, delete messages, mark read or reset recovery keys."""
        if not engine_policy_enabled():
            raise PermissionError("Walter Engine policy is not enforced")
        api = BeeperClient("engine", writable=True)
        try:
            return json.dumps(api.send_text(chat_id, text, reply_to), ensure_ascii=False)
        except (httpx.TransportError, TimeoutError):
            return json.dumps({"ok": False, "delivery": "unknown", "retry_automatically": False,
                               "hint": "Inspect chat history before any retry."})
        finally:
            api.close()
