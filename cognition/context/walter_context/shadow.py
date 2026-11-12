"""shadow: what the recorded shadow plans say, day by day (lot 4, step D). Read-only over the instance records.

    walter-context-preflight --report [--days N]

For each owner message the hook sent in shadow mode: the plan (level, subject, fast path), the context pack
walter-context would have injected and what the hook injects today. Totals compare the two; they say nothing yet
about answer quality (step G judges that on the same records).
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


def rows(folder: Path, days: int = 1) -> list[dict]:
    out = []
    for k in range(days):
        day = datetime.now(timezone.utc) - timedelta(days=k)
        path = folder / f"preflight-{day:%Y-%m-%d}.jsonl"
        if path.exists():
            out += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return out


def _degraded(r: dict) -> bool:
    return bool((r.get("plan", {}).get("decision") or {}).get("degraded"))


def report(folder: Path, days: int = 1) -> dict:
    rs = [r for r in rows(folder, days) if r.get("plan")]
    packed = [r for r in rs if r.get("pack")]
    med = lambda xs: round(statistics.median(xs)) if xs else None          # noqa: E731
    pack_t = [r["pack"]["tokens_per_message"] for r in packed]
    cur_t = [(r.get("current") or {}).get("tokens") or 0 for r in packed]
    return {
        "messages": len(rs), "errors": sum(1 for r in rows(folder, days) if r.get("error")),
        "levels": dict(Counter(r["plan"]["level"] for r in rs)),
        "fast_paths": dict(Counter(r["plan"].get("fast_path") or ("degraded" if _degraded(r) else "decision")
                                   for r in rs)),
        # SOCLE A2: a failed decision gives an explicit prudent plan; counted apart (and in `levels` as their L3)
        "degraded": sum(1 for r in rs if _degraded(r)),
        "degraded_errors": dict(Counter(str((r["plan"].get("decision") or {}).get("error") or "?").split(":")[0]
                                        for r in rs if _degraded(r))),
        "previous_fetched": dict(Counter(str(r["previous"]).split(":")[0] for r in rs if r.get("previous"))),
        "cuts": dict(Counter(f"{c['block'].split(':')[0]}:{c['action']}" for r in packed for c in r["pack"].get("cuts") or [])),
        "subjects": dict(Counter((r["plan"]["thread"]["id"] or "new") for r in rs).most_common(8)),
        "plan_ms_median": med([r.get("plan_ms") for r in rs if r.get("plan_ms") is not None]),
        "retrieval_ms_median": med([r["pack"]["retrieval_ms"] for r in packed]),
        "tokens_per_message": {"walter_context_median": med(pack_t), "current_hook_median": med(cur_t),
                               "walter_context_total": sum(pack_t), "current_hook_total": sum(cur_t)},
        "session_layer_tokens_median": med([r["pack"]["tokens_session_layer"] for r in packed]),
        "nothing_injected": {"walter_context": sum(1 for t in pack_t if not t), "current_hook": sum(1 for t in cur_t if not t)},
        "source_failures": dict(Counter(n.split(":")[0] for r in packed for n in r["pack"].get("notes") or [])),
    }
