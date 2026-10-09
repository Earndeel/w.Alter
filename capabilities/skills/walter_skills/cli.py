"""walter-skills CLI.

  sync      Hermes → store (one-way; Hermes keeps its own skills and curator)
  cards     (re)generate trigger cards for new/changed skills (poste skills.indexer)
  train     rebuild the learned retriever from walter_logs + judged labels
  catalog   refresh the Postgres catalogue (skills.catalog) from the store
  search    "message" [--context …] [--archived]
  read      name [--file path]
  curate    curator run (config/curator.json: shadow until shadow_until, then active) [--apply|--shadow] [--no-models]
  digest    weekly curator digest to Telegram (via `hermes send`)
  nightly   sync + cards + catalog + train (+ service reload) + curator report
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import cards, curator, engine, hermes_sync, store


def catalog() -> int:
    sys.path.insert(0, "/opt/walter-memory")
    from walter_memory.db import connection
    n = 0
    with connection() as conn:
        names = []
        for s in store.iter_skills(include_archived=True, include_drafts=True):
            c = cards.load(s.name) or {}
            sha = store.tree_hash(s.path)
            conn.execute(
                """insert into skills.catalog (name, state, domain, owner, origin, description, summary, path,
                                               content_sha, card_sha, meta, updated_at)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                   on conflict (name) do update set state = excluded.state, domain = excluded.domain,
                     owner = excluded.owner, origin = excluded.origin, description = excluded.description,
                     summary = excluded.summary, path = excluded.path, content_sha = excluded.content_sha,
                     card_sha = excluded.card_sha, meta = excluded.meta,
                     updated_at = case when skills.catalog.content_sha is distinct from excluded.content_sha
                                       or skills.catalog.state is distinct from excluded.state
                                       then now() else skills.catalog.updated_at end""",
                (s.name, s.state, s.domain, s.meta.get("owner"), s.meta.get("origin"), s.description[:2000],
                 c.get("summary"), str(s.path), sha, c.get("sha"), json.dumps(s.meta)))
            names.append(s.name)
            n += 1
        conn.execute("delete from skills.catalog where not (name = any(%s))", (names,))
    return n


def main() -> int:
    ap = argparse.ArgumentParser(prog="walter-skills")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    c = sub.add_parser("cards")
    c.add_argument("--force", action="store_true")
    t = sub.add_parser("train")
    t.add_argument("--log-weight", type=float, default=0.0)
    sub.add_parser("catalog")
    s = sub.add_parser("search")
    s.add_argument("message")
    s.add_argument("--context", default="")
    s.add_argument("--archived", action="store_true")
    s.add_argument("-k", type=int, default=5)
    r = sub.add_parser("read")
    r.add_argument("name")
    r.add_argument("--file", default=None)
    cu = sub.add_parser("curate")
    cu.add_argument("--apply", action="store_true")
    cu.add_argument("--shadow", action="store_true")
    cu.add_argument("--no-models", action="store_true")
    dg = sub.add_parser("digest")
    dg.add_argument("--dry-run", action="store_true")
    sub.add_parser("nightly")
    a = ap.parse_args()

    if a.cmd == "sync":
        st = hermes_sync.sync()
        print(json.dumps({k: (v if isinstance(v, int) else v[:20] + (["…"] if len(v) > 20 else [])) for k, v in st.items()}))
    elif a.cmd == "cards":
        print(json.dumps(cards.build(list(store.iter_skills(include_archived=True)), force=a.force)))
    elif a.cmd == "train":
        print(json.dumps(engine.train(log_weight=a.log_weight), indent=1, default=str))
    elif a.cmd == "catalog":
        print(f"{catalog()} skills in skills.catalog")
    elif a.cmd == "search":
        e = engine.load_engine()
        for row in e.search(a.message, a.context, k=a.k, include_archived=a.archived):
            print(f"{row['score']:8.3f}  {row['state']:8} {row['name']:40} {row['summary'][:90]}")
    elif a.cmd == "read":
        text = engine.read_skill(a.name, a.file)
        if text is None:
            print(f"unknown: {a.name}", file=sys.stderr)
            return 1
        print(text)
    elif a.cmd == "curate":
        apply = True if a.apply else (False if a.shadow else None)
        r = curator.run(apply=apply, use_models=not a.no_models)
        print(json.dumps(r["summary"]), r["branch"] or "master")
    elif a.cmd == "digest":
        text = curator.digest()
        print(text)
        if not a.dry_run:
            subprocess.run(["/root/.hermes/hermes-agent/venv/bin/hermes", "send", "-t", "telegram", text],
                           capture_output=True, text=True, timeout=120)
    elif a.cmd == "nightly":
        st = hermes_sync.sync()
        print("sync", {k: (v if isinstance(v, int) else len(v)) for k, v in st.items()})
        print("cards", cards.build(list(store.iter_skills(include_archived=True))))
        store.commit("cards refresh", paths=["index/cards"])
        print("catalog", catalog())
        print("train", {k: v for k, v in engine.train().items() if k != "weights"})
        subprocess.run(["systemctl", "try-restart", "walter-skills"], check=False)
        print("curator", curator.run()["summary"])
        subprocess.run(["systemctl", "try-restart", "walter-skills"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
