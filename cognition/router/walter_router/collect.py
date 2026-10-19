"""Collect leaderboards (from the aa-pareto skill cache) and live provider catalogues into models.snapshots,
then parse each new snapshot into models.benchmarks / models.offers."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import identity, media

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
CACHE = HERMES_HOME / "cache" / "aa-pareto"
HERMES_PY = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models?output_modalities=all"
KIE_URL = "https://api.kie.ai/client/v1/model-pricing/page"
MAX_BYTES = 64 * 1024 * 1024
MM_TASKS = {"provider_voice": "tts", "index": "speech_to_speech"}
# Kie publishes a few chat price rows with a wrong dimension label; each fix is checked against the
# published input price and the vendor's 1:5 input/output ratio before being added here.
KIE_DIMENSION_FIXES = {("claude-opus-5-5", "claude-opus-5"): "output"}
ARENA_URL = "https://arena.ai/leaderboard/"
BRIDGEBENCH_URL = "https://www.bridgebench.ai/leaderboard"
# AA Decision Index (v1.0, 2026-10-13): decision models (typed answers + probabilities) and LLM references on
# AA-Omniscience-Decision, HLE-MultiChoice, When2Call and WildGuardTest; accuracy, time and cost per 1M tasks.
AA_DECISION_URL = "https://artificialanalysis.ai/evaluations/artificial-analysis-decision-index"
FLARESOLVERR = os.environ.get("WALTER_FLARESOLVERR", "http://127.0.0.1:8191/v1")  # local, behind Cloudflare sites
# Internal postes stt / rerank / embeddings (2026-10-16, Monsieur: « rajouter le reranking, embedding et STT »).
# AA Speech-to-Text: AA-WER index (lower = better, English datasets — AA publishes no French result), speed factor
# (x real time) and price per 1000 audio minutes, per model x host, from the page's chart download tables.
AA_STT_URL = "https://artificialanalysis.ai/speech-to-text"
AA_STT_TABLES = ("STT AA-WER vs Price", "STT AA-WER vs Speed Factor", "STT Speed Factor vs Price")
# Agentset RAG leaderboards: pairwise ELO judged on retrieval tasks, average latency, nDCG@10, price per 1M tokens.
AGENTSET_URLS = {"rerank": "https://agentset.ai/rerankers", "embeddings": "https://agentset.ai/embeddings"}
# MTEB results repository: French retrieval = MIRACL hard negatives, subset fr (nDCG@10), for every embedding model
# OpenRouter serves (matched by our normalised id). GitHub API (60 calls/h without a token): one listing + one per model.
MTEB_API = "https://api.github.com/repos/embeddings-benchmark/results/contents/results"
MTEB_RAW = "https://raw.githubusercontent.com/embeddings-benchmark/results/main/results"
MTEB_FR = {"retrieval_fr": ("MIRACLRetrievalHardNegatives", "fr")}
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/models?output_modalities=embeddings"
# Arena.ai page -> board key stored in models.benchmarks.task (benchmark = 'arena')
ARENA_BOARDS = {"text": "text", "text/french": "text_french", "text/coding": "text_coding",
                "text/creative-writing": "text_creative", "code/webdev": "webdev",
                "code/image-to-webdev": "image_to_webdev", "vision": "vision", "document": "document",
                "search": "search", "agent": "agent", "text-to-image": "text_to_image",
                "image/image-edit/single-image": "image_edit",   # moved there on 2026-10-10 (was image-edit)
                "text-to-video": "text_to_video", "image-to-video": "image_to_video", "video-edit": "video_edit"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_json(url: str, payload: dict | None = None) -> Any:
    headers = {"User-Agent": "Walter-Router/1.0", "Accept": "application/json"}
    data = None
    if payload is not None:
        headers.update({"Content-Type": "application/json", "Origin": "https://kie.ai", "Referer": "https://kie.ai/pricing"})
        data = json.dumps(payload).encode()
    with urlopen(Request(url, data=data, headers=headers), timeout=60) as resp:  # noqa: S310 (fixed https URLs)
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"response too large: {url}")
    return json.loads(raw)


def _parse_time(value: str | None) -> datetime:
    if not value:
        return now()
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# --- sources -------------------------------------------------------------------------------------------

def source_aa() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "latest.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), "https://artificialanalysis.ai/"


def source_mm() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "multimodal_latest.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), "https://artificialanalysis.ai/"


def source_da() -> tuple[dict, datetime, str]:
    doc = json.loads((CACHE / "designarena.json").read_text())
    return doc, _parse_time(doc.get("generated_at")), doc.get("source_url") or "https://www.designarena.ai/"


def fetch_text(url: str) -> str:
    """A page, directly; through the local FlareSolverr when the site answers 403/503 (Cloudflare challenge —
    Arena since 2026-10-14)."""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Walter-Router/1.0)", "Accept": "text/html"})
    try:
        with urlopen(req, timeout=40) as resp:  # noqa: S310 (fixed https host)
            raw = resp.read(MAX_BYTES + 1)
        return raw.decode("utf-8", "replace")
    except HTTPError as exc:
        if exc.code not in (403, 503):
            raise
    body = json.dumps({"cmd": "request.get", "url": url, "maxTimeout": 90000}).encode()
    with urlopen(Request(FLARESOLVERR, data=body, headers={"Content-Type": "application/json"}), timeout=150) as resp:  # noqa: S310
        sol = json.loads(resp.read(MAX_BYTES))["solution"]
    if sol.get("status") != 200:
        raise ValueError(f"{url}: HTTP {sol.get('status')} through FlareSolverr")
    return sol["response"]


def _json_array(text: str, start: int) -> list:
    """The JSON array starting at text[start] == '[' (string-aware bracket matching)."""
    depth, in_str, esc = 0, False, False
    for k in range(start, len(text)):
        ch = text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:k + 1])
    raise ValueError("unterminated array")


def arena_board(page: str) -> dict | None:
    """Leaderboard rows embedded in an Arena.ai page (Next.js flight data): pairwise boards carry 'entries'
    (Elo rating + CI + votes), the agent board carries 'snapshot.rows' (average task score + CI)."""
    text = html.unescape(page).replace('\\"', '"').replace("\\\\", "\\")
    m = re.search(r'"id":"(leaderboard-sets/[^"]+)","entries":\[', text)
    if m:
        return {"leaderboard_id": m.group(1), "kind": "elo", "rows": _json_array(text, m.end() - 1)}
    i = text.find('"snapshot":{"lastUpdated"')
    if i >= 0:
        j = text.index('"rows":[', i) + len('"rows":')
        updated = re.search(r'"lastUpdated":"([^"]+)"', text[i:i + 80])
        return {"leaderboard_id": "agent", "kind": "agent", "updated": updated and updated.group(1),
                "rows": _json_array(text, j)}
    return None


def _json_object(text: str, start: int) -> str:
    """The JSON object starting at text[start] == '{' (string-aware brace matching)."""
    depth, in_str, esc = 0, False, False
    for k in range(start, len(text)):
        ch = text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:k + 1]
    raise ValueError("unterminated object")


def bridgebench_rows(page: str) -> list[dict]:
    """Model rows of the BridgeBench leaderboard page: {id, name, vendor, provisional, scores{overall, reasoning,
    frontend, backend, oneShot, security, trustworthiness, efficiency, speed, cost}, price, blended, context}."""
    text = html.unescape(page).replace('\\"', '"')
    rows: dict[str, dict] = {}
    for m in re.finditer(r'\{"id":"[^"]+","href":"/leaderboard/', text):
        try:
            obj = json.loads(_json_object(text, m.start()))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj.get("scores"), dict):
            obj.pop("mark", None)
            rows[obj["id"]] = obj
    return list(rows.values())


def source_bridgebench() -> tuple[dict, datetime, str]:
    """BridgeBench sits behind a Cloudflare challenge: fetched through the local FlareSolverr."""
    body = json.dumps({"cmd": "request.get", "url": BRIDGEBENCH_URL, "maxTimeout": 90000}).encode()
    req = Request(FLARESOLVERR, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=150) as resp:  # noqa: S310 (local service)
        sol = json.loads(resp.read(MAX_BYTES))["solution"]
    if sol.get("status") != 200:
        raise ValueError(f"bridgebench: HTTP {sol.get('status')}")
    rows = bridgebench_rows(sol["response"])
    if len(rows) < 10:
        raise ValueError(f"bridgebench: only {len(rows)} rows parsed")
    return {"rows": rows}, now(), BRIDGEBENCH_URL


def rsc_text(page: str) -> str:
    """Concatenated Next.js flight payload (self.__next_f.push([1, "..."])) of a server-rendered page."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def aa_decision_rows(page: str) -> list[dict]:
    text = rsc_text(page)
    i = text.find('{"contestants":')
    if i < 0:
        raise ValueError("aa_decision: no contestants in page")
    rows, _ = json.JSONDecoder().raw_decode(text[i + len('{"contestants":'):])
    return rows


