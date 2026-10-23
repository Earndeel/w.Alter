#!/usr/bin/env python3
"""
beeper_full_sync.py — Captures ALL Beeper conversations from the Beeper Desktop API,
transcribes voice messages via Gemini STT, stores in SQLite, pushes to VM.

Deploy this on the machine where Beeper Desktop runs (Mac or Android).
"""

import json, os, sqlite3, sys, urllib.request, urllib.error, hashlib, subprocess, argparse, base64, time
from datetime import datetime, timezone
from urllib.parse import unquote

# Config
BEEPER_API = "http://127.0.0.1:23373"
BEEPER_MEDIA_DIR = os.path.expanduser("~/Library/Application Support/BeeperTexts/media/local.beeper.com")
DB_PATH = os.path.expanduser("~/Documents/walter_beeper.db")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_STT_MODEL = "gemini-3.1-flash-lite-preview-05-08"

VM_ENDPOINT = os.environ.get("WALTER_VM_URL", "https://walter-ai.cloud/api/beeper/sync")
VM_SECRET = os.environ.get("WALTER_VM_SECRET", "")
MAX_PAGES = 15
PAGE_SIZE = 50


def get_token():
    """Read Beeper token from vault or env."""
    env_token = os.environ.get("BEEPER_API_TOKEN", "")
    if env_token:
        return env_token
    # Try common Mac locations
    for p in [
        os.path.expanduser("~/Library/Application Support/BeeperTexts/api_token.json"),
        os.path.expanduser("~/Library/Application Support/BeeperTexts/preferences.json"),
    ]:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    d = json.load(f)
                    token = d.get("token", d.get("access_token", ""))
                    if token:
                        return token
            except Exception:
                pass
    return ""


def beeper_request(path, params=None):
    token = get_token()
    if not token:
        raise RuntimeError("No Beeper API token found. Set BEEPER_API_TOKEN env var.")
    url = f"{BEEPER_API}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_all_messages(chat_id, max_pages=MAX_PAGES):
    all_msgs, seen, cursor = [], set(), None
    for _ in range(max_pages):
        params = {"limit": str(PAGE_SIZE)}
        if cursor:
            params["cursor"] = str(cursor)
        try:
            data = beeper_request(f"/v1/chats/{chat_id}/messages", params)
        except Exception as e:
            break
        items = data.get("items", [])
        new = [m for m in items if m.get("id") not in seen]
        if not new:
            break
        seen.update(m["id"] for m in new)
        all_msgs.extend(new)
        cursor = items[-1].get("sortKey")
        if not cursor:
            break
    all_msgs.sort(key=lambda m: m.get("sortKey", 0) or m.get("id", 0))
    return all_msgs


def find_media_file(attachment_id):
    """Search Beeper media directory for the file."""
    if os.path.exists(BEEPER_MEDIA_DIR):
        for fname in os.listdir(BEEPER_MEDIA_DIR):
            if attachment_id.endswith(fname) or fname in attachment_id:
                return os.path.join(BEEPER_MEDIA_DIR, fname)
    return None


def transcribe_ogg(ogg_path, gemini_key=GEMINI_API_KEY):
    if not gemini_key:
        return None
    import tempfile
    mp3_path = tempfile.mktemp(suffix=".mp3")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", ogg_path, "-acodec", "libmp3lame", "-q:a", "2", mp3_path],
                       check=True, capture_output=True, timeout=60)
    except Exception:
        return "[transcription failed]"
    with open(mp3_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_STT_MODEL}:generateContent?key={gemini_key}"
        payload = {"contents": [{"parts": [
            {"inline_data": {"mime_type": "audio/mpeg", "data": b64}},
            {"text": "Transcribe this audio verbatim in the original language. Only output the transcription."}
        ]}]}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        text = "".join(p.get("text", "") for c in result.get("candidates", []) for p in c.get("content", {}).get("parts", []))
        return text.strip() if text else None
    except Exception as e:
        return f"[transcription error: {e}]"
    finally:
        try:
            os.unlink(mp3_path)
        except OSError:
            pass


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS conversations (
        chat_id TEXT PRIMARY KEY, title TEXT, chat_type TEXT, account TEXT, last_updated TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS messages (
        text_id TEXT PRIMARY KEY, chat_id TEXT, msg_id INTEGER, sender_name TEXT, sender_id TEXT,
        timestamp TEXT, message_type TEXT, text_content TEXT, transcription TEXT,
        attachment_count INTEGER, raw_json TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(timestamp)")
    conn.commit()
    return conn


def sync(db_path, transcribe=False):
    conn = init_db(db_path)
    chats = beeper_request("/v1/chats").get("items", [])
    total = 0

    for chat in chats:
        cid = chat.get("id", "")
        if not cid:
            continue
        conn.execute("INSERT OR REPLACE INTO conversations VALUES (?,?,?,?,?)",
            (cid, chat.get("title",""), chat.get("type",""), chat.get("accountID",""),
             datetime.now(timezone.utc).isoformat()))

        print(f"Syncing: {chat.get('title','')} ({cid})")
        msgs = get_all_messages(cid)

        for m in msgs:
            mtype = m.get("type", "TEXT")
            sender = m.get("senderName", "unknown")
            text = m.get("text", "").strip()
            atts = m.get("attachments", [])
            transcription = ""

            if transcribe and (mtype == "VOICE" or any(a.get("isVoiceNote") for a in atts)):
                for a in atts:
                    if a.get("isVoiceNote"):
                        path = find_media_file(a.get("id", ""))
                        if path:
                            transcription = transcribe_ogg(path) or ""
                            print(f"  -> {transcription[:120]}")
                        break

            if not text and not transcription:
                if mtype in ("IMAGE","VIDEO","VOICE","CALL","REACTION","STICKER","LOCATION","NOTICE"):
                    text = f"[{mtype}]"

            tid = hashlib.sha256(f"{cid}:{m.get('id')}:{m.get('timestamp')}".encode()).hexdigest()[:32]
            conn.execute("INSERT OR REPLACE INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (tid, cid, m.get("id"), sender, m.get("senderID",""), m.get("timestamp",""),
                 mtype, text, transcription, len(atts), json.dumps(m, ensure_ascii=False)))
            total += 1

        conn.commit()
        print(f"  -> {len(msgs)} messages")

    conn.close()
    print(f"\nDone: {len(chats)} chats, {total} messages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcribe", action="store_true", help="Transcribe voice with Gemini STT")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    sync(args.db, transcribe=args.transcribe)
