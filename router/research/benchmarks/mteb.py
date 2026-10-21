"""MTEB results: French retrieval of every embedding model OpenRouter serves."""
from __future__ import annotations

from datetime import datetime
from urllib.error import HTTPError

from walter_router.analysis import identity
from walter_router.research.web import _github_json, fetch_json, now

# MTEB results repository: French retrieval = MIRACL hard negatives, subset fr (nDCG@10), for every embedding model
# OpenRouter serves (matched by our normalised id). GitHub API (60 calls/h without a token): one listing + one per model.
MTEB_API = "https://api.github.com/repos/embeddings-benchmark/results/contents/results"


MTEB_RAW = "https://raw.githubusercontent.com/embeddings-benchmark/results/main/results"


MTEB_FR = {"retrieval_fr": ("MIRACLRetrievalHardNegatives", "fr")}


OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/models?output_modalities=embeddings"


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
