"""walter-skills-watch — event-driven: a skill changes, it is judged and live within seconds. No timer.

Sources (file events, whoever the author — Hermes' agent, Monsieur by hand, a Hermes update, the write door):
  ~/.hermes/skills/<…>/<skill>/…   → once the edit has settled, sync THAT skill → draft → judged → live + card
  /opt/walter-skills/drafts/       → a proposal from Claude Code / Codex / DSH → judged → live + card
Safety net: a full pass every hour (a missed event is caught there). Work is serialised in one thread; git writes are
serialised across processes by store.write_lock.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import cards, curation, hermes_sync, jobs, registry, store

HERMES = hermes_sync.HERMES
SETTLE = {"hermes": 20.0, "drafts": 3.0}  # Hermes edits a skill in several writes (write_file, patch…): wait for calm
SWEEP_S = 3600


def _skill_of(path: Path) -> str | None:
    """The Hermes skill a changed path belongs to (nearest parent with a SKILL.md; dot folders ignored)."""
    try:
        rel = path.relative_to(HERMES)
    except ValueError:
        return None
    if not rel.parts or rel.parts[0].startswith("."):
        return None
    for parent in [path] + list(path.parents):
        if parent == HERMES:
            break
        if (parent / "SKILL.md").exists():
            return parent.name
    return None


def react(hermes_names: set[str], drafts: bool) -> dict:
    out = {}
    if hermes_names:
        out["sync"] = {k: (v if isinstance(v, int) else v) for k, v in hermes_sync.sync(names=hermes_names).items()
                       if v}
    out["drafts"] = curation.run(apply=True, only={"drafts"})["summary"]["done"]
    out["cards"] = cards.refresh([s for s in store.iter_skills()])
    out["catalog"] = jobs.catalog()
    registry.ledger("watch", "react", None, None, {"hermes": sorted(hermes_names), "drafts": drafts, "result": out})
    return out


def main() -> int:
    from watchfiles import watch
    store.DRAFTS.mkdir(exist_ok=True)
    pending: dict[tuple, float] = {}
    lock = threading.Lock()

    def listen():
        for changes in watch(HERMES, store.DRAFTS, debounce=1500, step=200, recursive=True):
            now = time.monotonic()
            with lock:
                for _, p in changes:
                    p = Path(p)
                    if store.DRAFTS in p.parents or p == store.DRAFTS:
                        pending[("drafts",)] = now
                    elif (name := _skill_of(p)):
                        pending[("hermes", name)] = now

    threading.Thread(target=listen, daemon=True).start()
    last_sweep = time.monotonic()
    while True:
        time.sleep(2)
        now = time.monotonic()
        with lock:
            due = [k for k, t in pending.items() if now - t >= SETTLE[k[0]]]
            for k in due:
                pending.pop(k)
        try:
            if due:
                react({k[1] for k in due if k[0] == "hermes"}, any(k[0] == "drafts" for k in due))
                with lock:  # our own draft moves fired events while we worked: they are already handled
                    pending.pop(("drafts",), None)
            if now - last_sweep > SWEEP_S:
                jobs.quick()
                last_sweep = now
        except Exception as e:  # the daemon survives; the hourly sweep retries
            try:
                registry.ledger("watch", "error", None, None, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
