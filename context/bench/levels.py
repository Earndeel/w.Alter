"""Levels bench (2026-11-07): per owner message, which context does each DSH injection policy put in the window, and
does it hold what the answer needs? Policies: `legacy` (the hook's memory block, the same whatever the plan) and
`pack` (walter-context: plan → level L0-L3 → blocks). Per case: planned level vs expected, injected tokens, gold
recall (one reference substring found, accents and case ignored). Cases are the instance's
(@instance/config/context/bench-levels.json); the output carries numbers and hit/miss only, never context text.

    walter-python bench/levels.py [--cases FILE] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def hit(text: str, gold: list[str]) -> bool | None:
    return None if not gold else any(norm(g) in norm(text) for g in gold)


def tokens(text: str) -> int:
    return round(len(text) / 3.6) if text else 0      # same estimate for both policies


def hook():
    root = subprocess.run(["walter", "path", "core"], capture_output=True, text=True).stdout.strip()
    sys.path.insert(0, str(Path(root) / "hooks"))
    import walter_hook
    return walter_hook


def legacy(h, case: dict) -> dict:
    t0 = time.time()
    text = h.memory_context(case["message"], "dsh-hook", "bench-levels")
    return {"tokens": tokens(text), "recall": hit(text, case["gold"]), "ms": round((time.time() - t0) * 1000)}


def pack(case: dict, port: str = "8897") -> dict:
    prev = case.get("previous")
    req = {"turn_id": f"bench-levels:{case['id']}:{int(time.time() * 1000)}", "message": case["message"],
           "previous": ({"user": prev["user"], "assistant": prev["assistant"], "age_s": 60} if prev else None),
           "runtime": "dsh", "session_id": "dsh/vm/bench-levels", "privacy_class": "cloud_allowed", "run_id": None,
           "exclude_blocks": ["capabilities"]}
    t0 = time.time()
    r = urllib.request.Request(f"http://127.0.0.1:{port}/preflight?inject=1", data=json.dumps(req).encode(),
                               headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(r, timeout=60).read())
    text, plan = out.get("text") or "", out.get("plan") or {}
    blocks = (out.get("pack") or {}).get("blocks") or []
    return {"level": plan.get("level"), "fast_path": plan.get("fast_path"), "tokens": tokens(text),
            "recall": hit(text, case["gold"]), "level_ok": plan.get("level") in case["levels"],
            "blocks": {b["id"]: b.get("tokens") for b in blocks if b.get("injected", True)},
            "ms": round((time.time() - t0) * 1000)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases")
    ap.add_argument("--json")
    a = ap.parse_args()
    path = a.cases or subprocess.run(["walter", "instance", "config", "context", "bench-levels.json"],
                                     capture_output=True, text=True).stdout.strip()
    cases = json.loads(Path(path).read_text())["cases"]
    h = hook()
    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(lambda c: {"id": c["id"], "expected": c["levels"], "legacy": legacy(h, c), "pack": pack(c)}, cases))
    summary = {}
    for pol in ("legacy", "pack"):
        graded = [r[pol]["recall"] for r in rows if r[pol]["recall"] is not None]
        summary[pol] = {"recall": f"{sum(graded)}/{len(graded)}", "tokens_total": sum(r[pol]["tokens"] for r in rows),
                        "tokens_L0_L1": sum(r[pol]["tokens"] for r in rows if r["expected"][0] in ("L0", "L1"))}
    summary["pack"]["level_ok"] = f'{sum(r["pack"]["level_ok"] for r in rows)}/{len(rows)}'
    out = {"summary": summary, "rows": rows}
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False))
    for r in rows:
        L, P = r["legacy"], r["pack"]
        print(f'{r["id"]:16} attendu {"/".join(r["expected"]):6} pack {P["level"]} {"ok" if P["level_ok"] else "KO"} '
              f'| legacy {L["tokens"]:5} tok rappel {L["recall"]} | pack {P["tokens"]:5} tok rappel {P["recall"]} {P["blocks"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
