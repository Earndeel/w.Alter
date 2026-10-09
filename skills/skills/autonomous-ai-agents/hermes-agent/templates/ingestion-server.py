#!/usr/bin/env python3
"""Minimal data ingestion HTTP server.
Replace SERVICE_NAME, PORT, AUTH_TOKEN, and DATA_FILE.
POST /{endpoint} with JSON body → appends to JSONL.
"""

import json, os, sys, time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# --- CONFIG ---
SERVICE_NAME = "walter-location"
PORT = 5051
AUTH_TOKEN = os.environ.get("LOCATION_AUTH_TOKEN", "changeme")
ENDPOINT = "/location"

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
DATA_DIR = HERMES_HOME / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "locations.jsonl"
HEARTBEAT_FILE = DATA_DIR / "location_heartbeat.json"


class IngestionHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # silent

    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            count = sum(1 for _ in open(DATA_FILE)) if DATA_FILE.exists() else 0
            self._send_json(200, {
                "status": "ok", "service": SERVICE_NAME,
                "total_records": count,
            })
            return
        self._send_json(200, {"service": SERVICE_NAME, "endpoints": [f"POST {ENDPOINT}"]})

    def do_POST(self):
        if self.path != ENDPOINT:
            self._send_json(404, {"error": "not found"})
            return

        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {AUTH_TOKEN}":
            self._send_json(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return

        record = {
            **data,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "source": "http_ingestion",
        }
        with open(DATA_FILE, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self._send_json(201, {"status": "ok", "stored": True})


def main():
    server = HTTPServer(("127.0.0.1", PORT), IngestionHandler)
    print(f"📍 {SERVICE_NAME} listening on 127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
