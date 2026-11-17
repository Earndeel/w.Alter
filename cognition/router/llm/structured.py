"""Structured model calls of walter-llm (SOCLE A6, 2026-11-11): typed decisions and rerank.

    POST /v1/decisions {state, questions?, occasion?, ask?, layers?, facts?, focus?, options?, now?, media?, need?,
                        samples?,
                        sampling?, straggler_s?, model?, models?, paid_floor_usd?, timeout?}
        → {answers, usage, model, provider, route, samples?, parts?, unavailable?, signals?, trace?, calls, attempts}
        samples > 1, sampling "mean" (default): parallel calls of the same model, averaged; once a majority has
        answered the late ones get `straggler_s` (default 0.4 s, null = wait for all) and are then dropped.
        sampling "first": the same calls hedged, the first answer is kept (the need's policy may set either).
        occasion: the questions are composed from the signals the modules declare (decision.compose); `focus` =
        the state key holding the event itself (e.g. new_message), the only text the cues read. `ask`: the signal
        ids of a complementary decision (only those are asked; one the occasion does not declare → 400);
        `layers`: ["observation"] and/or ["inference"] (readings asked apart from the judgements, in parallel).
    POST /v1/rerank    {query, documents, top_n?, model?, paid_floor_usd?, timeout?}
        → {results: [{index, relevance_score}], model, provider, route, usage, cost_usd, cost_status, attempts}

The Router decides (decision chain = `walter-router decision-chain`, rerank = the `rerank` poste); this module only
executes, in order, and stops at the first model that answers. A model named by the caller must be one the Router
offers for that task (else 400): it narrows the chain, never adds to it. When everything fails the caller gets a
structured list of attempts (provider/model + short reason: HTTP status, exception type or missing grant — never a
secret, a payload or a path).

Provider adapters (the only ones in Walter for these interfaces):
  OpenRouter Decisions API  "vendor/model[:free]"      key OPENROUTER_API_KEY
  Cloudflare Workers AI     "cloudflare/clef" | "clef"  keys CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_AI_TOKEN
  Nace systemone            "nace/drex-max-v1.1"        key NACE_API_KEY (same contract as OpenRouter Decisions)
  OpenRouter rerank        "vendor/model"             key OPENROUTER_API_KEY

`merge_answers` here is THE implementation of the samples mean (moved from walter_memory.llm, same semantics).
No import of the gateway: its dependencies (key reader, http client, logger) are passed in, so tests run offline.
"""
from __future__ import annotations

import asyncio
import json
import time

OPENROUTER_DECISIONS = "https://openrouter.ai/api/alpha/decisions"
OPENROUTER_EXTRACTIONS = "https://openrouter.ai/api/alpha/extractions"   # values, estimates, passages (d1.2, 17/11)
OPENROUTER_RERANK = "https://openrouter.ai/api/v1/rerank"
OPENROUTER_CREDITS = "https://openrouter.ai/api/v1/credits"
CF_RUN = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}"
CF_PRICE = {"clef": 0.24, "clef-flash": 0.09}   # USD per M input tokens (Workers AI catalogue, 2026-10-03)
NACE_SYSTEMONE = "https://console.nace.ai/v1/systemone"
NACE_PRICE = {"drex-max-v1.1": 0.03}  # USD per M input tokens, output not billed (Nace docs, launch price, 2026-11-13)
# Liquid AI's own System One API (d1.2 family, 2026-11): same contract as Nace's. Offers are named `liquidai/<id>` so
# they never collide with OpenRouter's `liquid/d1…` resale of the older ones. Key LIQUID_API_KEY (grant card).
LIQUID_SYSTEMONE = "https://api.liquid.ai/decisions/v1/systemone"
LIQUID_PRICE = {"d1.2": 0.02, "d1.2-ultra": 0.042}  # USD per M input tokens, output not billed (Liquid docs, 2026-11)
MAX_SAMPLES = 5
MAX_DOCUMENTS = 1000
DEFAULT_TIMEOUT = 30.0
STRAGGLER_S = 0.4          # samples > 1: once a majority has answered, the late ones get this long (body `straggler_s`)


class MissingGrant(RuntimeError):
    """A provider key this gateway is not granted (the message names the variable and the grant, never a value)."""


