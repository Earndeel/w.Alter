"""Bench: same 200 Beeper images as media_triage_jev.py, judged by Cloudflare Clef / Clef-flash, which SEE the image
(resized to 768 px) together with the same pseudonymised message context Jev received.

Monsieur's choice (2026-10-03): images go to Workers AI as-is (Cloudflare: no storage, no training); nudes are
kept (flagged, never treated as junk). Read-only: nothing is written to core.*. Calls are logged in
system.model_calls (processor bench.media_triage, provider cloudflare).

    venv/bin/python bench/media_triage_clef.py --out /root/.hermes/logs/media-triage-test
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from media_triage_jev import NOTE, SELF_NAMES  # noqa: E402
from walter_memory import llm, privacy  # noqa: E402

SHM = Path("/dev/shm/media-triage-review/orig")
PRICE = {"clef": 0.24, "clef-flash": 0.09}  # USD per M input tokens (Workers AI catalogue, 2026-10-03)
NOTE_IMG = NOTE.replace("You cannot see the file itself, only its context.",
                        "You see the image itself plus the message context it was sent in.")

QUESTIONS = {
    "value": {"type": "choice", "instructions": "How valuable would it be for Monsieur's personal long-term memory to "
              "keep and describe this image? Judge the image AND its conversation context. " + NOTE_IMG,
              "criteria": {
                  "high": "Personal or useful: Monsieur's life, people close to him, places, events, intimate or nude "
                          "photos exchanged in a personal relationship; document, receipt, ticket, address, plan, "
                          "information shared on purpose in a real conversation",
                  "medium": "Possibly useful, unclear",
                  "low": "Unlikely to matter: meme, reaction image, forwarded social post or reel, advertising, spam, "
                         "unsolicited message from a stranger, decorative image"}},
    "content": {"type": "choice", "instructions": "What is this image? " + NOTE_IMG,
                "criteria": {
                    "personal_photo": "Photo taken by a person: people, selfie, place, food, object, event",
                    "intimate": "Nude, sexual or intimate photo",
                    "document_or_info": "Document, receipt, ticket, ID-like paper, map, plan, price, schedule, notes",
                    "screenshot": "Screenshot of an app, conversation, website or post",
                    "shared_media": "Meme, reaction image, sticker, GIF frame, forwarded social-media post, reel",
                    "ad_or_spam": "Advertising, promotion, spam, scam, unsolicited marketing",
                    "other": "None of the above"}},
    "processing": {"type": "choice", "instructions": "Which processing should be applied to this image? " + NOTE_IMG,
                   "criteria": {"ocr": "Mostly text to read (document, screenshot, receipt)",
                                "caption": "Mostly visual content to describe (photo)",
                                "both": "Both meaningful text and visual content",
                                "none": "Not worth processing"}},
    "nudity": {"type": "noul", "instructions": "Does the image contain nudity or sexual content?"},
    "people": {"type": "noul", "instructions": "Does the image show at least one real person (face or body)?"},
    "text": {"type": "noul", "instructions": "Does the image contain meaningful readable text?"},
    "sticker_like": {"type": "noul", "instructions": "Is it a sticker, emoji, GIF frame or reaction image?"},
}


def cf_auth() -> tuple[str, dict]:
    get = lambda f: subprocess.run(["walter-secret", "get", "W.Alter · cloudflare", f],  # noqa: E731
                                   check=True, capture_output=True, text=True).stdout.strip()
    # Global key at Monsieur's request (2026-10-03); a Workers-AI-only token would be narrower.
    return get("account_id"), {"X-Auth-Email": "lucas.jouvencon@gmail.com", "X-Auth-Key": get("global_api_key")}


def image_b64(path: Path) -> str:
    with Image.open(path) as im:
        im.seek(0)
        im = ImageOps.exif_transpose(im.convert("RGBA") if im.mode in ("P", "LA") else im)
        im.thumbnail((768, 768))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def call(client: httpx.Client, account: str, headers: dict, model: str, state: str, img: str) -> dict:
    body = {"model": model, "state": json.loads(state), "questions": QUESTIONS,
            "images": [{"content_type": "image/jpeg", "base64": img}]}
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}"
    t0 = time.perf_counter()
    base = dict(processor="bench.media_triage", model=f"@cf/cloudflare/{model}", provider="cloudflare",
                purpose="media triage test (image+context)", budget="backfill", privacy_class="redacted_cloud")
    try:
        r = client.post(url, headers=headers, json=body, timeout=60)
        d = r.json()
        if r.status_code >= 400 or not d.get("success"):
            raise RuntimeError(f"HTTP {r.status_code}: {str(d.get('errors'))[:300]}")
    except Exception as e:
        llm._log(**base, status="error", error=str(e)[:500], latency_ms=int((time.perf_counter() - t0) * 1000))
        raise
    ms = int((time.perf_counter() - t0) * 1000)
    res = d["result"]
    tok = (res.get("usage") or {}).get("input_tokens") or 0
    cost = tok * PRICE[model] / 1e6
    llm._log(**base, status="ok", latency_ms=ms, input_tokens=tok, output_tokens=0, cost_usd=cost)
    a = res["answers"]
    out = {"ms": ms, "tokens": tok, "cost": cost}
    for q, spec in QUESTIONS.items():
        if spec["type"] == "choice":
            out[q], out[f"{q}_confidence"] = a[q]["choice"], a[q]["confidence"]
            out[f"{q}_probs"] = a[q]["probabilities"]
        else:
            out[q] = a[q]["noul"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/.hermes/logs/media-triage-test")
    ap.add_argument("--models", default="clef,clef-flash")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    out = Path(args.out)
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    res_path, prog_path = out / "results_clef.jsonl", out / "progress_clef.json"
    done = {json.loads(line)["object_id"] for line in res_path.read_text().splitlines()} if res_path.exists() else set()
    account, headers = cf_auth()
    models = args.models.split(",")
    t_start, n, errors = time.time(), len(done), 0

    def work(r: dict) -> dict:
        row = {"object_id": r["object_id"]}
        try:
            img = image_b64(SHM / r["storage_key"])
        except Exception as e:  # noqa: BLE001 — HEIC etc.
            return {**row, "error": f"image: {e}"[:200]}
        # Same pseudonymised context Jev received (names were replaced before leaving the VM).
        state = r.get("jev", {}).get("redacted_state")
        if not state:
            raw = json.dumps(r.get("state") or {}, ensure_ascii=False)
            state = privacy.redact(raw, SELF_NAMES)[0]
        with httpx.Client() as client:
            for m in models:
                try:
                    row[m] = call(client, account, headers, m, state, img)
                except Exception as e:  # noqa: BLE001 — recorded, the run continues
                    row[f"{m}_error"] = str(e)[:300]
        return row

    todo = [r for r in rows if r["object_id"] not in done]
    with res_path.open("a") as f, ThreadPoolExecutor(args.workers) as ex:
        for row in ex.map(work, todo):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            errors += sum(1 for k in row if k.endswith("error"))
            prog_path.write_text(json.dumps({"done": n, "total": len(rows), "errors": errors,
                                             "elapsed_s": round(time.time() - t_start)}))
    for p in (res_path, prog_path):
        p.chmod(0o600)
    print(json.dumps(summary(out, models), indent=1, ensure_ascii=False))


def summary(out: Path, models: list[str]) -> dict:
    rows = [json.loads(line) for line in (out / "results_clef.jsonl").read_text().splitlines()]
    s = {"n": len(rows)}
    for m in models:
        ok = [r[m] for r in rows if m in r]
        lat = sorted(x["ms"] for x in ok)
        s[m] = {"ok": len(ok), "errors": len(rows) - len(ok),
                "cost_usd": round(sum(x["cost"] for x in ok), 4),
                "tokens_avg": round(sum(x["tokens"] for x in ok) / len(ok)) if ok else None,
                "latency_ms_p50": lat[len(lat) // 2] if lat else None,
                "latency_ms_p95": lat[int(len(lat) * 0.95) - 1] if lat else None,
                "value": {v: sum(1 for x in ok if x["value"] == v) for v in ("high", "medium", "low")},
                "content": {c: sum(1 for x in ok if x["content"] == c) for c in QUESTIONS["content"]["criteria"]},
                "value_confidence_lt_0.5": sum(1 for x in ok if x["value_confidence"] < 0.5),
                "nudity_gt_0.5": sum(1 for x in ok if x["nudity"] > 0.5),
                "people_gt_0.5": sum(1 for x in ok if x["people"] > 0.5),
                "sticker_like_gt_0.5": sum(1 for x in ok if x["sticker_like"] > 0.5)}
    return s


if __name__ == "__main__":
    main()
