"""Service postes stt / rerank / embeddings (2026-10-16): AA Speech-to-Text, Agentset and MTEB boards."""
from __future__ import annotations

import json

import pytest

from walter_router import collect, db, identity, media, scoring


def _flight(payload: str) -> str:
    """A server-rendered Next.js page carrying `payload` in its flight data."""
    return f"<script>self.__next_f.push([1,{json.dumps(payload)}])</script>"


def test_aa_stt_tables_join_on_model_and_host():
    wer_price = {"data": [{"Model": "MAI-Transcribe-2", "Provider": "Microsoft AI", "AA-WER Index": 0.0204,
                           "Price per 1k Min": 1.67}], "fileName": "STT AA-WER vs Price"}
    wer_speed = {"data": [{"Model": "MAI-Transcribe-2", "Provider": "Microsoft AI", "AA-WER Index": 0.0204,
                           "Speed Factor": 317.6}], "fileName": "STT AA-WER vs Speed Factor"}
    other = {"data": [{"Model": "x", "AA-WER Index": 0.5}], "fileName": "STT AA-WER vs Active Parameters"}
    page = _flight("".join(f'{{"downloadData":{json.dumps(t, separators=(",", ":"))}}}' for t in (wer_price, wer_speed, other)))
    rows = collect.aa_stt_rows(page)
    assert rows == [{"model": "MAI-Transcribe-2", "provider": "Microsoft AI", "wer": 0.0204,
                     "price_per_1k_min": 1.67, "speed_factor": 317.6}]
    bench = collect.parse_benchmarks("aa_stt", {"rows": rows})
    wer = next(b for b in bench if b["task"] == "wer")
    assert wer["score"] == pytest.approx(97.96) and wer["extra"]["wer_pct"] == pytest.approx(2.04)   # higher = better
    assert wer["cost"] == pytest.approx(0.00167) and wer["cost_unit"] == "usd_per_audio_minute"


def test_agentset_entries_and_latency_as_speed():
    entries = [{"rank": 1, "name": "Cohere Rerank 4 Pro", "score": 1629, "provider": "Cohere", "license": "Proprietary",
                "description": "ELO: 1629 | Win Rate: 57.7%", "avgLatencyMs": 500.0, "avgNdcg10": 0.09,
                "costPer1MTokens": 0.05}]
    page = _flight('Last updated: ","February 15, 2026"]' + json.dumps({"entries": entries}, separators=(",", ":")))
    board = collect.agentset_board(page)
    assert board["updated"] == "February 15, 2026" and board["entries"][0]["score"] == 1629
    rows = collect.parse_benchmarks("agentset", {"boards": {"rerank": board}})
    by_task = {r["task"]: r for r in rows}
    assert by_task["rerank"]["model_id"] == "rerank-4-pro" and by_task["rerank"]["extra"]["win_rate"] == 57.7
    assert by_task["rerank_speed"]["score"] == pytest.approx(2.0)   # 1000 / 500 ms


@pytest.mark.parametrize("ns,key,host,expected", [
    ("aa_stt", "Whisper (L, v3, Turbo), Groq", "Groq", ("whisper-large-v3-turbo", "")),
    ("aa_stt", "Parakeet TDT 0.6B V3, Togetherai", "Together AI", ("parakeet-tdt-0-6b-v3", "")),
    ("aa_stt", "Gemini 3.1 Flash-Lite Preview (Minimal)", "Google", ("gemini-3-1-flash-lite-preview", "minimal")),
    ("aa_stt", "Large v2", "OpenAI", ("whisper-1", "")),
    ("aa_stt", "Grok Voice Transcribe 1.0", "SpaceXAI", ("grok-stt-1", "")),
    ("agentset", "Cohere Rerank 3.5", None, ("rerank-v3-5", "")),
    ("agentset", "Gemini Embedding 2", None, ("gemini-embedding-2-preview", "")),
    ("agentset", "BAAI/bge-m3", None, ("bge-m3", "")),
    ("mteb", "Qwen__Qwen3-Embedding-8B", None, ("qwen-3-embedding-8b", "")),
])
def test_service_board_identities(ns, key, host, expected):
    assert identity.normalize(ns, key, host) == expected