def merge_answers(samples: list[dict]) -> dict:
    """The mean of several answers to the same questions. noul: mean probability. choice: mean probability per option,
    the choice = the highest mean, its confidence = the sum of the confidences of the samples that chose it divided
    by the number of samples (a sample that chose otherwise counts 0), `agreement` = the share that chose it."""
    out: dict = {}
    for k, first in samples[0].items():
        got = [s[k] for s in samples if isinstance(s.get(k), dict)]
        if first.get("type") == "noul":
            out[k] = {**first, "noul": sum(g.get("noul") or 0 for g in got) / len(got)}
            continue
        if isinstance(first.get("choices"), list):           # several options: each option its own mean
            opts = list(dict.fromkeys(o for g in got for o in (g.get("probabilities") or {})))
            p = {o: sum((g.get("probabilities") or {}).get(o) or 0 for g in got) / len(got) for o in opts}
            out[k] = {**first, "choices": [o for o in opts if p[o] >= 0.5], "probabilities": p}
            continue
        if isinstance(first.get("interval"), list):          # an estimate: median of the medians, mean interval
            nums = sorted(g["number"] for g in got if isinstance(g.get("number"), (int, float)))
            lows = [g["interval"][0] for g in got if isinstance((g.get("interval") or [None])[0], (int, float))]
            highs = [g["interval"][1] for g in got if isinstance((g.get("interval") or [None, None])[1], (int, float))]
            out[k] = {**first, "number": nums[len(nums) // 2] if nums else None,
                      "interval": [sum(lows) / len(lows) if lows else None, sum(highs) / len(highs) if highs else None]}
            continue
        kind = first.get("type")
        if kind in ("text", "number", "date"):               # a value read: the majority value, its share, mean found
            value = lambda g: json.dumps(g.get(kind), sort_keys=True, default=str)  # noqa: E731
            counts: dict = {}
            for g in got:
                counts[value(g)] = counts.get(value(g), 0) + 1
            top = max(counts, key=lambda v: counts[v])          # ties: the first sample's value
            pick = next(g for g in got if value(g) == top)
            founds = [g["found"] for g in got if isinstance(g.get("found"), (int, float))]
            out[k] = {**pick, "found": sum(founds) / len(founds) if founds else pick.get("found"),
                      "agreement": counts[top] / len(got)}
            continue
        if kind in ("spans", "box", "boxes"):                # passages and boxes are not averaged: the first sample's
            out[k] = first
            continue
        options = list(dict.fromkeys(o for g in got for o in (g.get("probabilities") or {})))
        if not options:
            out[k] = first
            continue
        p = {o: sum((g.get("probabilities") or {}).get(o, 0) for g in got) / len(got) for o in options}
        choice = max(options, key=lambda o: p[o])           # ties: the first sample's order, deterministic
        agree = [g for g in got if g.get("choice") == choice]
        out[k] = {**first, "choice": choice, "probabilities": p,
                  "confidence": sum(g.get("confidence") or 0 for g in agree) / len(got),
                  "agreement": len(agree) / len(got)}
    return out


UNMERGED = frozenset({"spans", "box", "boxes"})


def provider_of(model: str) -> str:
    if model.startswith("nace/"):
        return "nace"
    if model.startswith("liquidai/"):
        return "liquid"
    return "cloudflare" if model.startswith("cloudflare/") or "/" not in model else "openrouter"


def is_free(model: str) -> bool:
    return model.endswith(":free") or provider_of(model) == "cloudflare"


def reason(exc: BaseException) -> str:
    """A short, safe reason for one failed attempt."""
    if isinstance(exc, MissingGrant):
        return str(exc)[:200]
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        code = getattr(exc, "code", None)
        return f"HTTP {status}" + (f" {code}" if code else "")
    return type(exc).__name__


class ProviderError(RuntimeError):
    def __init__(self, status: int, code=None):
        super().__init__(f"HTTP {status}")
        self.status, self.code = status, (str(code)[:40] if code not in (None, "") else None)


def _error_code(data) -> str | None:
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return err.get("code") or err.get("type")
        errs = data.get("errors")
        if isinstance(errs, list) and errs and isinstance(errs[0], dict):
            return errs[0].get("code")
    return None


def _json(resp):
    try:
        return resp.json()
    except ValueError:
        return None


def _float(value) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


async def decide_once(client, key, model: str, state: dict, questions: dict, timeout: float, media=None) -> dict:
    """One decision on one model → {answers, usage, model, cost_usd, cost_status, input_tokens}. Walter Decision's
    plan splits the questions for this model's routes (decision call, Extractions call, several options as nouls);
    the parts go out in parallel and come back as one answer in the canonical shape."""
    import decision as wd
    provider = provider_of(model)
    p = wd.plan(provider, model, questions, media or [])
    if not p["extract"] and not p["emulated"]:
        res = await _decide_route(client, key, model, state, p["native"], timeout, media)
        return {**res, "answers": wd.finish(questions, res["answers"])}
    text = wd.render_state(state)
    parts = []
    if p["native"]:
        parts.append(_decide_route(client, key, model, state, p["native"], timeout, media))
    if p["extract"]:
        parts.append(_extract_once(client, key, model, text, wd.extraction_fields(p["extract"]), timeout))
    got = await asyncio.gather(*parts, return_exceptions=True)
    for r in got:
        if isinstance(r, BaseException):
            raise r
    nat = got[0] if p["native"] else None
    ext = got[-1] if p["extract"] else None
    answers = wd.finish(questions, wd.assemble(questions, p, (nat or {}).get("answers") or {},
                                               (ext or {}).get("answers") or {}, text))
    costs = [r["cost_usd"] for r in got]
    status = "unknown" if any(c is None for c in costs) else \
        ("reported" if all(r["cost_status"] == "reported" for r in got) else "estimated")
    tokens = sum(r.get("input_tokens") or 0 for r in got)
    return {"answers": answers, "usage": {"input_tokens": tokens, "parts": [r["usage"] for r in got]},
            "model": (nat or ext)["model"], "cost_usd": None if status == "unknown" else sum(costs),
            "cost_status": status, "input_tokens": tokens,
            "parts": (["decisions"] if nat else []) + (["extractions"] if ext else [])}


async def _extract_once(client, key, model: str, text: str, fields: dict, timeout: float) -> dict:
    """OpenRouter's Extractions route (text state, typed fields)."""
    r = await client.post(OPENROUTER_EXTRACTIONS, headers={"Authorization": f"Bearer {key('OPENROUTER_API_KEY')}"},
                          json={"model": model, "state": text, "fields": fields}, timeout=timeout)
    data = _json(r)
    if r.status_code >= 400 or not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise ProviderError(r.status_code, _error_code(data))
    usage = data.get("usage") or {}
    cost = _float(usage.get("cost"))
    return {"answers": data["answers"], "usage": usage, "model": data.get("model") or model, "cost_usd": cost,
            "cost_status": "reported" if cost is not None else "unknown",
            "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens")}