def source_aa_decision() -> tuple[dict, datetime, str]:
    rows = aa_decision_rows(fetch_text(AA_DECISION_URL))
    if len([r for r in rows if r.get("kind") == "decisionModel"]) < 5:
        raise ValueError(f"aa_decision: only {len(rows)} rows parsed")
    return {"rows": rows}, now(), AA_DECISION_URL


def aa_stt_rows(page: str) -> list[dict]:
    """One row per model x host of AA's Speech-to-Text page: the chart download tables (WER vs price, WER vs speed,
    speed vs price) joined on (Model, Provider)."""
    text = rsc_text(page)
    merged: dict[tuple[str, str], dict] = {}
    for m in re.finditer(r'"downloadData":\{"data":\[', text):
        try:
            table = json.loads(_json_object(text, m.end() - len('{"data":[')))
        except (ValueError, json.JSONDecodeError):
            continue
        if table.get("fileName") not in AA_STT_TABLES:
            continue
        for r in table["data"]:
            row = merged.setdefault((r["Model"], r.get("Provider") or ""), {"model": r["Model"], "provider": r.get("Provider")})
            for src, dst in (("AA-WER Index", "wer"), ("Speed Factor", "speed_factor"), ("Price per 1k Min", "price_per_1k_min")):
                if r.get(src) is not None:
                    row[dst] = r[src]
    return list(merged.values())


def source_aa_stt() -> tuple[dict, datetime, str]:
    rows = aa_stt_rows(fetch_text(AA_STT_URL))
    if len([r for r in rows if r.get("wer") is not None]) < 20:
        raise ValueError(f"aa_stt: only {len(rows)} rows parsed")
    return {"rows": rows}, now(), AA_STT_URL


def agentset_board(page: str) -> dict:
    """Leaderboard entries embedded in an Agentset page (rank, name, ELO score, provider, licence, avgLatencyMs,
    avgNdcg10, costPer1MTokens[, dimensions]), its 'Last updated' date and the detail-page slug of each name."""
    text = rsc_text(page) or html.unescape(page)
    m = re.search(r'"entries":\[', text)
    if not m:
        raise ValueError("agentset: no entries in page")
    updated = re.search(r'Last updated: ","([^"]+)"', text)
    slugs = dict(re.findall(r'"name":"([^"]+)","url":"https://agentset\.ai/(?:rerankers|embeddings)/([^"]+)"', text))
    return {"entries": _json_array(text, m.end() - 1), "updated": updated and updated.group(1), "slugs": slugs}


def source_agentset() -> tuple[dict, datetime, str]:
    boards, errors = {}, {}
    for key, url in AGENTSET_URLS.items():
        try:
            board = agentset_board(fetch_text(url))
            if len(board["entries"]) < 5:
                raise ValueError(f"only {len(board['entries'])} entries")
            boards[key] = {"url": url, **board}
        except Exception as exc:  # noqa: BLE001 — one missing board leaves the other usable
            errors[key] = f"{type(exc).__name__}: {exc}"[:200]
    if not boards:
        raise ValueError(f"agentset: no board parsed: {errors}")
    return {"boards": boards, "errors": errors}, now(), "https://agentset.ai/leaderboard"


