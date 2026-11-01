"""walter-skills CLI — operator's view of the module.

  search "message" [--context …] [--archived]      ranking as the agents get it
  expose "message" [--runtime …] [--session …]    exactly what the policy would show
  read <name> [--file path]                       a skill (or one of its files)
  nightly [--only step,…]                         the nightly graph (see jobs.py)
  quick                                           every 15 min: Hermes sync → judged drafts live → cards
  sync | cards | catalog | implicit | judge | sessions | train [--force] | curate [--apply|--shadow] | map | digest
  health                                          problems as JSON, exit 1 if any (5-min watchdog)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser(prog="walter-skills")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("message"); s.add_argument("--context", default=""); s.add_argument("--archived", action="store_true")
    s.add_argument("-k", type=int, default=8)
    x = sub.add_parser("expose")
    x.add_argument("message"); x.add_argument("--context", default=""); x.add_argument("--runtime", default="cli")
    x.add_argument("--session"); x.add_argument("--first", action="store_true"); x.add_argument("--kind", default="message")
    r = sub.add_parser("read")
    r.add_argument("name"); r.add_argument("--file", default=None)
    n = sub.add_parser("nightly")
    n.add_argument("--only", default="")
    for c in ("sync", "cards", "catalog", "implicit", "judge", "sessions", "map", "digest", "health", "quick"):
        sub.add_parser(c)
    sub.add_parser("manifest")
    br = sub.add_parser("brief")
    br.add_argument("--json", action="store_true"); br.add_argument("--map-only", action="store_true"); br.add_argument("--search-tool", default="skills_search")
    ix = sub.add_parser("index")
    ix.add_argument("--domain", default="")
    ix.add_argument("--offset", type=int, default=0)
    ix.add_argument("--limit", type=int, default=20)
    t = sub.add_parser("train")
    t.add_argument("--force", action="store_true")
    cu = sub.add_parser("curate")
    cu.add_argument("--apply", action="store_true"); cu.add_argument("--shadow", action="store_true")
    cu.add_argument("--only", default="")
    a = ap.parse_args()
    p = lambda o: print(json.dumps(o, ensure_ascii=False, indent=1, default=str))  # noqa: E731

    if a.cmd == "search":
        from . import policy
        for row in policy.search(a.message, a.context, a.k, a.archived, runtime="cli"):
            print(f"{row['score']:8.3f}  {row['state']:8} {row['name']:42} {row['summary'][:90]}")
    elif a.cmd == "expose":
        from . import policy
        e = policy.expose(a.kind, a.message, context=a.context, session_id=a.session, runtime=a.runtime, first_turn=a.first)
        print(f"[{e.mode} · {e.reason} · {e.latency_ms} ms]\n{e.text}")
    elif a.cmd == "read":
        from .retrieval import read_skill
        text = read_skill(a.name, a.file)
        if text is None:
            print(f"unknown: {a.name}", file=sys.stderr)
            return 1
        print(text)
    elif a.cmd == "nightly":
        from . import jobs
        p(jobs.nightly(set(filter(None, a.only.split(","))) or None))
    elif a.cmd == "quick":
        from . import jobs
        p(jobs.quick())
    elif a.cmd == "sync":
        from . import hermes_sync
        p({k: (v if isinstance(v, int) else v[:20]) for k, v in hermes_sync.sync().items()})
    elif a.cmd == "cards":
        from . import cards
        p(cards.refresh())
    elif a.cmd == "catalog":
        from . import jobs
        print(f"{jobs.catalog()} skills in skills.catalog")
    elif a.cmd in ("implicit", "judge", "sessions"):
        from . import learning
        p({"implicit": learning.implicit, "judge": learning.judge, "sessions": learning.drafts_from_sessions}[a.cmd]())
    elif a.cmd == "train":
        from . import learning
        p(learning.train_and_promote(force=a.force))
    elif a.cmd == "curate":
        from . import curation
        apply = True if a.apply else (False if a.shadow else None)
        p(curation.run(apply=apply, only=set(filter(None, a.only.split(","))) or None))
    elif a.cmd == "map":
        from . import domains
        domains.build()
        print(domains.render("skills_search"))
    elif a.cmd == "brief":
        from . import domains
        if a.map_only:
            print(domains.domain_map())
            return
        doc = domains.brief_document(a.search_tool)
        print(json.dumps(doc, ensure_ascii=False) if a.json else doc["content"])
    elif a.cmd == "manifest":
        from . import domains
        print(domains.manifest())
    elif a.cmd == "index":
        from . import domains
        p(domains.index(a.domain, a.offset, a.limit))
    elif a.cmd == "digest":
        from . import curation
        text = curation.digest()
        print(text)
        subprocess.run(["/root/.hermes/hermes-agent/venv/bin/hermes", "send", "-t", "telegram", text],
                       capture_output=True, text=True, timeout=120)
    elif a.cmd == "health":
        from . import jobs
        problems, m = jobs.health()
        p({"problems": problems, "metrics": m})
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
