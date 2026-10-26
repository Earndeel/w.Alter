"""Direct media generation (image, video, music, voice) on the model the router picked.

Flow: decision (role by objective, the owner's favourite) -> mode (t2i/i2i/t2v/i2v/r2v) -> prompt rewritten by the
economic text tier following the model's prompt style -> optional workflow (Seedance premium: a reference still is
generated first with the image favourite) -> provider in the owner's order (Kie when available and not more than
25 % dearer than OpenRouter, OpenRouter otherwise; a UI-only route such as Flow is returned as manual unless a paid
fallback is allowed) -> submit, poll, download -> models.exec_log.

APIs: Kie market `POST /api/v1/jobs/createTask` + `GET /api/v1/jobs/recordInfo?taskId=` (docs.kie.ai, schemas in
config/kie_media_schemas.json); OpenRouter `POST /api/v1/videos` + polling URL + content URL, and
`POST /api/v1/images` (b64_json) (openrouter.ai/docs, 2026-10-02).
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from walter_router import paths
from walter_router import instance
from walter_router.serve import execution
from walter_router.analysis import select as sel

CONFIG = paths.CONFIG
OUT_DIR = instance.hermes_home() / "generated" / "walter-router"
UA = execution.UA
KIE = "https://api.kie.ai"
OPENROUTER = "https://openrouter.ai/api/v1"
KIE_USD_PER_CREDIT = 0.005          # 6 credits = 0.03 $ (Sunburst 1K, 2026-10-02)
TIMEOUTS = {"image": 360, "video": 1200, "music": 600, "audio": 300}
HERMES = instance.hermes_bin()


def _models() -> dict:
    return json.loads((CONFIG / "media_models.json").read_text())["models"]


def _schemas() -> dict:
    return json.loads((CONFIG / "kie_media_schemas.json").read_text())["models"]


def _http(method: str, url: str, headers: dict, body: dict | None = None, timeout: int = 60) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers={"User-Agent": UA, "Content-Type": "application/json",
                                                          **headers})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed provider hosts)
        raw = resp.read(200 * 1024 * 1024)
    return json.loads(raw) if raw.lstrip()[:1] in (b"{", b"[") else raw


# --- parameters -----------------------------------------------------------------------------------------

def _nearest(value: Any, allowed: list) -> Any:
    """Closest allowed value (case-insensitive for strings, numeric distance for numbers/durations)."""
    if value is None or not allowed:
        return value
    low = {str(a).lower(): a for a in allowed}
    if str(value).lower() in low:
        return low[str(value).lower()]
    from walter_router.analysis import media
    if all(re.fullmatch(r"\d+(\.\d+)?[pk]", str(a).lower()) for a in allowed) and \
            re.fullmatch(r"\d+(\.\d+)?[pk]", str(value).lower()):  # resolutions: compare pixel heights
        norm = lambda r: media.resolution_rank(str(r).upper() if str(r).lower().endswith("k") else str(r).lower())
        return min(allowed, key=lambda a: abs(norm(a) - norm(value)))
    try:
        v = float(re.sub(r"[^\d.]", "", str(value)))
        nums = [(abs(float(re.sub(r"[^\d.]", "", str(a))) - v), a) for a in allowed if re.search(r"\d", str(a))]
        return min(nums)[1] if nums else allowed[0]
    except ValueError:
        return allowed[0]


def coerce(path: str, params: dict) -> dict:
    """Keep only the fields the Kie model accepts, mapped to its allowed values (duration, resolution, ratio)."""
    schema = _schemas().get(path)
    if not schema:
        return params
    out = {}
    for k, v in params.items():
        spec = schema["properties"].get(k)
        if spec is None or v is None:
            continue
        if "enum" in spec:
            v = _nearest(v, spec["enum"])
        elif spec.get("type") == "integer":
            v = int(round(float(v)))
            if "minimum" in spec:
                v = max(v, spec["minimum"])
            if "maximum" in spec:
                v = min(v, spec["maximum"])
        out[k] = v
    for k in schema.get("required") or []:
        if k not in out and "default" in schema["properties"].get(k, {}):
            out[k] = schema["properties"][k]["default"]
    return out


# --- prompt crafting (economic tier) --------------------------------------------------------------------

def craft_prompt(conn, request: str, style: str | None) -> str:
    """Rewrite the owner's request in the model's prompt style with the economic text tier (L1, via Hermes).
    Falls back to the request itself."""
    if not style:
        return request
    from walter_router.serve import choose
    try:
        d = choose.pick(conn, "general", "L1")
        route = next((r for r in execution.routes(conn, d["model_id"], d.get("variant") or "")
                      if r.get("probe_ok") is not False), None)
        if not route:
            return request
        q = (f"Réécris cette demande de {instance.owner()} en prompt pour un modèle génératif. Consigne de style : {style}\n"
             f"Réponds UNIQUEMENT par le prompt final, sans guillemets ni commentaire.\n\nDemande : {request}")
        cmd = [str(HERMES), "chat", "-q", q, "--oneshot", "-Q", "--provider", route["hermes_provider"], "-m",
               route["model"], "-t", "memory", "--max-turns", "1", "--source", "walter-router-prompt"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                             env=instance.child_env(WALTER_ROUTER_CHILD="1"))
        lines = [ln for ln in re.sub(r"\x1b\[[0-9;]*m", "", out.stdout).splitlines()
                 if ln.strip() and not ln.startswith(("session_id:", "⚠", "Warning:")) and "hermes doctor" not in ln]
        text = "\n".join(lines).strip().strip('"')
        return text if len(text) > 15 else request
    except Exception:  # noqa: BLE001 — a raw prompt is better than no generation
        return request


# --- providers ------------------------------------------------------------------------------------------

def openrouter_id(conn, model_id: str) -> str | None:
    snaps = sel.latest_snapshots(conn)
    row = conn.execute("""select offer_key from models.offers where snapshot_id = %s and provider = 'openrouter'
                          and model_id = %s order by length(offer_key) limit 1""",
                       (snaps.get("openrouter"), model_id)).fetchone()
    return row["offer_key"].split(" | ")[0] if row else None


def choose_provider(conn, model_id: str, interface: str, resolution: str | None, has_kie_path: bool,
                    or_id: str | None) -> list[str]:
    """The owner's order for paid media: Kie if it has the model and is not > 25 % dearer than OpenRouter at this
    resolution, then OpenRouter (last when its credit is exhausted). A provider the last probe saw down
    (models.provider_status) goes last."""
    offers = sel.load_offers(conn, sel.latest_snapshots(conn)).get(model_id, [])

    def price(provider: str) -> float | None:
        p = [o["norm_price"] for o in offers if o["provider"] == provider and o["interface"] == interface
             and o.get("norm_price") is not None and o.get("offer_kind") == "generation"
             and (not resolution or not o.get("resolution") or o["resolution"].lower() == resolution.lower())]
        return min(p) if p else None

    status = {r["provider"]: r["ok"] for r in conn.execute("select provider, ok from models.provider_status")}
    or_down, kie_down = status.get("openrouter") is False, status.get("kie") is False
    kie_p, or_p = price("kie"), price("openrouter")
    order = []
    if has_kie_path and not (kie_down and or_id) and \
            (or_p is None or kie_p is None or kie_p <= or_p * execution.KIE_MAX_PREMIUM or or_down):
        order.append("kie")
    if or_id:
        order.append("openrouter")
    if has_kie_path and "kie" not in order:
        order.append("kie")
    return order


def fallback_models(conn, task: str, role: str | None, model_id: str, mode: str | None = None, n: int = 2,
                    declared_only: bool = True) -> list[str]:
    """Other models to try when every provider of `model_id` failed. Since 2026-10-22 (owner: « le secours, c'est pas
    le modèle mais plutôt le provider ») the fallback of a media task is the SAME model on its other providers
    (generate's provider loop); another model is used only when the owner declared it (knowledge.json
    roles.<role>.fallback). declared_only=False gives the former computed list (composite order, same price class
    for ratio / budget roles), kept for the dossier."""
    from walter_router.analysis import knowledge
    from walter_router.analysis.scoring import composite
    declared = ((knowledge.load().get("roles") or {}).get(role or "default") or {}).get("fallback")
    out = [m for m in ([declared] if isinstance(declared, str) else (declared or [])) if m != model_id]
    if declared_only:
        return out[:n]
    t = conn.execute("select interface, modes from models.tasks where task = %s", (task,)).fetchone()
    if not t:
        return out[:n]
    offers = sel.load_offers(conn, sel.latest_snapshots(conn))

    def unit(m: str) -> float | None:
        p = [o["norm_price"] for o in offers.get(m, []) if o["interface"] == t["interface"]
             and o.get("offer_kind") == "generation" and o.get("norm_price") is not None]
        return min(p) if p else None

    pref = conn.execute("select watch from models.preferences where task = %s and role = %s",
                        (task, role or "default")).fetchone()
    ref = unit(model_id)
    cands = []
    for c in composite(conn, task):
        m = c["model_id"]
        cfg = _models().get(m)
        if m == model_id or m in out or not cfg or unit(m) is None:
            continue
        if mode and not ((cfg.get("kie") or {}).get(mode) or (cfg.get("openrouter") and mode != "r2v")):
            continue
        cands.append(m)
    if pref and pref["watch"] == "dominance" and ref:   # ratio / budget role: stay in the same price class
        cheap = [m for m in cands if unit(m) <= ref * FALLBACK_COST_X]
        cands = cheap + sorted((m for m in cands if m not in cheap), key=unit)
    return (out + cands)[:n]


FALLBACK_COST_X = 2.0


# --- submit / poll --------------------------------------------------------------------------------------

def _kie_key() -> str:
    return instance.env_value("KIE_API_KEY") or ""


def run_kie(path: str, params: dict, kind: str) -> dict:
    h = {"Authorization": f"Bearer {_kie_key()}"}
    sub = _http("POST", f"{KIE}/api/v1/jobs/createTask", h, {"model": path, "input": coerce(path, params)})
    if sub.get("code") != 200:
        raise RuntimeError(f"kie submit: {sub.get('code')} {sub.get('msg')}")
    task_id = sub["data"]["taskId"]
    deadline = time.monotonic() + TIMEOUTS[kind]
    while time.monotonic() < deadline:
        time.sleep(8 if kind != "image" else 5)
        rec = _http("GET", f"{KIE}/api/v1/jobs/recordInfo?taskId={task_id}", h)["data"]
        if rec["state"] == "success":
            res = json.loads(rec.get("resultJson") or "{}")
            urls = res.get("resultUrls") or [x.get("audio_url") for x in (res.get("data") or []) if x.get("audio_url")]
            return {"task_id": task_id, "urls": urls,
                    "cost_usd": (rec.get("creditsConsumed") or 0) * KIE_USD_PER_CREDIT, "seconds": rec.get("costTime")}
        if rec["state"] in ("fail", "failed"):
            raise RuntimeError(f"kie task failed: {rec.get('failCode')} {rec.get('failMsg')}")
    raise TimeoutError(f"kie task {task_id} still running after {TIMEOUTS[kind]} s")


def run_openrouter(or_id: str, kind: str, params: dict) -> dict:
    h = {"Authorization": f'Bearer {instance.env_value("OPENROUTER_API_KEY")}'}
    if kind == "image":
        body = {"model": or_id, "prompt": params["prompt"], **{k: params[k] for k in ("aspect_ratio", "resolution")
                                                              if params.get(k)}}
        res = _http("POST", f"{OPENROUTER}/images", h, body, timeout=300)
        return {"b64": [d["b64_json"] for d in res.get("data", []) if d.get("b64_json")],
                "cost_usd": (res.get("usage") or {}).get("cost")}
    body = {"model": or_id, "prompt": params["prompt"],
            **{k: params[k] for k in ("duration", "resolution", "aspect_ratio") if params.get(k)}}
    if params.get("first_frame"):
        body["frame_images"] = [{"type": "image_url", "image_url": {"url": params["first_frame"]},
                                 "frame_type": "first_frame"}]
    if params.get("references"):
        body["input_references"] = [{"type": "image_url", "image_url": {"url": u}} for u in params["references"]]
    job = _http("POST", f"{OPENROUTER}/videos", h, body)
    deadline = time.monotonic() + TIMEOUTS["video"]
    while time.monotonic() < deadline:
        time.sleep(10)
        st = _http("GET", job["polling_url"], h)
        if st["status"] == "completed":
            return {"urls": st.get("unsigned_urls") or [], "cost_usd": (st.get("usage") or {}).get("cost"),
                    "auth_download": True}
        if st["status"] == "failed":
            raise RuntimeError(f"openrouter video failed: {st.get('error')}")
    raise TimeoutError("openrouter video still running")


def _download(urls: list[str], b64: list[str], folder: Path, stem: str, auth: dict | None) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, u in enumerate(urls):
        ext = Path(u.split("?")[0]).suffix or ".bin"
        req = Request(u, headers={"User-Agent": UA, **(auth or {})})
        with urlopen(req, timeout=300) as resp:  # noqa: S310 (provider result URLs)
            p = folder / f"{stem}-{i + 1}{ext}"
            p.write_bytes(resp.read(1024 * 1024 * 1024))
            paths.append(str(p))
    for i, data in enumerate(b64):
        p = folder / f"{stem}-{len(paths) + i + 1}.png"
        p.write_bytes(base64.b64decode(data))
        paths.append(str(p))
    return paths


# --- entry point ----------------------------------------------------------------------------------------

def generate(conn, request: str, task: str | None = None, role: str | None = None, image_urls: list[str] | None = None,
             aspect_ratio: str | None = None, duration: int | None = None, resolution: str | None = None,
             paid_fallback: bool = False, craft: bool = True, _depth: int = 0, model: str | None = None,
             _fallback: bool = True, voice: str | None = None,
             style: str | None = None, provider: str | None = None) -> dict:
    from walter_router.serve.routes import route as route_request
    from walter_router.serve import choose
    from walter_router.analysis import knowledge
    d = choose.pick(conn, task, role=role) if (task and role) else route_request(conn, request, task)
    task = d.get("task")
    t = conn.execute("select * from models.tasks where task = %s", (task,)).fetchone()
    if not t or t["interface"] not in ("image", "video", "music", "audio"):
        return {"error": f"not a media task: {task}", "decision": {k: d.get(k) for k in ("task", "model_id")}}
    if model:   # a fallback model (or a forced one) for the same task and role
        d = {**d, "model_id": model, "mode": None}
    model_id, cfg = d["model_id"], _models().get(d["model_id"])
    if not cfg:
        return {"error": f"no media executor configured for {model_id}", "decision": d.get("model_id")}
    kind = cfg["kind"]
    if d.get("mode") == "manual_ui" and not paid_fallback:
        prof = knowledge.profile(conn, model_id) or {}
        return {"mode": "manual_ui", "model_id": model_id, "role": d.get("role"), "provider": d.get("provider"),
                "how": prof.get("workflow"), "note": "Rôle prévu via une interface (crédits gratuits) ; "
                "relancer avec paid_fallback pour générer en payant via Kie."}
    mode = {"image": "i2i" if image_urls else "t2i", "video": "i2v" if image_urls else "t2v",
            "music": "music", "audio": "tts"}[kind]
    prof = knowledge.profile(conn, model_id) or {}
    prompt = craft_prompt(conn, request, cfg.get("prompt_style")) if craft else request
    steps = [{"step": "prompt", "prompt": prompt}]
    references = None
    if cfg.get("workflow") == "reference_first" and kind == "video" and not image_urls and _depth == 0:
        ref = generate(conn, f"Image de référence (planche visuelle, même personnage/décor/produit) pour : {request}",
                       task="text_to_image", role="default", aspect_ratio=aspect_ratio or "16:9", _depth=1)
        if ref.get("urls"):
            references, mode = ref["urls"][:1], "r2v"
            steps.append({"step": "reference", "model": ref.get("model_id"), "files": ref.get("files")})
    resolution = resolution or (cfg.get("defaults") or {}).get("resolution")
    kie_path = (cfg.get("kie") or {}).get(mode)
    or_id = openrouter_id(conn, model_id)
    order = choose_provider(conn, model_id, t["interface"], resolution, bool(kie_path), or_id)
    if provider:   # named by the owner: that provider only
        order = [p for p in order if p == provider]
        if not order:
            return {"error": f"{model_id} ne s'exécute pas chez {provider} ici", "model_id": model_id}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = OUT_DIR / f"{stamp}-{task}"
    errors = []
    for provider in order:
        t0 = time.monotonic()
        try:
            if provider == "kie":
                params = {"prompt": prompt, "aspect_ratio": aspect_ratio, "duration": duration, "resolution": resolution}
                if kind == "music":
                    params = {"custom_mode": True, "instrumental": not re.search(r"parole|chant|voix|lyrics|vocal",
                                                                                 request, re.I),
                              "model": "V6", "style": prompt[:200], "title": request[:60], "duration": duration}
                elif kind == "audio":   # voice / style: Hermes TTS passes its persona (Algenib, butler style)
                    turn = {"speaker_id": "Speaker 1", "text": request, **({"style": style} if style else {})}
                    params = {"speakers": [{"speaker_id": "Speaker 1", "voice_name": voice or "Fola"}],
                              "dialogue_turns": [turn]}
                if image_urls:
                    field = cfg["kie"].get("images") if kind == "image" else cfg["kie"].get("first_frame")
                    params[field] = image_urls if field.endswith("urls") else image_urls[0]
                if references:
                    params[cfg["kie"]["references"]] = references
                res = run_kie(kie_path, params, kind)
                files = _download(res["urls"], [], folder, f"{model_id}", None)
            else:
                res = run_openrouter(or_id, kind, {"prompt": prompt, "aspect_ratio": aspect_ratio,
                                                   "duration": duration, "resolution": resolution,
                                                   "first_frame": image_urls[0] if image_urls else None,
                                                   "references": references})
                auth = {"Authorization": f'Bearer {instance.env_value("OPENROUTER_API_KEY")}'} \
                    if res.get("auth_download") else None
                files = _download(res.get("urls") or [], res.get("b64") or [], folder, model_id, auth)
            execution.log(conn, {"task": task, "role": d.get("role"), "model_id": model_id, "provider": provider,
                                 "model": kie_path if provider == "kie" else or_id, "ok": True, "kind": kind,
                                 "seconds": round(time.monotonic() - t0, 1), "cost_usd": res.get("cost_usd")})
            conn.commit()
            return {"model_id": model_id, "role": d.get("role"), "task": task, "provider": provider, "mode": mode,
                    "prompt": prompt, "files": files, "urls": res.get("urls"), "cost_usd": res.get("cost_usd"),
                    "steps": steps, "errors": errors, "workflow_note": prof.get("cost_note")}
        except Exception as exc:  # noqa: BLE001 — next provider
            errors.append(f"{provider}: {type(exc).__name__}: {exc}"[:300])
            execution.log(conn, {"task": task, "role": d.get("role"), "model_id": model_id, "provider": provider,
                                 "model": kie_path if provider == "kie" else or_id, "ok": False, "kind": kind,
                                 "seconds": round(time.monotonic() - t0, 1)})
            conn.commit()
    if _fallback and _depth == 0:
        for fb in fallback_models(conn, task, d.get("role"), model_id, mode):
            r = generate(conn, request, task=task, role=d.get("role"), image_urls=image_urls, aspect_ratio=aspect_ratio,
                         duration=duration, resolution=None, paid_fallback=True, craft=craft, model=fb, _fallback=False,
                         voice=voice, style=style)
            if r.get("files"):
                return {**r, "fallback_from": model_id, "errors": errors + (r.get("errors") or [])}
            errors += r.get("errors") or [r.get("error", "")]
    return {"error": "every provider failed", "model_id": model_id, "errors": errors, "steps": steps}