def _github_json(url: str) -> Any:
    headers = {"User-Agent": "Walter-Router/1.0", "Accept": "application/vnd.github+json"}
    token = _env_value("GITHUB_TOKEN")
    if token:   # optional: lifts the 60 calls/h anonymous limit (header only, never logged)
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=60) as resp:  # noqa: S310 (fixed https host)
        return json.loads(resp.read(MAX_BYTES))


def source_mteb() -> tuple[dict, datetime, str]:
    """MTEB French retrieval (MIRACL-HN fr, nDCG@10) of every embedding model OpenRouter serves that the MTEB results
    repository has evaluated; the latest score per revision folder is kept (best revision chosen at parse time)."""
    served = {identity.normalize("openrouter", m["id"])[0] for m in fetch_json(OPENROUTER_EMBEDDINGS_URL)["data"]
              if ":" not in m["id"]}
    dirs = [d["name"] for d in _github_json(MTEB_API) if d.get("type") == "dir"]
    if len(dirs) < 100:
        raise ValueError(f"mteb: only {len(dirs)} model folders listed")
    rows, errors = [], {}
    for d in dirs:
        if identity.normalize("mteb", d)[0] not in served:
            continue
        try:
            revisions = [r["name"] for r in _github_json(f"{MTEB_API}/{d}") if r.get("type") == "dir"]
        except Exception as exc:  # noqa: BLE001
            errors[d] = f"{type(exc).__name__}: {exc}"[:200]
            continue
        for rev in revisions:
            for board, (task_name, subset) in MTEB_FR.items():
                try:
                    res = fetch_json(f"{MTEB_RAW}/{d}/{rev}/{task_name}.json")
                except HTTPError as exc:
                    if exc.code != 404:
                        errors[f"{d}/{rev}"] = f"HTTP {exc.code}"
                    continue
                scores = [s["main_score"] for split in (res.get("scores") or {}).values() for s in split
                          if s.get("hf_subset") == subset and s.get("main_score") is not None]
                if scores:
                    rows.append({"model": d, "revision": rev, "board": board, "task_name": task_name,
                                 "subset": subset, "main_score": max(scores), "mteb_version": res.get("mteb_version"),
                                 "date": res.get("date")})
    if len({r["model"] for r in rows}) < 5:
        raise ValueError(f"mteb: only {len(rows)} French scores ({errors})")
    return {"rows": rows, "errors": errors}, now(), "https://github.com/embeddings-benchmark/results"


def source_arena() -> tuple[dict, datetime, str]:
    boards, errors = {}, {}
    for path, key in ARENA_BOARDS.items():
        try:
            board = arena_board(fetch_text(ARENA_URL + path))
            if board and board["rows"]:
                boards[key] = {"path": path, **board}
            else:
                errors[key] = "no leaderboard rows in page"
        except Exception as exc:  # noqa: BLE001 — one missing board leaves the others usable
            errors[key] = f"{type(exc).__name__}: {exc}"[:200]
        time.sleep(0.5)
    if len(boards) < len(ARENA_BOARDS) // 2:
        raise ValueError(f"arena: only {len(boards)} boards parsed: {errors}")
    return {"boards": boards, "errors": errors}, now(), ARENA_URL


def display_pricing(page: str) -> list | None:
    """The `displayPricing` array embedded in an OpenRouter model page (per-second / per-song / per-tier prices
    that the /models API reports as 0 for media models)."""
    text = html.unescape(page).replace('\\"', '"')
    i = text.find('"displayPricing":')
    if i < 0:
        return None
    j = text.index("[", i)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "[":
            depth += 1
        elif text[k] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[j:k + 1])
    return None


def source_openrouter() -> tuple[dict, datetime, str]:
    doc = fetch_json(OPENROUTER_URL)
    if not doc.get("data"):
        raise ValueError("openrouter: empty catalogue")
    for m in doc["data"]:
        if _or_interface(m) not in UNIT_PRICED_INTERFACES or ":" in m["id"] or m["id"].startswith(("openrouter/", "~")):
            continue
        try:
            m["_display_pricing"] = display_pricing(fetch_text(f"https://openrouter.ai/{m['id']}"))
        except Exception as exc:  # noqa: BLE001 — a missing page leaves that model unpriced, not the run failed
            m["_display_pricing_error"] = f"{type(exc).__name__}: {exc}"[:200]
        time.sleep(0.3)
    return doc, now(), OPENROUTER_URL


def source_kie() -> tuple[dict, datetime, str]:
    records, page = [], 1
    while True:
        body = fetch_json(KIE_URL, {"pageNum": page, "pageSize": 100, "modelDescription": "", "interfaceType": ""})
        data = body["data"]
        if body.get("code") != 200 or data["current"] != page or not 1 <= data["pages"] <= 100:
            raise ValueError("kie: invalid page")
        records.extend(data["records"])
        if page == data["pages"]:
            break
        page += 1
    if len(records) != data["total"]:
        raise ValueError("kie: incomplete catalogue")
    return {"data": records}, now(), KIE_URL


def source_codex() -> tuple[dict, datetime, str]:
    """Live Codex catalogue of Monsieur's ChatGPT account, read through Hermes (read-only; token never printed)."""
    code = ("import json; from hermes_cli.models import _codex_catalog; "
            "print(json.dumps(_codex_catalog('openai-codex', False)))")
    out = subprocess.run([str(HERMES_PY), "-c", code], cwd=str(HERMES_HOME / "hermes-agent"), capture_output=True,
                         text=True, timeout=120, env={**os.environ, "HERMES_HOME": str(HERMES_HOME)})
    ids = json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 and out.stdout.strip() else []
    if not ids:
        raise ValueError(f"codex: catalogue unavailable (exit {out.returncode})")
    return {"models": ids}, now(), "chatgpt.com/backend-api/codex (account catalogue)"


PROVIDERS_CONFIG = Path(__file__).resolve().parent.parent / "config" / "providers.json"
HERMES_ENV = HERMES_HOME / ".env"


