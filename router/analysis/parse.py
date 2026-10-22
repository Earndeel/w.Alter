"""Understanding a snapshot: leaderboard rows -> models.benchmarks, catalogue rows -> models.offers."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from walter_router.analysis import identity
from walter_router.analysis import media
from walter_router.research.prices.openrouter import MEDIA_INTERFACES, UNIT_PRICED_INTERFACES, _or_interface

MM_TASKS = {"provider_voice": "tts", "index": "speech_to_speech"}


# Kie publishes a few chat price rows with a wrong dimension label; each fix is checked against the
# published input price and the vendor's 1:5 input/output ratio before being added here.
KIE_DIMENSION_FIXES = {("claude-opus-5-5", "claude-opus-5"): "output"}


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
    elif kind == "aa_eval":
        units = {k: v.get("unit") for k, v in (doc.get("evals") or {}).items()}
        for r in doc["data"]:
            mid, variant = identity.normalize("aa", r["slug"], r.get("name"))
            for key, unit in units.items():
                value = _num(r.get(key))
                if value is None:
                    continue
                rows.append(dict(benchmark="aa_eval", task=key, external_key=r["slug"], model_id=mid, variant=variant,
                                 display_name=r.get("name"), score=round(value * 100, 3) if unit == "pct" else value,
                                 score_unit={"pct": "%", "elo": "Elo", "index": "AA index"}.get(unit, unit),
                                 cost=None, cost_unit=None, released=None, extra={"source": (doc.get("evals") or {}).get(key, {}).get("page")}))
        for key, models in (doc.get("indexes") or {}).items():
            for r in models:
                mid, variant = identity.normalize("aa", r["slug"], r.get("name"))
                rows.append(dict(benchmark="aa_eval", task=key, external_key=r["slug"], model_id=mid, variant=variant,
                                 display_name=r.get("name"), score=r["index"], score_unit="AA domain index",
                                 cost=r.get("cost_per_task"), cost_unit="usd_per_aa_task" if r.get("cost_per_task") else None,
                                 released=None, extra={"time_per_task_s": r.get("time_per_task_s"),
                                                       "sub_scores": r.get("sub_scores")}))
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
    elif kind == "video_evals":
        # Video-MME-v2: measured by its authors (with / without subtitles). LLM Stats: vendors' own claims, flagged
        # self_reported (the analysis weighs them half). Scores on 0-100.
        for r in (doc.get("video_mme_v2") or {}).get("rows") or []:
            mid, variant = identity.normalize("video_evals", r["name"])
            extra = {"frames": r.get("frames"), "avg_acc": r.get("avg_acc"), "type": r.get("type"), "stale": r.get("stale")}
            for task, score in zip(("with_subtitles", "without_subtitles"), r["overall"]):
                if score is not None:
                    rows.append(dict(benchmark="video_mme_v2", task=task, external_key=f'{r["name"]} | {r.get("frames") or ""}',
                                     model_id=mid, variant=variant, display_name=r["name"], score=round(score, 2),
                                     score_unit="Video-MME-v2 non-linear score /100", cost=None, cost_unit=None,
                                     released=None, extra=extra))
        for board, b in (doc.get("llm_stats") or {}).items():
            for m in b.get("models") or []:
                score = _num(m.get("score"))
                if score is None or not m.get("model_id"):
                    continue
                mid, variant = identity.normalize("video_evals", m["model_id"])
                rows.append(dict(benchmark="llm_stats", task=board, external_key=m["model_id"], model_id=mid,
                                 variant=variant, display_name=m.get("model_name"), score=round(100 * score, 2),
                                 score_unit=f'{b.get("name") or board} % (LLM Stats)', cost=None, cost_unit=None,
                                 released=None,
                                 extra={"self_reported": bool(m.get("self_reported")), "verified": bool(m.get("verified")),
                                        "organization": m.get("organization_name"), "method": m.get("analysis_method"),
                                        "source": m.get("self_reported_source"), "updated": b.get("updated_at")}))
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


OR_BASE_UNITS = {"/M characters": "per character", "/M UTF-8 bytes": "per utf-8 byte", "/minute": "per second",
                 "/1K calls": "per call", "/M tokens": "per token"}


def _or_name(name: str | None) -> str | None:
    """'Black Forest Labs: FLUX.3 Image' -> 'FLUX.3 Image'; short names keep their vendor ('MiniMax H3', 'HeyGen Video 1')."""
    if not name:
        return None
    vendor, _, rest = name.partition(": ")
    return (rest if len(rest) >= 9 and " " in rest else f"{vendor} {rest}") if rest else vendor


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
            if interface in ("decisions", "chat"):   # what the model can read besides text (image, audio, video, file)
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
