---
name: memory-vector-recall-architecture
description: Audit and maintain dual vector-recall memory systems with quality embeddings plus low-latency local voice embeddings.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [memory, embeddings, qdrant, voice, recall, latency]
---

# Memory Vector Recall Architecture

Use this skill when Monsieur asks whether a local embedding service is redundant, when auditing voice-memory latency, or when maintaining systems that keep both a quality vector path and a low-latency local vector path.

## Core model

Many memory stacks deliberately run two vector paths:

1. **Quality path** — higher-quality hosted embeddings, larger vectors, rerankers, PostgreSQL-backed recall, better written answers.
2. **Voice/ultra path** — small local embedding model, small vectors, direct vector search, very low latency for live speech.

Do not call the local path redundant until you have checked which actor uses it and measured fallback latency. A service can be architecturally redundant for written recall but still critical for voice UX. Charming, this is how one saves RAM and accidentally makes the butler sound drunk.

## Audit sequence

1. Identify the callers first: voice router, gateway endpoints, timers, systemd reverse dependencies, and sync jobs.
2. Check collections separately: vector size, model, point count, and whether payloads map back to the same source-of-truth facts.
3. Compare actual latency for the ultra path and fallback path with live requests.
4. Compare actual resident memory, not model-card size or old design notes.
5. Inspect sync path: source-of-truth table, eligibility filter, deterministic point IDs, and endpoint names.
6. Decide based on trade-off: RAM saved versus voice latency lost.

## Durable pitfalls

- Never mix embeddings from different models in one vector collection. Different vector spaces make cosine similarity meaningless.
- A local MiniLM-style service commonly needs a separate collection from a hosted Gemini-style service because dimensions and vector spaces differ.
- Planning estimates for local model memory can be wildly lower than runtime RSS; measure the process.
- Verify service unit dimensions against the actual health endpoint. Stale values like `768` in config while the service returns `384` create future confusion.
- Verify batch endpoint names. A sync script calling one route while the service exposes another silently degrades into slow individual requests if fallback exists.
- Bind low-level embedding services to loopback unless a real remote consumer exists.
- If the voice path has fallback to hosted recall, stopping local embed may not break functionality, but it can increase response latency by orders of magnitude.

## Recommended decision frame

Keep the local embed service when:

- live voice or speech-to-speech recall is important;
- measured local recall is tens of milliseconds;
- fallback recall is hundreds of milliseconds or seconds;
- RAM headroom is acceptable.

Make it on-demand or disable it when:

- the system is memory-constrained;
- voice recall is not active;
- fallback quality matters more than immediacy;
- the service only exists for periodic sync and not live calls.

## W.Alter Jarvis audit note

In the W.Alter memory stack, the local embed path observed on 2026-06-29 was a voice-first optimization, not the principal Hindsight path: local MiniLM vectors backed an ultra-fast recall route and a separate local Qdrant collection, while the main quality path used the larger Hindsight/Gemini collection. The loaded `jarvis-memory-system` skill overlaps this topic and should be patched when the scanner permits it.

## References

- `references/walter-local-embed-audit-2026-06-29.md` — sanitized audit notes from the W.Alter local embed investigation.