def _env_value(name: str) -> str | None:
    """A key from Hermes' 0600 .env (or the process environment), read at run time (never logged / put in a URL)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in HERMES_ENV.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    except OSError:
        pass
    return os.environ.get(name)


def source_hermes_providers() -> tuple[dict, datetime, str]:
    """Live /models catalogue of OpenAI-compatible providers configured in Hermes (config/providers.json)."""
    out, errors = [], {}
    for p in json.loads(PROVIDERS_CONFIG.read_text())["providers"]:
        key = _env_value(p["key_env"])
        if not key:
            errors[p["provider"]] = f'{p["key_env"]} missing'
            continue
        req = Request(p["api"].rstrip("/") + "/models",
                      headers={"Authorization": f"Bearer {key}", "User-Agent": "Walter-Router/1.0",
                               "Accept": "application/json"})
        try:
            with urlopen(req, timeout=60) as resp:  # noqa: S310 (configured https endpoint)
                data = json.loads(resp.read(MAX_BYTES))["data"]
            out.append({**{k: p[k] for k in ("provider", "name", "api", "hermes_provider")}, "models": data})
        except Exception as exc:  # noqa: BLE001
            errors[p["provider"]] = f"{type(exc).__name__}: {exc}"[:200]
    if not out:
        raise ValueError(f"hermes_providers: no catalogue ({errors})")
    return {"providers": out, "errors": errors}, now(), str(PROVIDERS_CONFIG)


DECLARED = Path(__file__).resolve().parent.parent / "config" / "declared_offers.json"


def source_declared() -> tuple[dict, datetime, str]:
    doc = json.loads(DECLARED.read_text())
    return {"offers": doc["offers"]}, now(), str(DECLARED)


SOURCES = {"aa": source_aa, "aa_decision": source_aa_decision, "mm": source_mm, "da": source_da, "arena": source_arena, "bridgebench": source_bridgebench,
           "aa_stt": source_aa_stt, "agentset": source_agentset, "mteb": source_mteb,
           "openrouter": source_openrouter, "kie": source_kie, "codex": source_codex,
           "declared": source_declared, "hermes_providers": source_hermes_providers}


# --- parsing -------------------------------------------------------------------------------------------

def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _mm_unit_price(row: dict) -> tuple[float | None, str | None]:
    """AA list price normalised to the provider units we compare against (reference only, never 'callable')."""
    price, unit = _num(row.get("api_price_usd")), (row.get("api_price_unit") or "").strip()
    if price is None:
        return None, None
    if unit == "1k imgs":
        return price / 1000, "usd_per_image"
    if unit == "min":
        return price / 60, "usd_per_second"
    if unit == "1M chars":
        return price, "usd_per_1m_chars"
    return price, unit or None


def parse_benchmarks(kind: str, doc: dict) -> list[dict]:
    rows: list[dict] = []
    if kind == "aa":
        for r in doc["data"]:
            score = _num(r.get("intelligence_index"))
            if score is None:
                continue
            mid, variant = identity.normalize("aa", r["slug"], r.get("name"))
            rows.append(dict(benchmark="aa_intelligence", task="intelligence", external_key=r["slug"], model_id=mid,
                             variant=variant, display_name=r.get("name"), score=score, score_unit="AA Intelligence Index",
                             cost=_num(r.get("aa_cost_per_task_intelligence_usd")), cost_unit="usd_per_aa_task",
                             released=None, extra={}))
    elif kind == "mm":
        for module in doc["modules"].values():
            for task_key, task in module["tasks"].items():
                best: dict[str, dict] = {}
                for r in task.get("rows") or task.get("records") or []:
                    score = _num(r.get("quality_score"))
                    if score is None:
                        continue
                    if r["model"] in best and best[r["model"]]["score"] >= score:
                        continue
                    mid, variant = identity.normalize("mm", r["model"])
                    cost, unit = _mm_unit_price(r)
                    best[r["model"]] = dict(
                        benchmark="aa_mm", task=MM_TASKS.get(task_key, task_key), external_key=r["model"], model_id=mid,
                        variant=variant, display_name=r["model"], score=score, score_unit=r.get("quality_metric"),
                        cost=cost, cost_unit=unit, released=r.get("released"),
                        extra={"api_price_raw": r.get("api_price_raw"), "samples": r.get("samples"),
                               "provider": r.get("provider")},
                        meta={"open_weights": True if r.get("open_weights") is True else None, "license": None})
                rows.extend(best.values())
    elif kind == "da":
        for section, bench in (("categories", "da_models"), ("agent_categories", "da_agents")):
            for task_key, cat in (doc.get(section) or {}).items():
                cat_rows = cat.get("rows") if isinstance(cat, dict) else cat
                seen: set[str] = set()
                for r in cat_rows or []:
                    key = r.get("model") or r.get("modelId")
                    score = _num(r.get("elo"))
                    if not key or score is None or key in seen:
                        continue
                    seen.add(key)
                    mid, variant = identity.normalize("da", key)
                    rows.append(dict(benchmark=bench, task=task_key, external_key=key, model_id=mid, variant=variant,
                                     display_name=key, score=score, score_unit="Design Arena Elo", cost=None,
                                     cost_unit=None, released=None,
                                     extra={k: r.get(k) for k in ("win_rate", "battles", "avg_generation_time_ms")}))
    elif kind == "arena":
        for task_key, board in doc["boards"].items():
            seen: set[str] = set()
            for r in board["rows"]:
                key = r.get("modelDisplayName") or r.get("model")
                if not key or key in seen:
                    continue
                if board["kind"] == "agent":
                    score = _num((r.get("avgScore") or {}).get("value"))
                    ci = _num((r.get("avgScore") or {}).get("ci"))
                    score, ci = (score * 1000 if score is not None else None), (ci * 1000 if ci is not None else None)
                    extra = {"rank": r.get("rank"), "ci": [score - ci, score + ci] if score is not None and ci else None,
                             "sessions": r.get("sessions"), "organization": r.get("modelOrganization"),
                             "release_type": r.get("releaseType")}
                    unit = "Arena Agent score (x1000)"
                else:
                    score = _num(r.get("rating"))
                    extra = {"rank": r.get("rank"), "ci": [r.get("ratingLower"), r.get("ratingUpper")],
                             "votes": r.get("votes"), "organization": r.get("modelOrganization"),
                             "release_type": r.get("releaseType"), "price_per_second": r.get("pricePerSecond"),
                             "price_per_image": r.get("pricePerImage"), "license": r.get("license")}
                    unit = "Arena Elo"
                if score is None:
                    continue
                seen.add(key)
                mid, variant = identity.normalize("arena", key)
                lic = r.get("license")
                rows.append(dict(benchmark="arena", task=task_key, external_key=key, model_id=mid, variant=variant,
                                 display_name=key, score=score, score_unit=unit, cost=None, cost_unit=None,
                                 released=None, extra=extra,
                                 meta={"open_weights": None if not lic else lic.strip().lower() != "proprietary",
                                       "license": lic}))
    elif kind == "aa_decision":
        for r in doc["rows"]:
            score = _num(r.get("indexScore"))
            if score is None or not r.get("slug"):
                continue
            mid, variant = identity.normalize("aa_decision", r["slug"], r.get("name"))
            if r.get("kind") == "decisionModel":
                variant = ""   # 'GPT-6 Luna (Decisions)' is a product, not an effort tier
            cost = _num(r.get("costPerTaskUsd"))
            rows.append(dict(benchmark="aa_decision", task="decision", external_key=r["slug"], model_id=mid,
                             variant=variant, display_name=r.get("name"), score=score, score_unit="AA Decision Index",
                             cost=cost * 1e6 if cost is not None else None, cost_unit="usd_per_1m_tasks", released=None,
                             extra={"kind": r.get("kind"), "host": r.get("hostName"), "creator": r.get("creatorName"),
                                    "time_per_task_ms": r.get("timePerTaskMs"), "scores": r.get("scores") or {}}))
    elif kind == "aa_stt":
        # Stored score is always "higher = better" (alerts, nerf and podium code rely on it): WER -> 100 - WER %.
        for r in doc["rows"]:
            name = identity.stt_name(r["model"], r.get("provider"))
            mid, variant = identity.normalize("aa_stt", r["model"], r.get("provider"))
            price = _num(r.get("price_per_1k_min"))
            wer, speed = _num(r.get("wer")), _num(r.get("speed_factor"))
            extra = {"host": r.get("provider"), "wer_pct": round(100 * wer, 3) if wer is not None else None,
                     "speed_factor": speed, "price_per_1k_min": price, "language": "en"}
            common = dict(external_key=f'{r["model"]} | {r.get("provider") or ""}', model_id=mid, variant=variant,
                          display_name=name, cost=price / 1000 if price else None,   # 0 = no public price
                          cost_unit="usd_per_audio_minute", released=None, extra=extra)
            if wer is not None:
                rows.append(dict(benchmark="aa_stt", task="wer", score=round(100 * (1 - wer), 3),
                                 score_unit="AA-WER accuracy % (100 - WER)", **common))
            if speed:
                rows.append(dict(benchmark="aa_stt", task="speed", score=speed,
                                 score_unit="AA STT speed factor (x real time)", **common))
    elif kind == "agentset":
        for board, b in doc["boards"].items():
            for r in b["entries"]:
                score, lat = _num(r.get("score")), _num(r.get("avgLatencyMs"))
                if score is None:
                    continue
                mid, variant = identity.normalize("agentset", r["name"])
                win = re.search(r"Win Rate: ([\d.]+)%", r.get("description") or "")
                lic = r.get("license")
                extra = {"rank": r.get("rank"), "organization": r.get("provider"), "license": lic, "latency_ms": lat,
                         "ndcg10": r.get("avgNdcg10"), "dimensions": r.get("dimensions"),
                         "win_rate": float(win.group(1)) if win else None, "updated": b.get("updated"),
                         "slug": (b.get("slugs") or {}).get(r["name"])}
                common = dict(external_key=r["name"], model_id=mid, variant=variant, display_name=r["name"],
                              cost=_num(r.get("costPer1MTokens")) or None, cost_unit="usd_per_1m_tokens",
                              released=None, extra=extra,
                              meta={"open_weights": None if not lic else lic.strip().lower() != "proprietary",
                                    "license": lic})
                rows.append(dict(benchmark="agentset", task=board, score=score, score_unit="Agentset ELO", **common))
                if lat:   # latency as a "higher = better" speed: requests per second at the measured latency
                    rows.append(dict(benchmark="agentset", task=f"{board}_speed", score=round(1000 / lat, 3),
                                     score_unit="Agentset speed (1000 / latency ms)", **common))
    elif kind == "mteb":
        best: dict[tuple[str, str], dict] = {}
        for r in doc["rows"]:   # several revision folders of one model: its best published result
            k = (r["board"], r["model"])
            if k not in best or r["main_score"] > best[k]["main_score"]:
                best[k] = r
        for (board, folder), r in best.items():
            mid, variant = identity.normalize("mteb", folder)
            rows.append(dict(benchmark="mteb", task=board, external_key=folder, model_id=mid, variant=variant,
                             display_name=folder.split("__", 1)[-1], score=round(100 * r["main_score"], 2),
                             score_unit=f'MTEB nDCG@10 x100 ({r["task_name"]} {r["subset"]})', cost=None,
                             cost_unit=None, released=None,
                             extra={k: r.get(k) for k in ("revision", "task_name", "subset", "mteb_version", "date")}))
    elif kind == "bridgebench":
        axes = {"oneShot": "one_shot"}
        for r in doc["rows"]:
            mid, variant = identity.normalize("bridgebench", r["id"])
            for axis, score in (r.get("scores") or {}).items():
                score = _num(score)
                if score is None:
                    continue
                rows.append(dict(benchmark="bridgebench", task=axes.get(axis, axis), external_key=r["id"], model_id=mid,
                                 variant=variant, display_name=r.get("name"), score=score,
                                 score_unit="BridgeBench points /1000", cost=None, cost_unit=None, released=None,
                                 extra={"provisional": r.get("provisional"), "price": r.get("price"),
                                        "blended": r.get("blended"), "context": r.get("context")}))
    return rows


MEDIA_INTERFACES = ("image", "video", "audio", "music")
# Services priced per unit on their OpenRouter page (transcription per second / hour, rerank per search): the API's
# prompt "token" price of those models is that unit price, not a token price.
UNIT_PRICED_INTERFACES = MEDIA_INTERFACES + ("transcription", "rerank")
OR_BASE_UNITS = {"/M characters": "per character", "/M UTF-8 bytes": "per utf-8 byte", "/minute": "per second",
                 "/1K calls": "per call", "/M tokens": "per token"}
_OR_OUTPUTS = {"video": "video", "image": "image", "audio": "audio", "speech": "audio", "transcription": "transcription",
               "embeddings": "embedding", "rerank": "rerank"}


def _or_name(name: str | None) -> str | None:
    """'Black Forest Labs: FLUX.3 Image' -> 'FLUX.3 Image'; short names keep their vendor ('MiniMax H3', 'HeyGen Video 1')."""
    if not name:
        return None
    vendor, _, rest = name.partition(": ")
    return (rest if len(rest) >= 9 and " " in rest else f"{vendor} {rest}") if rest else vendor


def _or_interface(model: dict) -> str:
    out = model.get("architecture", {}).get("output_modalities") or ["text"]
    if "lyria" in model["id"]:
        return "music"
    for modality, interface in _OR_OUTPUTS.items():
        if modality in out:
            return interface
    return "chat" if "text" in out else (out[0] if out else "chat")


def _kie_interface(rec: dict) -> str:
    kind = rec.get("interfaceType") or "chat"
    desc = rec["modelDescription"].lower()
    if kind == "music" and any(k in desc for k in ("tts", "text to speech", "elevenlabs", "dialogue")):
        return "audio"
    return kind


OFFER_KINDS = ("openrouter", "kie", "codex", "declared", "hermes_providers")


def _media_fields(interface: str, label: str, unit_price: float | None, unit: str | None,
                  inputs: list[str] | None = None, tier_label: str = "") -> dict:
    """What the offer sells (media.classify) and its price in the interface's comparable unit."""
    c = media.classify(interface, label, inputs)
    price, norm_unit = media.norm_price(interface, unit_price, unit, label)
    return dict(offer_kind=c["kind"], modes=c["modes"], resolution=media.resolution(label, tier_label) or c["resolution"],
                audio=c["audio"], norm_price=price if c["kind"] == "generation" else None, norm_unit=norm_unit)