def _liquid_media(media) -> dict:
    """Images and audio for Liquid's own API (measured 17/11, against its docs): images go in `images` (data URLs);
    audio goes in the top-level `audio` field as data URLs (WAV, MP3, FLAC, OGG). Its documented `media` field is
    silently IGNORED by the live API (the answer is then about no audio at all), so it is never used."""
    def url(m, mime):
        return m["data"] if m["data"].startswith("data:") else f"data:{mime};base64,{m['data']}"
    out = {}
    imgs = [url(m, "image/png") for m in media or [] if m["type"] == "image"]
    clips = [url(m, "audio/wav") for m in media or [] if m["type"] == "audio"]
    if imgs:
        out["images"] = imgs
    if clips:
        out["audio"] = clips
    return out


async def _decide_route(client, key, model: str, state: dict, questions: dict, timeout: float, media=None) -> dict:
    """One decision call on the model's own decision route."""
    if provider_of(model) == "cloudflare":
        short = model.split("/", 1)[-1]
        account, token = key("CLOUDFLARE_ACCOUNT_ID"), key("CLOUDFLARE_AI_TOKEN")
        r = await client.post(CF_RUN.format(account=account, model=short), headers={"Authorization": f"Bearer {token}"},
                              json={"model": short, "state": state, "questions": questions}, timeout=timeout)
        data = _json(r)
        if r.status_code >= 400 or not isinstance(data, dict) or not data.get("success") \
                or not isinstance((data.get("result") or {}).get("answers"), dict):
            raise ProviderError(r.status_code, _error_code(data))
        res = data["result"]
        tok = (res.get("usage") or {}).get("input_tokens") or 0
        return {"answers": res["answers"], "usage": res.get("usage") or {}, "model": model,
                "cost_usd": tok * CF_PRICE.get(short, 0.24) / 1e6, "cost_status": "estimated", "input_tokens": tok}
    if provider_of(model) in ("nace", "liquid"):        # the two System One APIs: one contract, own host and key
        short = model.split("/", 1)[1]
        nace = provider_of(model) == "nace"
        url, var, prices = (NACE_SYSTEMONE, "NACE_API_KEY", NACE_PRICE) if nace else \
            (LIQUID_SYSTEMONE, "LIQUID_API_KEY", LIQUID_PRICE)
        r = await client.post(url, headers={"Authorization": f"Bearer {key(var)}"},
                              json={"model": short, "state": state, "questions": questions,
                                    **(_liquid_media(media) if not nace else {})}, timeout=timeout)
        data = _json(r)
        if r.status_code >= 400 or not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise ProviderError(r.status_code, _error_code(data))
        usage = data.get("usage") or {}
        tok = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        price = prices.get(short)
        reported = _float(usage.get("cost"))          # Liquid reports the cost of the call (USD) beside the tokens
        if reported is not None:
            return {"answers": data["answers"], "usage": usage, "model": model, "cost_usd": reported,
                    "cost_status": "reported", "input_tokens": tok}
        return {"answers": data["answers"], "usage": usage, "model": model,
                "cost_usd": tok * price / 1e6 if price is not None else None,
                "cost_status": "estimated" if price is not None else "unknown", "input_tokens": tok}
    if media:      # images beside the state: a top-level state array with image_url parts (verified 17/11, d1.2 family)
        state = [state, *({"type": "image_url", "image_url": {"url": u}} for u in _liquid_media(media).get("images", []))]
    r = await client.post(OPENROUTER_DECISIONS, headers={"Authorization": f"Bearer {key('OPENROUTER_API_KEY')}"},
                          json={"model": model, "state": state, "questions": questions}, timeout=timeout)
    data = _json(r)
    if r.status_code >= 400 or not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise ProviderError(r.status_code, _error_code(data))
    usage = data.get("usage") or {}
    cost = _float(usage.get("cost"))
    return {"answers": data["answers"], "usage": usage, "model": data.get("model") or model,
            "cost_usd": cost, "cost_status": "reported" if cost is not None else "unknown",
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens")}


def _requested(body: dict, offered: list[str]) -> tuple[list[str] | None, str | None]:
    """The models to try: the Router's list, or the caller's narrowing of it (each must be offered)."""
    asked = body.get("models") if body.get("models") is not None else ([body["model"]] if body.get("model") else None)
    if asked is None:
        return list(offered), None
    if not isinstance(asked, list) or not asked or not all(isinstance(m, str) and m for m in asked):
        return None, "model/models must name models"
    unknown = [m for m in asked if m not in offered]
    if unknown:
        return None, "model not offered by the Router for this task: " + ", ".join(m[:80] for m in unknown)
    return list(dict.fromkeys(asked)), None


def _floor(body: dict) -> float | None:
    value = _float(body.get("paid_floor_usd"))
    return value if value is not None and value >= 0 else None


def _timeout(body: dict) -> float:
    value = _float(body.get("timeout"))
    return max(1.0, min(value, 120.0)) if value else DEFAULT_TIMEOUT


def _straggler(body: dict) -> float | None:
    """Seconds the late samples are given once a majority has answered; `straggler_s: null` waits for all of them."""
    if "straggler_s" in body and body["straggler_s"] is None:
        return None
    value = _float(body.get("straggler_s"))
    return STRAGGLER_S if value is None else max(0.0, min(value, 30.0))


async def _samples(once, n: int, grace: float | None) -> tuple[list, list[float]]:
    """n parallel samples. Once a majority has answered, the others get `grace` seconds, then are dropped: the mean
    is made of those that came (13/11/2026: one sample in three took 9.6 s and held the whole decision of a message
    past the time its caller waits). Returns (results of the finished samples, seconds of each dropped one)."""
    t0 = time.perf_counter()
    tasks = [asyncio.ensure_future(once()) for _ in range(n)]
    pending = set(tasks)
    need = n // 2 + 1
    while pending and sum(1 for t in tasks if t.done() and t.result()[1] is not None) < need:
        _, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    dropped: list[float] = []
    if pending:
        _, pending = await asyncio.wait(pending, timeout=grace)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            dropped = [round(time.perf_counter() - t0, 3)] * len(pending)
    return [t.result() for t in tasks if not t.cancelled()], dropped


# A route that cannot answer for a reason of its own — the model is gone at the provider (HTTP 404 / 410), the
# gateway has no grant or key for it — is set aside for a while instead of being asked again at every decision
# (2026-11-13: with the OpenRouter credit empty, each preflight decision spent 4.4 s on two such routes before
# failing, most of the time the caller waits). It is still named in `attempts` and `calls`, and asked again after.
UNAVAILABLE_S = 600.0
_unavailable: dict[str, tuple[float, str]] = {}


def _route_level(why: str) -> bool:
    return why.startswith(("HTTP 404", "HTTP 410", "missing_grant", "key_unavailable"))


OCCASIONS = ("turn", "incoming", "outgoing", "document", "result")
SAMPLING = ("mean", "first")


async def _first(once, n: int) -> tuple[list, int]:
    """Hedged samples: n identical calls at once, the first answer is the decision, the others are cancelled
    (17/11 replay of 600 preflight calls, d1.2-ultra: first of 2 = 614 / 665 ms p50 / p95 against 663 / 1119 for
    the mean of 3 with the same agreement with the jury, 0.910). Returns (finished results, how many cancelled)."""
    tasks = [asyncio.ensure_future(once()) for _ in range(n)]
    pending, done_all = set(tasks), []
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            done_all.append(t.result())
        if any(r[1] is not None for r in done_all):
            break
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return done_all, len(pending)


def _assign(models: list[str], questions: dict, media, usable: dict) -> tuple[dict, list]:
    """Each question → the first usable model of the chain that carries it (its kind, the media). Returns
    ({model: [question keys]} in chain order, [questions no model carries])."""
    import decision as wd
    groups: dict = {}
    nowhere = []
    for name, q in questions.items():
        for m in models:
            if not usable.get(m):
                continue
            try:
                wd.plan(provider_of(m), m, {name: q}, media)
            except wd.Unsupported:
                continue
            groups.setdefault(m, []).append(name)
            break
        else:
            nowhere.append(name)
    return {m: groups[m] for m in models if m in groups}, nowhere


def _carries(model: str, questions: dict, media) -> bool:
    import decision as wd
    try:
        wd.plan(provider_of(model), model, questions, media)
        return True
    except wd.Unsupported:
        return False


async def decisions(body: dict, *, chain: list[str], key, client, log, balance=None, signals=None) -> tuple[int, dict]:
    """Execute a decision request along the Router's chain. `log(entry)` receives one entry per physical call.

    Walter Decision (decision.py): the questions are checked against the language first, the caller's `need` gives
    the policy (reuse window, timeout cap, escalation, sampling), a decision already given is reused, and each
    answered call's journal entry carries the need, the schema key and the confidence per question (calibration).

    2.0 (17/11): `occasion` (+ `facts`, `options`, `now`) composes the questions from the signals the modules declare
    (`signals` = `walter decisions`); the reply adds `signals` (answers by signal id) and `trace` (asked, skipped and
    why, unavailable and why). Each question goes to the first model of the chain that carries it: the parts that
    need another route (a value read by OpenRouter's Extractions, an image) go to the model that has it, in parallel
    with the rest, and each part fails over along the models able to carry it. A part that fails or that no model
    carries leaves its optional signals `unavailable` (said, never guessed); a required one fails the decision."""
    import decision as wd
    state, questions = body.get("state"), body.get("questions")
    occasion = body.get("occasion")
    composed = None
    try:
        media = wd.check_media(body.get("media"))
    except wd.Invalid as exc:
        return 400, {"error": f"not a Walter decision: {exc}"}
    if occasion is not None:
        if occasion not in OCCASIONS:
            return 400, {"error": f"occasion must be one of {', '.join(OCCASIONS)}"}
        if not isinstance(state, dict):
            return 400, {"error": "state (object) required"}
        facts, opts = body.get("facts") or [], body.get("options") or {}
        if not isinstance(facts, list) or not all(isinstance(f, str) and f for f in facts):
            return 400, {"error": "facts is a list of names"}
        if not isinstance(opts, dict) or not all(isinstance(v, dict) for v in opts.values()):
            return 400, {"error": "options maps a set name to {option: description}"}
        if not isinstance(signals, dict) or not isinstance(signals.get("signals"), list):
            return 503, {"error": "decision signals unavailable (walter decisions)", "attempts": []}
        focus = body.get("focus")
        if focus is not None and (not isinstance(focus, str) or focus not in state):
            return 400, {"error": "focus names a key of the state (the part the cues read)"}
        # the cues read the event itself (`focus`: the new message), not the history the state carries beside it
        cue_text = wd.state_text(state[focus] if focus else state)
        facts = set(facts) | wd.cues(cue_text) | {f"media.{m['type']}" for m in media}
        ask = body.get("ask")
        if ask is not None:
            declared = {x.get("id") for x in signals["signals"] if occasion in (x.get("occasions") or ())}
            if not isinstance(ask, list) or not ask or not all(isinstance(a, str) and a for a in ask):
                return 400, {"error": "ask is a non-empty list of signal ids"}
            if set(ask) - declared:
                return 400, {"error": f"ask names signals not declared for {occasion}: "
                                      + ", ".join(sorted(set(ask) - declared))[:300]}
        layers = body.get("layers")
        if layers is not None and (not isinstance(layers, list) or not layers
                                   or not set(layers) <= {"observation", "inference"}):
            return 400, {"error": "layers is a non-empty list among observation, inference"}
        composed = wd.compose(signals["signals"], occasion, facts, opts, registry=signals.get("hash") or "", only=ask,
                              layers=layers)
        extra = questions if isinstance(questions, dict) else {}
        clash = sorted(set(extra) & set(composed["questions"]))
        if clash:
            return 400, {"error": "questions named like composed signals: " + ", ".join(clash)}
        questions = {**composed["questions"], **extra}
        trace = {"occasion": occasion, "registry": composed["registry"], "facts": composed["facts"],
                 "asked": composed["asked"], "skipped": composed["skipped"]}
        if not questions:
            return 200, {"answers": {}, "signals": {}, "trace": {**trace, "unavailable": {}}, "calls": [],
                         "attempts": [], "model": None, "provider": None, "route": None, "schema": None}
    elif not isinstance(state, dict) or not isinstance(questions, dict) or not questions:
        return 400, {"error": "state (object) and questions (non-empty object) required"}
    try:
        questions, schema = wd.compile_questions(questions)
    except wd.Invalid as exc:
        return 400, {"error": f"not a Walter decision: {exc}"}
    required = set(questions) if composed is None else \
        {composed["ids"][s] for s in composed["required"]} | (set(questions) - set(composed["questions"]))
    need = body.get("need") if isinstance(body.get("need"), str) and body.get("need") else None
    need = need[:80] if need else None
    pol = wd.policy(need)
    samples = body.get("samples", (pol.get("sampling") or {}).get("k", 1))
    if isinstance(samples, bool) or not isinstance(samples, int) or not 1 <= samples <= MAX_SAMPLES:
        return 400, {"error": f"samples must be an integer 1..{MAX_SAMPLES}"}
    mode = body.get("sampling") or (pol.get("sampling") or {}).get("mode") or "mean"
    if mode not in SAMPLING:
        return 400, {"error": "sampling is mean or first"}
    if not chain:
        return 503, {"error": "no_decision_chain", "attempts": []}
    models, refused = _requested(body, chain)
    if refused:
        return 400, {"error": refused, "chain": chain}
    floor, timeout = _floor(body), _timeout(body)
    if pol.get("max_timeout_s"):
        timeout = min(timeout, max(1.0, float(pol["max_timeout_s"])))
    now = body.get("now") if isinstance(body.get("now"), str) else None
    tag = {"need": need, "schema": schema}
    asked_state = state if not media and not now else \
        {"state": state, "media": wd._digest(media) if media else None, "now": (now or "")[:10]}
    memo_key = wd.Memo.key(models, samples if mode == "mean" else 1, asked_state, schema) \
        if pol.get("memo_ttl_s") and body.get("reuse", True) is not False else None
    if memo_key and (hit := wd.MEMO.get(memo_key)) is not None:
        log({"provider": hit.get("provider"), "model": hit.get("model"), "ok": True, "reused": True, "seconds": 0,
             "cost_usd": 0.0, "cost_status": "reused", **tag})
        return 200, {**hit, "reused": True, "calls": [], "attempts": []}
    attempts: list[dict] = []
    calls: list[dict] = []
    usable: dict = {}
    for model in models:                 # set-aside routes and the OpenRouter credit floor, once per decision
        provider = provider_of(model)
        aside = _unavailable.get(model)
        if aside and time.monotonic() < aside[0]:
            call = {"provider": provider, "model": model, "ok": False, "skipped": "route_unavailable",
                    "error": aside[1], "seconds": 0}
            attempts.append({"provider": provider, "model": model, "reason": f"route_unavailable: {aside[1]}"})
            calls.append(call)
            log({**call})
            continue
        # the floor is the OpenRouter credit's: a model billed elsewhere (Nace, Workers AI) is never held back by it
        if floor is not None and balance is not None and provider == "openrouter" and not is_free(model):
            bal = await balance()
            if bal is not None and bal < floor:
                attempts.append({"provider": provider, "model": model, "reason": "balance_below_floor"})
                calls.append({"provider": provider, "model": model, "ok": False, "skipped": "balance_below_floor",
                              "seconds": 0})
                log({"provider": provider, "model": model, "ok": False, "seconds": 0, "skipped": "balance_below_floor"})
                continue
        usable[model] = True
    groups, nowhere = _assign(models, questions, media, usable)
    for model in models:                 # a usable model that carries none of the questions: named, not an error
        if usable.get(model) and model not in groups and not any(_carries(model, {k: questions[k]}, media)
                                                                 for k in questions):
            try:
                wd.plan(provider_of(model), model, questions, media)
            except wd.Unsupported as exc:
                attempts.append({"provider": provider_of(model), "model": model, "reason": f"unsupported: {exc}"[:240]})
                calls.append({"provider": provider_of(model), "model": model, "ok": False, "skipped": "unsupported",
                              "seconds": 0})
                log({"provider": provider_of(model), "model": model, "ok": False, "seconds": 0,
                     "skipped": "unsupported", **tag})
    if nowhere and (set(nowhere) & required or not groups):
        if not groups and not usable:
            return 502, {"error": "no decision model answered", "attempts": attempts, "calls": calls}
        return 422, {"error": "no model of the decision chain can answer these questions", "attempts": attempts,
                     "calls": calls, "unsupported": nowhere}
    straggler = _straggler(body)

    async def part(names: list[str], first_model: str) -> tuple[dict | None, list, list]:
        sub = {k: questions[k] for k in names}
        # passages and boxes are never averaged (merge_answers keeps the first sample's): one call is the answer —
        # unless the samples are hedged (sampling "first"): the first of n identical calls is then the answer, which
        # cuts the tail of a slow route (17/11: OpenRouter's Extractions route, 0.1–3.6 s for the same kind of text)
        n = 1 if mode != "first" and all(wd.kind(q) in UNMERGED for q in sub.values()) else samples
        cands = [first_model] + [m for m in models[models.index(first_model) + 1:]
                                 if usable.get(m) and _carries(m, sub, media)]
        p_calls, p_attempts = [], []
        for i, model in enumerate(cands):
            provider = provider_of(model)

            async def once(model=model, provider=provider):
                t0 = time.perf_counter()
                try:
                    res = await decide_once(client, key, model, state, sub, timeout, *([media] if media else []))
                except Exception as exc:  # noqa: BLE001 — the next model able to carry this part
                    call = {"provider": provider, "model": model, "ok": False, "error": reason(exc),
                            "seconds": round(time.perf_counter() - t0, 3)}
                    log({**call})
                    return call, None
                call = {"provider": provider, "model": model, "ok": True,
                        "seconds": round(time.perf_counter() - t0, 3), "cost_usd": res["cost_usd"],
                        "cost_status": res["cost_status"], "input_tokens": res["input_tokens"]}
                log({**call, "usage": {"in": res["input_tokens"], "out": 0, "cached": None}, **tag,
                     "confidence": wd.confidences(res["answers"])})
                return call, res
            if mode == "first" and n > 1:
                got, cancelled = await _first(once, n)
                dropped = []
                for _ in range(cancelled):       # a hedge the answer did not wait for: billed, not an error
                    call = {"provider": provider, "model": model, "ok": False, "skipped": "hedged", "seconds": 0,
                            "cost_status": "unknown"}
                    p_calls.append(call)
                    log({**call, **tag})
            else:
                got, dropped = await _samples(once, n, straggler)
            p_calls += [c for c, _ in got]
            for seconds in dropped:              # a sample the answer did not wait for: counted, not an error
                call = {"provider": provider, "model": model, "ok": False, "skipped": "straggler", "seconds": seconds}
                p_calls.append(call)
                log({**call})
            ok = [res for _, res in got if res is not None]
            if not ok:
                why = str(got[0][0]["error"])
                p_attempts.append({"provider": provider, "model": model, "reason": why})
                if all(_route_level(str(c.get("error") or "")) for c, _ in got):
                    _unavailable[model] = (time.monotonic() + UNAVAILABLE_S, why[:120])
                continue
            _unavailable.pop(model, None)
            first = ok[0]
            res = {"answers": first["answers"] if len(ok) == 1 or mode == "first"
                   else merge_answers([r["answers"] for r in ok]),
                   "usage": first["usage"], "model": first["model"] if provider == "openrouter" else model,
                   "provider": provider, "route": f"{provider}/{model}", "questions": names}
            if n > 1:
                res["samples"] = 1 if mode == "first" else len(ok)
            doubt = wd.uncertain(res["answers"], pol.get("escalate_below"))
            nxt = next((m for m in cands[i + 1:] if not (_unavailable.get(m) and time.monotonic() < _unavailable[m][0])),
                       None)
            if doubt and nxt:
                res["escalated"] = await _escalate(res, doubt, nxt, state, sub, key=key, client=client, log=log,
                                                   timeout=timeout, tag=tag, media=media)
                p_calls.append(res["escalated"].pop("call"))
            return res, p_calls, p_attempts
        return None, p_calls, p_attempts

    done = await asyncio.gather(*(part(names, m) for m, names in groups.items()))
    answered, unavailable = [], {k: "unsupported: no model of the chain carries it" for k in nowhere}
    for res, p_calls, p_attempts in done:
        calls += p_calls
        attempts += p_attempts
        if res is not None:
            answered.append(res)
    failed = [k for (m, names), (res, _, pa) in zip(groups.items(), done) if res is None for k in names]
    if not answered or set(failed) & required:
        return 502, {"error": "no decision model answered", "attempts": attempts, "calls": calls,
                     **({"failed": failed} if answered else {})}
    for (m, names), (res, _, pa) in zip(groups.items(), done):
        if res is None:
            why = pa[-1]["reason"] if pa else "failed"
            unavailable.update({k: f"failed: {why}"[:160] for k in names})
    main = max(answered, key=lambda r: (len(set(r["questions"]) & required), len(r["questions"])))
    answers: dict = {}
    for r in answered:
        answers.update(r["answers"])
    answers = wd.resolve(questions, answers, now)
    out = {"answers": answers, "usage": main["usage"], "model": main["model"], "provider": main["provider"],
           "route": main["route"], "calls": calls, "attempts": attempts}
    if samples > 1:
        out["samples"] = main.get("samples")
    if mode == "first" and samples > 1:
        out["sampling"] = "first"
    if len(answered) > 1 or unavailable:
        out["parts"] = [{"model": r.get("model"), "route": r["route"], "questions": r["questions"]} for r in answered]
    esc = [r["escalated"] for r in answered if r.get("escalated")]
    if esc:
        out["escalated"] = esc[0] if len(esc) == 1 else {"parts": esc}
    if unavailable:
        out["unavailable"] = unavailable
    out["schema"], out["need"] = schema, need
    if composed is not None:
        out["signals"] = wd.by_signal(composed, answers)
        out["trace"] = {**trace, "unavailable": {sid: unavailable[k] for sid, k in composed["ids"].items()
                                                 if k in unavailable}}
        if signals.get("relations"):        # Decision Resolver (§6, 17/11): the answers resolved against the declared
            import resolver                 # relations, deterministically; `signals` stays what the models said
            out["resolution"] = resolver.resolve(out["signals"], signals["relations"], composed["facts"],
                                                 required=composed["required"], asked=composed["asked"])
    if memo_key and not unavailable:
        wd.MEMO.put(memo_key, {k: v for k, v in out.items() if k not in ("calls", "attempts")},
                    pol.get("memo_ttl_s") or 0)
    return 200, out


async def _escalate(out: dict, doubt: list[str], model: str, state: dict, questions: dict, *, key, client, log,
                    timeout: float, tag: dict, media=None) -> dict:
    """Ask the uncertain questions — only those — to the next model of the chain; its answers replace them."""
    import decision as wd
    provider, t0 = provider_of(model), time.perf_counter()
    try:
        res = await decide_once(client, key, model, state, {k: questions[k] for k in doubt}, timeout,
                                *([media] if media else []))
    except Exception as exc:  # noqa: BLE001 — the first answers stand
        call = {"provider": provider, "model": model, "ok": False, "error": reason(exc), "escalation": True,
                "seconds": round(time.perf_counter() - t0, 3)}
        log({**call, **tag})
        return {"model": model, "questions": doubt, "error": call["error"], "call": call}
    call = {"provider": provider, "model": model, "ok": True, "escalation": True,
            "seconds": round(time.perf_counter() - t0, 3), "cost_usd": res["cost_usd"],
            "cost_status": res["cost_status"], "input_tokens": res["input_tokens"]}
    log({**call, "usage": {"in": res["input_tokens"], "out": 0, "cached": None}, **tag,
         "confidence": wd.confidences(res["answers"])})
    replaced = [k for k in doubt if isinstance(res["answers"].get(k), dict)]
    out["answers"] = {**out["answers"], **{k: res["answers"][k] for k in replaced}}
    return {"model": model, "questions": replaced, "call": call}


async def rerank_once(client, key, model: str, query: str, documents: list[str], top_n: int, timeout: float) -> dict:
    r = await client.post(OPENROUTER_RERANK, headers={"Authorization": f"Bearer {key('OPENROUTER_API_KEY')}"},
                          json={"model": model, "query": query, "documents": documents, "top_n": top_n}, timeout=timeout)
    data = _json(r)
    if r.status_code >= 400 or not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ProviderError(r.status_code, _error_code(data))
    results = []
    for row in data["results"]:
        idx = row.get("index") if isinstance(row, dict) else None
        if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(documents):
            results.append({"index": idx, "relevance_score": _float(row.get("relevance_score"))})
    if not results and documents:
        raise ProviderError(r.status_code, "empty_results")
    usage = data.get("usage") or {}
    cost = _float(usage.get("cost"))
    return {"results": results, "usage": usage, "model": data.get("model") or model, "cost_usd": cost,
            "cost_status": "reported" if cost is not None else "unknown"}


async def rerank(body: dict, *, routes: list[dict], key, client, log, balance=None) -> tuple[int, dict]:
    """Execute a rerank request on the Router's `rerank` poste routes, in order."""
    query, documents = body.get("query"), body.get("documents")
    if not isinstance(query, str) or not query.strip():
        return 400, {"error": "query (non-empty string) required"}
    if not isinstance(documents, list) or not documents or len(documents) > MAX_DOCUMENTS \
            or not all(isinstance(d, str) for d in documents):
        return 400, {"error": f"documents must be 1..{MAX_DOCUMENTS} strings"}
    top_n = body.get("top_n") or len(documents)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        return 400, {"error": "top_n must be a positive integer"}
    top_n = min(top_n, len(documents))
    offered = [r["model"] for r in routes if r.get("model")]
    if not offered:
        return 503, {"error": "no_rerank_route", "attempts": []}
    models, refused = _requested(body, offered)
    if refused:
        return 400, {"error": refused, "offered": offered}
    floor, timeout = _floor(body), _timeout(body)
    attempts = []
    for route in [r for r in routes if r.get("model") in models]:
        provider, model = route.get("provider"), route["model"]
        base = {"provider": provider, "model": model}
        if provider != "openrouter":
            attempts.append({**base, "reason": f"no_adapter:{provider}"})
            continue
        if floor is not None and balance is not None and not is_free(model):
            bal = await balance()
            if bal is not None and bal < floor:
                attempts.append({**base, "reason": "balance_below_floor"})
                log({**base, "ok": False, "seconds": 0, "skipped": "balance_below_floor"})
                continue
        t0 = time.perf_counter()
        try:
            res = await rerank_once(client, key, model, query, documents, top_n, timeout)
        except Exception as exc:  # noqa: BLE001 — next route of the poste
            attempts.append({**base, "reason": reason(exc)})
            log({**base, "ok": False, "seconds": round(time.perf_counter() - t0, 3), "error": reason(exc)})
            continue
        seconds = round(time.perf_counter() - t0, 3)
        log({**base, "ok": True, "seconds": seconds, "cost_usd": res["cost_usd"], "cost_status": res["cost_status"],
             "usage": {"in": res["usage"].get("prompt_tokens") or res["usage"].get("total_tokens"), "out": 0,
                       "cached": None}})
        return 200, {"results": res["results"], "model": model, "provider": provider, "route": f"{provider}/{model}",
                     "usage": res["usage"], "cost_usd": res["cost_usd"], "cost_status": res["cost_status"],
                     "seconds": seconds, "attempts": attempts}
    return 502, {"error": "no rerank route answered", "attempts": attempts}


class Balance:
    """OpenRouter's remaining credit, cached 5 minutes; None when unknown (never blocks a free model)."""

    def __init__(self, client, key, ttl: float = 300):
        self.client, self.key, self.ttl = client, key, ttl
        self.value: tuple[float, float | None] | None = None

    async def __call__(self) -> float | None:
        if self.value and time.time() - self.value[0] < self.ttl:
            return self.value[1]
        try:
            r = await self.client.get(OPENROUTER_CREDITS, headers={"Authorization": f"Bearer {self.key('OPENROUTER_API_KEY')}"},
                                      timeout=15)
            d = r.json()["data"]
            value = float(d["total_credits"]) - float(d["total_usage"])
        except Exception:  # noqa: BLE001 — unknown balance: the floor cannot refuse
            value = None
        self.value = (time.time(), value)
        return value