def test_service_offers_land_on_their_interface_with_comparable_prices():
    doc = {"data": [
        {"id": "openai/whisper-large-v3-turbo", "name": "OpenAI: Whisper Large V3 Turbo",
         "architecture": {"input_modalities": ["audio"], "output_modalities": ["transcription"]},
         "pricing": {"prompt": "0.00000333", "completion": "0"},
         "_display_pricing": [{"kind": "unit", "sku_label": "Audio Seconds", "price": "0.00000333",
                               "displayMultiplier": 1, "unitLabel": "/second"}]},
        {"id": "google/gemini-3.1-flash-lite", "name": "Google: Gemini 3.1 Flash Lite",
         "architecture": {"input_modalities": ["text", "audio"], "output_modalities": ["text"]},
         "pricing": {"prompt": "0.00000025", "completion": "0.0000015", "audio": "0.0000005"}},
        {"id": "openai/text-embedding-3-small", "name": "OpenAI: Text Embedding 3 Small",
         "architecture": {"input_modalities": ["text"], "output_modalities": ["embeddings"]},
         "pricing": {"prompt": "0.00000002", "completion": "0"}},
        {"id": "cohere/rerank-4-fast", "name": "Cohere: Rerank 4 Fast",
         "architecture": {"input_modalities": ["text"], "output_modalities": ["rerank"]},
         "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    rows = {r["offer_key"]: r for r in collect.parse_offers("openrouter", doc)}
    whisper = rows["openai/whisper-large-v3-turbo"]
    assert whisper["interface"] == "transcription" and whisper["price_in_1m"] is None   # per second, not a token price
    sku = rows["openai/whisper-large-v3-turbo | Audio Seconds"]
    assert sku["norm_price"] == pytest.approx(0.0001998) and sku["norm_unit"] == "per minute"
    assert rows["google/gemini-3.1-flash-lite"]["interface"] == "chat"
    heard = rows["google/gemini-3.1-flash-lite | audio input"]
    assert heard["interface"] == "transcription" and heard["price_in_1m"] == pytest.approx(0.5)
    emb = rows["openai/text-embedding-3-small"]
    assert emb["interface"] == "embedding" and emb["norm_price"] == pytest.approx(0.02) and emb["norm_unit"] == "per 1m tokens"
    assert rows["cohere/rerank-4-fast"]["interface"] == "rerank" and rows["cohere/rerank-4-fast"]["price_in_1m"] is None
    assert media.norm_price("transcription", 0.1, "per hour", "Audio Hours") == (pytest.approx(0.1 / 60), "per minute")


def test_service_postes_rank_on_their_boards_and_stay_pinned():
    with db.connect() as conn:
        tasks = {r["task"]: r for r in conn.execute(
            "select * from models.tasks where task in ('stt', 'rerank', 'embeddings')")}
        assert tasks["stt"]["interface"] == "transcription" and tasks["embeddings"]["interface"] == "embedding"
        assert all(t["quality_benchmark"] for t in tasks.values())
        assert "revectoriser" in tasks["embeddings"]["requirements"]["on_change"]
        pins = {r["task"]: r["pinned_model_id"] for r in conn.execute(
            "select task, pinned_model_id from models.preferences where task in ('stt', 'rerank', 'embeddings')")}
        assert len(pins) == 3 and all(pins.values())   # never switched by a refresh: only Monsieur's « Changer »
        rerank = scoring.composite(conn, "rerank")
        if rerank:   # the 0.7 s recall budget excludes slower rerankers
            assert all((c.get("latency_ms") or 0) <= 700 for c in rerank)