def parse_offers(kind: str, doc: dict) -> list[dict]:
    rows: list[dict] = []
    if kind == "openrouter":
        for m in doc["data"]:
            oid = m["id"]
            if ":" in oid or oid.startswith(("openrouter/", "~")):
                continue  # batch/free duplicates, meta-routers and moving "latest" pointers
            mid, _ = identity.normalize("openrouter", oid)
            pr = m.get("pricing") or {}
            pin, pout = _num(pr.get("prompt")), _num(pr.get("completion"))
            interface = _or_interface(m)
            created = datetime.fromtimestamp(m["created"], timezone.utc) if m.get("created") else None
            # media models report 0/0 token prices in the API: that is not a price; neither is the prompt "token"
            # price of a service whose page prices it per unit (whisper per second, MAI per hour, rerank per search)
            is_media = interface in MEDIA_INTERFACES or (interface in UNIT_PRICED_INTERFACES and (
                not pin or any(e.get("kind") == "unit" for e in m.get("_display_pricing") or [])))
            inputs = m.get("architecture", {}).get("input_modalities") or []
            rows.append(dict(provider="openrouter", offer_key=oid, model_id=mid, interface=interface, access="paid",
                             price_in_1m=None if is_media or pin is None or pin < 0 else pin * 1e6,
                             price_out_1m=None if is_media or pout is None or pout < 0 else pout * 1e6,
                             unit_price=None, unit=None, provider_created=created, pricing=pr,
                             display_name=_or_name(m.get("name")),
                             meta={"open_weights": True if m.get("hugging_face_id") else None, "license": None,
                                   "hf": m.get("hugging_face_id") or None,
                                   "context_length": m.get("context_length")},
                             # embeddings compare on their input price per 1M tokens
                             **_media_fields(interface, "", pin * 1e6 if interface == "embedding" and pin else None,
                                             "per 1m tokens" if interface == "embedding" else None, inputs)))
            if interface == "decisions":   # what a decision model can read besides text (image, audio, video)
                rows[-1]["modes"] = sorted(x for x in inputs if x != "text")
            if interface == "chat" and "audio" in inputs:
                # a chat model that hears audio also transcribes (Hermes stt: Gemini Flash-Lite via chat/completions
                # input_audio): one offer on the transcription interface, priced per 1M audio input tokens
                aud = _num(pr.get("audio")) or pin
                rows.append(dict(provider="openrouter", offer_key=f"{oid} | audio input", model_id=mid,
                                 interface="transcription", access="paid",
                                 price_in_1m=aud * 1e6 if aud and aud > 0 else None,
                                 price_out_1m=pout * 1e6 if pout and pout > 0 else None, unit_price=None, unit=None,
                                 provider_created=created, pricing={"audio": pr.get("audio"), "prompt": pr.get("prompt"),
                                                                    "completion": pr.get("completion"), "via": "chat"},
                                 **_media_fields("transcription", "audio input", None, None, inputs)))
            for entry in m.get("_display_pricing") or []:
                if entry.get("kind") != "unit":
                    continue  # token-priced media (e.g. image output per M tokens) has no per-unit equivalent
                label_unit = (entry.get("unitLabel") or "").strip()
                unit = "per " + label_unit.lstrip("/").strip()
                if (_num(entry.get("displayMultiplier")) or 1) != 1:
                    # the price is per base unit; the page multiplies it for display ("/M characters" x 1e6)
                    unit = OR_BASE_UNITS.get(label_unit, f'{unit} / {entry["displayMultiplier"]}')
                for tier in entry.get("tiers") or [{"sku_label": "", "price": entry.get("price")}]:
                    price = _num(tier.get("price"))
                    if price is None:
                        continue
                    key = " | ".join(x for x in (oid, entry.get("sku_label"), tier.get("sku_label")) if x)
                    label = " | ".join(x for x in (entry.get("sku_label"), tier.get("sku_label")) if x)
                    rows.append(dict(provider="openrouter", offer_key=key, model_id=mid, interface=interface, access="paid",
                                     price_in_1m=None, price_out_1m=None, unit_price=price, unit=unit,
                                     provider_created=created, pricing={"display": entry, "tier": tier},
                                     **_media_fields(interface, label, price, unit, inputs, tier.get("sku_label") or "")))
    elif kind == "kie":
        chat: dict[str, dict] = {}
        for rec in doc["data"]:
            parts = [p.strip() for p in rec["modelDescription"].split(",")]
            name, interface = parts[0], _kie_interface(rec)
            mid, _ = identity.normalize("kie", name)
            price = None if "," in str(rec.get("usdPrice")) else _num(rec.get("usdPrice"))
            if interface == "chat":
                dim = parts[-1].lower()
                dim = KIE_DIMENSION_FIXES.get((name.lower(), dim), dim)
                entry = chat.setdefault(name, dict(provider="kie", offer_key=name, model_id=mid, interface="chat",
                                                   access="paid", price_in_1m=None, price_out_1m=None, unit_price=None,
                                                   unit="per million tokens", provider_created=None, pricing={}))
                entry["pricing"][parts[-1]] = rec.get("usdPrice")
                if dim == "input":
                    entry["price_in_1m"] = price
                elif dim == "output":
                    entry["price_out_1m"] = price
                continue
            rows.append(dict(provider="kie", offer_key=rec["modelDescription"], model_id=mid, interface=interface,
                             access="paid", price_in_1m=None, price_out_1m=None, unit_price=price,
                             unit=rec.get("creditUnit"), provider_created=None, pricing=rec,
                             **_media_fields(interface, ", ".join(parts[1:]), price, rec.get("creditUnit"))))
        rows.extend(chat.values())
    elif kind == "declared":
        for d in doc["offers"]:
            mid, _ = identity.normalize("declared", d["model"])
            rows.append(dict(provider=d["provider"], offer_key=d["offer_key"], model_id=mid, interface=d["interface"],
                             access=d["access"], price_in_1m=None, price_out_1m=None, unit_price=None, unit=None,
                             provider_created=None, pricing={"declared": d.get("declared"), "note": d.get("note")},
                             offer_kind="generation", modes=d.get("modes") or [], resolution=None, audio=None,
                             norm_price=None, norm_unit=None))
    elif kind == "hermes_providers":
        for p in doc["providers"]:
            for m in p["models"]:
                outs = [x.get("type") for x in m.get("output_modalities") or [] if isinstance(x, dict)] or ["text"]
                interface = next((i for i in ("video", "image", "audio") if i in outs), "chat")
                prices = {pr.get("type"): _num(pr.get("cost_usd")) for side in ("input_modalities", "output_modalities")
                          for x in m.get(side) or [] if isinstance(x, dict) for pr in x.get("pricing") or []}
                mid, _ = identity.normalize("hermes_providers", m["id"])
                pin, pout = prices.get("prompt"), prices.get("completion")
                rows.append(dict(provider=p["provider"], offer_key=m["id"], model_id=mid, interface=interface,
                                 access="free" if m.get("is_free") else "paid",
                                 price_in_1m=pin * 1e6 if pin is not None else None,
                                 price_out_1m=pout * 1e6 if pout is not None else None, unit_price=None, unit=None,
                                 provider_created=datetime.fromtimestamp(m["created"], timezone.utc) if m.get("created") else None,
                                 pricing={"prices": prices, "quantization": m.get("quantization"),
                                          "hermes_provider": p["hermes_provider"]},
                                 # the base id names the model; a service tier (".../flex") or a raw id is no name
                                 display_name=None if m["id"].count("/") > 1 or "/" in (m.get("name") or "/")
                                 else m["name"].split(": ", 1)[-1],
                                 meta={"open_weights": True if m.get("hugging_face_id") else None,
                                       "license": None, "hf": m.get("hugging_face_id")}))
    elif kind == "codex":
        for oid in doc["models"]:
            mid, _ = identity.normalize("codex", oid)
            rows.append(dict(provider="codex", offer_key=oid, model_id=mid, interface="chat", access="subscription",
                             price_in_1m=None, price_out_1m=None, unit_price=None, unit=None, provider_created=None,
                             pricing={"subscription": "ChatGPT Plus (user-declared)"}))
    return rows


# --- storage -------------------------------------------------------------------------------------------

NAME_PRIORITY = {"openrouter": 1, "hermes_providers": 2, "aa": 3, "mm": 4, "bridgebench": 5, "arena": 6, "kie": 7, "da": 8,
                 "aa_stt": 9, "agentset": 10, "mteb": 11}


def _display_name(namespace: str, name: str | None) -> str | None:
    if not name or namespace not in NAME_PRIORITY:
        return None
    if namespace in ("aa", "mm", "arena", "aa_stt"):
        name = re.sub(r"\s*\([^)]*\)", "", name).strip()  # effort tier / 'based on' notes are variants, not names
    return name if namespace != "kie" else name.split(",")[0].strip()


def _apply_meta(conn, namespace: str, model_id: str, meta: dict | None) -> None:
    """Open weights / licence: 'open' from any source wins (Arena licence, AA open_weights, a Hugging Face id);
    'proprietary' only fills an unknown. The Arena licence text is preferred."""
    if meta and meta.get("context_length"):
        conn.execute("""update models.canonical set context_length = greatest(coalesce(context_length, 0), %s)
                        where model_id = %s""", (int(meta["context_length"]), model_id))
    if not meta or meta.get("open_weights") is None:
        return
    conn.execute("""update models.canonical set
                      open_weights = case when %(ow)s then true else coalesce(open_weights, false) end,
                      license = case when %(lic)s::text is not null and (license is null or %(src)s = 'arena')
                                     then %(lic)s else license end,
                      license_source = case when %(lic)s::text is not null and (license is null or %(src)s = 'arena')
                                            then %(src)s else coalesce(license_source, %(src)s) end
                    where model_id = %(id)s""",
                 {"ow": meta["open_weights"], "lic": meta.get("license") or (f'hf:{meta["hf"]}' if meta.get("hf") else None),
                  "src": namespace, "id": model_id})


def _ensure_identity(conn, namespace: str, key: str, model_id: str, vendor: str | None = None,
                     name: str | None = None) -> None:
    content_policy, base = identity.policy(model_id)
    conn.execute("""insert into models.canonical (model_id, vendor, content_policy, base_model_id) values (%s, %s, %s, %s)
                    on conflict (model_id) do update set content_policy = excluded.content_policy,
                      base_model_id = excluded.base_model_id
                    where models.canonical.content_policy is distinct from excluded.content_policy
                       or models.canonical.base_model_id is distinct from excluded.base_model_id""",
                 (model_id, vendor, content_policy, base))
    name = _display_name(namespace, name)
    if name:  # the most readable source names the model (OpenRouter > AA > AA multimodal > Arena > Kie > Design Arena)
        conn.execute("""update models.canonical set display_name = %s, display_source = %s where model_id = %s
                        and (display_source is null or display_source = %s
                             or coalesce((%s::jsonb ->> display_source)::int, 99) > %s)""",
                     (name, namespace, model_id, namespace, json.dumps(NAME_PRIORITY), NAME_PRIORITY[namespace]))
    origin = "manual" if key in identity.MANUAL.get(namespace, {}) else "auto"
    conn.execute("""insert into models.aliases (namespace, external_key, model_id, origin) values (%s, %s, %s, %s)
                    on conflict (namespace, external_key) do update set model_id = excluded.model_id, origin = excluded.origin
                    where models.aliases.origin = 'auto' or excluded.origin = 'manual'""",
                 (namespace, key, model_id, origin))


def _insert_rows(conn, sid: int, kind: str, doc: dict) -> int:
    """(Re)derive benchmarks/offers of one snapshot from its raw document with the current identity rules."""
    conn.execute("delete from models.benchmarks where snapshot_id = %s", (sid,))
    conn.execute("delete from models.offers where snapshot_id = %s", (sid,))
    rows = parse_offers(kind, doc) if kind in OFFER_KINDS else parse_benchmarks(kind, doc)
    for r in rows:
        key = r.get("external_key") or r["offer_key"]
        _ensure_identity(conn, kind, key, r["model_id"],
                         name=r.get("display_name") or (key if kind == "kie" else None))
        _apply_meta(conn, kind, r["model_id"], r.get("meta"))
        if "benchmark" in r:
            conn.execute("""insert into models.benchmarks (snapshot_id, benchmark, task, external_key, model_id, variant,
                            display_name, score, score_unit, cost, cost_unit, released, extra)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) on conflict do nothing""",
                         (sid, r["benchmark"], r["task"], r["external_key"], r["model_id"], r["variant"], r["display_name"],
                          r["score"], r["score_unit"], r["cost"], r["cost_unit"], r["released"], json.dumps(r["extra"])))
        else:
            conn.execute("""insert into models.offers (snapshot_id, provider, offer_key, model_id, interface, access,
                            price_in_1m, price_out_1m, unit_price, unit, provider_created, pricing,
                            offer_kind, modes, resolution, audio, norm_price, norm_unit)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s) on conflict do nothing""",
                         (sid, r["provider"], r["offer_key"], r["model_id"], r["interface"], r["access"], r["price_in_1m"],
                          r["price_out_1m"], r["unit_price"], r["unit"], r["provider_created"], json.dumps(r["pricing"]),
                          r.get("offer_kind", "generation"), r.get("modes") or [], r.get("resolution"), r.get("audio"),
                          r.get("norm_price"), r.get("norm_unit")))
    conn.execute("update models.snapshots set row_count = %s where snapshot_id = %s", (len(rows), sid))
    return len(rows)


def store(conn, kind: str, doc: dict, fetched_at: datetime, url: str) -> tuple[int, bool]:
    """Insert the snapshot (deduplicated by content) and (re)derive its rows. Returns (snapshot_id, is_new).

    An unchanged document is re-derived anyway, so identity rule changes (aliases.json) apply immediately.
    """
    blob = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(blob.encode()).hexdigest()
    found = conn.execute("select snapshot_id from models.snapshots where kind = %s and sha256 = %s", (kind, sha)).fetchone()
    if found:
        sid, new = found["snapshot_id"], False
        conn.execute("update models.snapshots set fetched_at = greatest(fetched_at, %s) where snapshot_id = %s",
                     (fetched_at, sid))
    else:
        sid, new = conn.execute("""insert into models.snapshots (kind, fetched_at, source_url, sha256, row_count, raw)
                                   values (%s, %s, %s, %s, 0, %s::jsonb) returning snapshot_id""",
                                (kind, fetched_at, url, sha, blob)).fetchone()["snapshot_id"], True
    _insert_rows(conn, sid, kind, doc)
    return sid, new


def collect_all(conn) -> dict[str, Any]:
    """Collect every source; a failing source is reported and the last good snapshot stays in use."""
    report: dict[str, Any] = {}
    for kind, fn in SOURCES.items():
        try:
            doc, fetched_at, url = fn()
            with conn.transaction():
                sid, new = store(conn, kind, doc, fetched_at, url)
            report[kind] = {"snapshot_id": sid, "new": new}
        except Exception as exc:  # noqa: BLE001 — one source must not stop the others
            report[kind] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return report


def prune(conn, keep_days: int = 30) -> int:
    """Delete snapshots older than keep_days, always keeping the latest one of each kind."""
    cur = conn.execute("""delete from models.snapshots s where fetched_at < now() - make_interval(days => %s)
                          and snapshot_id <> (select max(snapshot_id) from models.snapshots t where t.kind = s.kind)""",
                       (keep_days,))
    return cur.rowcount
