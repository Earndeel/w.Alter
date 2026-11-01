"""Curation operators — one contract: propose(ctx) → [proposal]; apply(ctx, proposal) → {status, ...}.

Every change is made in ctx.root (master or a shadow worktree), committed with its evidence, and must pass the
checks of base.validate when it rewrites content. Nothing is ever deleted: archive/ keeps everything.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .. import postes, registry, store
from . import base, signals

RETIRED = {
    "Qdrant / pg-qdrant-sync": r"\bqdrant\b|pg-qdrant",
    "hybrid-search / write-worker / write-bridge": r"hybrid[-_]search|write[-_]worker|write[-_]bridge",
    "dream-cycle": r"dream[-_]cycle",
    "jarvis-memory-gateway": r"jarvis[-_]memory[-_]gateway",
    "web call (call.walter-ai.cloud)": r"call\.walter-ai\.cloud|hermes-voice-call",
    "walter-ops remote admin": r"walter-ops\b",
}


class Archive:
    """Dormant skills: no read by any agent for N days, not needed by a real message in N days, not pinned, not an
    entry → the reserve (archive/ + `reserve: true`): still found by search and restored as soon as an agent reads it."""
    name, limit, editor = "archive", None, False

    def propose(self, ctx: base.Context) -> list[dict]:
        sig, out = ctx.sig, []
        for s in ctx.skills().values():
            u = sig["usage"].get(s.name, {})
            idle = (signals.now() - u["last"]).days if u.get("last") else None
            age = signals.content_age_days(s)
            if (s.name not in sig["pins"] and not sig["needed"].get(s.name) and s.meta.get("kind") != "entry"
                    and age >= ctx.cfg["archive_after_days"]
                    and (idle is None or idle >= ctx.cfg["archive_after_days"])):
                out.append({"skill": s.name, "idle_days": idle, "content_age_days": age,
                            "reason": "never read by any agent" if idle is None else f"not read for {idle} days"})
        return out

    def apply(self, ctx: base.Context, p: dict) -> dict:
        s = ctx.skills().get(p["skill"])
        if not s:
            return {"status": "skipped"}
        base.archive(ctx.root, s, p["reason"], {"reserve": True})
        c = ctx.commit(f"curator: reserve {s.name} ({p['reason']}; not needed by a real message lately)", "archive",
                       s.name, p)
        return {"status": "done", "commit": c}


class Links:
    """References to archived skills → their direct, specific successor (never a catch-all umbrella)."""
    name, limit, editor = "fix_refs", None, False

    def propose(self, ctx: base.Context) -> list[dict]:
        archived = {s.name for s in store.iter_skills(include_archived=True, root=ctx.root) if s.state == "archived"}
        succ, active, out = ctx.sig["successors"], set(ctx.skills()), []
        for s in ctx.skills().values():
            if s.meta.get("owner") == "upstream":
                continue
            blob = "\n".join(p.read_text(errors="replace") for p in s.path.rglob("*.md"))
            refs = {n for n in archived if len(n) > 6 and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", blob)}
            fix = {r: succ[r] for r in refs if succ.get(r) in active}
            if fix:
                out.append({"skill": s.name, "replace": fix, "unresolved": sorted(refs - set(fix))})
        return out

    def apply(self, ctx: base.Context, p: dict) -> dict:
        s = ctx.skills().get(p["skill"])
        for path in s.path.rglob("*.md"):
            t = path.read_text(errors="replace")
            new = t
            for old, succ in p["replace"].items():
                new = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", succ, new)
            if new != t:
                path.write_text(new)
        c = ctx.commit(f"curator: {s.name}: references to archived skills → {p['replace']}", "fix_refs", s.name, p)
        return {"status": "done" if c else "skipped", "commit": c}


class Split:
    """SKILL.md too long: the editor only PLANS which sections move verbatim to references/ (code moves the bytes)."""
    name, limit, editor = "split", "max_splits", True

    def propose(self, ctx: base.Context) -> list[dict]:
        out = [{"skill": s.name, "chars": len(s.body)} for s in ctx.skills().values()
               if len(s.body) > ctx.cfg["max_chars"] and s.meta.get("owner") != "upstream"
               and s.name not in ctx.sig["cool"]]
        return sorted(out, key=lambda x: -x["chars"])

    def apply(self, ctx: base.Context, p: dict) -> dict:
        s = ctx.skills()[p["skill"]]
        fm, intro, secs = base.sections(s.body)
        if len(secs) < 3:
            return {"status": "skipped", "reason": "fewer than 3 sections"}
        existing = sorted(str(f.relative_to(s.path)) for f in (s.path / "references").rglob("*") if f.is_file()) \
            if (s.path / "references").exists() else []
        toc = "\n".join(f"{i}. {h} ({len(t)} chars): {t[len(h):len(h) + 200].strip()!r}" for i, (h, t) in enumerate(secs))
        plan, _ = postes.ask_json("editor", (
            f"W.Alter skill `{s.name}` is {len(s.body)} chars; every load costs that many tokens. Plan a split. The "
            "sections below will be MOVED VERBATIM by a script — you do not rewrite them. Decide which stay in SKILL.md "
            "(rules needed on every use) and which move to which references/<topic>.md file (2–8 files). Write `core`: "
            "<= 3000 chars of always-on rules, each QUOTED or minimally shortened from a sentence of the text (no "
            "inference, no new rule). Also give a one-line `map` entry for EVERY reference file, including the existing "
            f"ones: {existing or 'none'}. Return JSON only: "
            '{"core": "...", "keep": [indexes], "moves": {"references/<file>.md": [indexes]}, '
            '"map": {"references/<file>.md": "when to read it"}}\n\nSections:\n' + toc +
            f"\n\nFull skill for context:\n{s.body[:60000]}"), require="moves")
        if not plan or not isinstance(plan.get("moves"), dict):
            return {"status": "rejected", "reason": "no plan"}
        keep = {int(i) for i in plan.get("keep", []) if str(i).isdigit()}
        moved: dict[str, list[int]] = {}
        for f, idx in plan["moves"].items():
            f = "references/" + re.sub(r"[^a-z0-9_.-]", "-", Path(f).name.lower())
            moved[f if f.endswith(".md") else f + ".md"] = [int(i) for i in idx if str(i).isdigit()
                                                           and int(i) < len(secs) and int(i) not in keep]
        keep |= set(range(len(secs))) - keep - {i for v in moved.values() for i in v}  # forgotten → stays inline
        refs = {f: "\n".join(secs[i][1].rstrip() + "\n" for i in sorted(ix)) for f, ix in moved.items() if ix}
        for f in list(refs):
            if (s.path / f).exists():  # never overwrite an existing reference: append
                refs[f] = (s.path / f).read_text(errors="replace").rstrip() + "\n\n" + refs[f]
        mapping = "\n".join(f"- `{f}` — {plan.get('map', {}).get(f, 'details')}" for f in sorted(set(refs) | set(existing)))
        res = {"skill_md": fm + intro.rstrip() + "\n\n## Always-on rules\n\n" + plan.get("core", "").strip() + "\n\n"
               + "".join(secs[i][1].rstrip() + "\n\n" for i in sorted(keep))
               + "## References (read with skill_read(name, file_path=...))\n\n" + mapping + "\n",
               "references": refs, "added_text": plan.get("core", "")}
        v = base.validate(ctx, "split", [s], s, res)
        if not v["accepted"]:
            return {"status": "rejected", **v}
        base.write_files(s.path, res)
        c = ctx.commit(f"curator: split {s.name} ({p['chars']} chars → SKILL.md + references)", "split", s.name, p | v)
        return {"status": "done", "commit": c, **v}


class Merge:
    """Near-duplicates → filing merge: the secondary skill is copied byte-exact into references/merged-<name>/; the
    editor writes only the description and an 'also covers' section (judged), then retrieval must not degrade."""
    name, limit, editor = "merge", "max_merges", True

    def propose(self, ctx: base.Context) -> list[dict]:
        sig, act, out = ctx.sig, ctx.sig["active"], []
        sim = sig["sim"]
        for i in range(len(act)):
            for j in range(i + 1, len(act)):
                a, b = act[i], act[j]
                if sim[i, j] < ctx.cfg["dup_cosine"] or "upstream" in (a.meta.get("owner"), b.meta.get("owner")) \
                        or {a.name, b.name} & (sig["cool"] | sig["pins"]) or {"workflow", "entry"} & {a.meta.get("kind"), b.meta.get("kind")}:
                    continue
                out.append({"a": a.name, "b": b.name, "cosine": round(float(sim[i, j]), 3),
                            "reads_60d": [sig["usage"].get(a.name, {}).get("n60", 0),
                                          sig["usage"].get(b.name, {}).get("n60", 0)]})
        return sorted(out, key=lambda x: -x["cosine"])

    def apply(self, ctx: base.Context, p: dict) -> dict:
        sk = ctx.skills()
        if p["a"] not in sk or p["b"] not in sk:
            return {"status": "skipped", "reason": "already changed in this run"}
        keep, gone = (sk[p["a"]], sk[p["b"]]) if p["reads_60d"][0] >= p["reads_60d"][1] else (sk[p["b"]], sk[p["a"]])
        files = [f"references/merged-{gone.name}/{f.relative_to(gone.path)}" for f in sorted(gone.path.rglob("*"))
                 if f.is_file() and f.name not in ("SKILL.md", store.SIDECAR)]
        obj, _ = postes.ask_json("editor", (
            f"W.Alter skills `{keep.name}` (kept) and `{gone.name}` look similar. If they do NOT cover the same job "
            f'(e.g. different providers, tools or services), answer only {{"skip": "<reason>"}}. Otherwise `{gone.name}` '
            f"will be copied VERBATIM into references/merged-{gone.name}/ ({gone.name}.md + {files or 'no other file'}). "
            f"Write only: `description` (one line starting with \"Use when\", both trigger classes) and `section` "
            f"('## Also covers ({gone.name})', <= 1500 chars: when to read references/merged-{gone.name}/{gone.name}.md, "
            "rules that differ, exact paths above) — only facts from the sources. "
            'Return JSON only: {"description": "...", "section": "..."}\n\n'
            f"{base.bundle(keep, 30000)}\n\n{base.bundle(gone, 30000)}"))
        if not obj or obj.get("skip"):
            return {"status": "rejected", "reason": f"editor: {(obj or {}).get('skip', 'no answer')}"[:300]}
        fm, intro, secs = base.sections(keep.body)
        desc = (obj.get("description") or "").replace("\n", " ").strip()
        if fm and desc:
            fm = re.sub(r"(?m)^description:.*(\n(?:[ \t]+.*\n?)*)?", "description: " + json.dumps(desc, ensure_ascii=False)
                        + "\n", fm, count=1)
        res = {"skill_md": fm + intro + "".join(t for _, t in secs).rstrip() + "\n\n" + (obj.get("section") or "").strip() + "\n",
               "references": {f"references/merged-{gone.name}/{gone.name}.md": gone.body},
               "copy_dir": [str(gone.path), f"references/merged-{gone.name}"],
               "added_text": desc + "\n" + (obj.get("section") or "")}
        v = base.validate(ctx, "merge", [keep, gone], keep, res)
        card = v.pop("card", None)
        if not v["accepted"]:
            return {"status": "rejected", **v}
        base.write_files(keep.path, res)
        base.archive(ctx.root, gone, f"merged into {keep.name}", {"absorbed_into": keep.name})
        if card and ctx.mode == "active":
            registry.put_card(keep.name, store.tree_hash(keep.path), card, "editor-merge", "card-v1")
        c = ctx.commit(f"curator: merge {gone.name} into {keep.name} (lossless, judged, retrieval kept)", "merge",
                       keep.name, p | v)
        return {"status": "done", "commit": c, **v}


class Workflow:
    """Chains of specific skills that real sessions repeat → a workflow skill that ORCHESTRATES them (no absorption)."""
    name, limit, editor = "workflow", "max_workflows", True

    def propose(self, ctx: base.Context) -> list[dict]:
        pos = {s.name: i for i, s in enumerate(ctx.sig["active"])}
        # A chain already covered by a workflow, active or archived, is never written again (until 2026-11-01 the
        # same three steps came back every night under a new name).
        known = {frozenset(s.meta.get("requires") or []) for s in store.iter_skills(include_archived=True, root=ctx.root)
                 if (s.meta.get("kind") == "workflow" or s.meta.get("absorbed_into")) and s.meta.get("requires")}
        out = []
        for w in signals.workflow_chains(ctx.aliases, set(pos), ctx.cfg):
            if frozenset(w["steps"]) in known:
                continue
            ix = [pos[n] for n in w["steps"]]
            top = max(float(ctx.sig["sim"][i, j]) for i in ix for j in ix if i != j)
            if top < ctx.cfg["workflow_max_step_cosine"]:  # too similar = variants of one tool, not a chain
                out.append(w | {"max_step_cosine": round(top, 3)})
        return out

    def apply(self, ctx: base.Context, p: dict) -> dict:
        sk = ctx.skills()
        steps = [sk[n] for n in p["steps"] if n in sk]
        if len(steps) < 2:
            return {"status": "skipped"}
        lines = "\n".join(f"- {s.name}: {(ctx.cards.get(s.name) or {}).get('summary') or s.description}" for s in steps)
        obj, _ = postes.ask_json("editor", (
            f"Real sessions repeatedly chain these W.Alter skills in this order ({p['sessions']} sessions):\n{lines}\n\n"
            "Write ONE workflow skill that orchestrates them WITHOUT copying their content: when the chain applies, "
            "the order, what each step hands to the next, the checks between steps, and 'load <sub-skill> with "
            "skill_read' at each step. Frontmatter: name, description (Use when …), `type: workflow`, "
            '`requires: [<sub-skills>]`. Return JSON only: {"name": "<kebab-case>", "skill_md": "<full SKILL.md>"}\n\n'
            + "\n\n".join(base.bundle(s, 15000) for s in steps)), require="skill_md")
        if not obj:
            return {"status": "rejected", "reason": "editor returned nothing"}
        name = re.sub(r"[^a-z0-9-]", "-", str(obj.get("name", "")).lower()).strip("-")
        missing = [s.name for s in steps if s.name not in obj["skill_md"]]
        # No model judge (2026-10-26, Monsieur): every step named, workflow type, free name.
        if missing or "type: workflow" not in obj["skill_md"] or not name or name in sk or store.find(name):
            return {"status": "rejected", "name": name, "missing_steps": missing}
        dst = ctx.root / "skills" / (steps[0].domain or "workflows") / name  # lives in the domain of its first step
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "SKILL.md").write_text(obj["skill_md"].rstrip() + "\n")
        store.write_sidecar(dst, {"origin": "walter-curator", "owner": "walter", "kind": "workflow",
                                  "requires": [s.name for s in steps], "created_at": signals.now().isoformat()})
        c = ctx.commit(f"curator: workflow {name} = {' → '.join(p['steps'])}", "workflow", name, p)
        return {"status": "done", "name": name, "commit": c}


def issues_body(verdict: dict | None) -> str:
    """Every remark of the judge, in full, for the commit body (the subject line is cut at 150 characters)."""
    issues = (verdict or {}).get("issues") or []
    return ("\n\nJudge:\n" + "\n".join(f"- {i}" for i in issues)) if issues else ""


class Drafts:
    """Agents' proposals (write door) and Hermes' own changes → live at once, no model judge (git keeps the trace)."""
    name, limit, editor = "drafts", None, False

    def propose(self, ctx: base.Context) -> list[dict]:
        d = ctx.root / "drafts"
        return [{"draft": p.name, **store.read_sidecar(p)} for p in sorted(d.iterdir()) if (p / "SKILL.md").exists()] \
            if d.exists() else []

    def apply(self, ctx: base.Context, p: dict) -> dict:
        d, kind, target = ctx.root / "drafts" / p["draft"], p.get("kind"), p.get("target")
        if kind == "hermes_update":
            return {"status": "skipped", "reason": "Hermes changed a skill Walter also changed: manual merge"}
        # No model judge on drafts (2026-10-26, Monsieur: "beaucoup trop strict inutilement"). The write door already
        # refuses secrets, malformed frontmatter, oversize text and paths outside the skill; here only the target is
        # checked. A wrong change is undone with git (every acceptance is its own commit).
        sk = ctx.skills()
        if kind == "new":
            verdict = {"ok": target not in sk and not (ctx.root / "archive" / target).exists(),
                       "issues": [f"{target} already exists"] if target in sk or (ctx.root / "archive" / target).exists()
                       else []}
        elif kind in ("patch", "hermes_patch") and target in sk:
            verdict = {"ok": True, "issues": []}
        else:
            verdict = {"ok": False, "issues": [f"{target} is not an active skill"]}
        if verdict and verdict.get("ok"):
            if kind == "new":
                dst = ctx.root / "skills" / (p.get("domain") or "learned") / target
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(d), str(dst))
                side = {"origin": "hermes-agent" if p.get("runtime") == "hermes" else "agent-proposal", "owner": "walter",
                        "proposed_by": p.get("runtime"), "reason": p.get("reason"), "hermes": p.get("hermes"),
                        "review_notes": verdict.get("minor")}
                store.write_sidecar(dst, {k: v for k, v in side.items() if v} | {"store_sha": store.tree_hash(dst)})
            elif kind == "patch":
                shutil.copyfile(d / p.get("changed", "SKILL.md"), sk[target].path / p.get("changed", "SKILL.md"))
                shutil.rmtree(d)
            else:  # hermes_patch: Hermes' new version replaces ours (we never edited it)
                meta = sk[target].meta
                shutil.rmtree(sk[target].path)
                shutil.move(str(d), str(sk[target].path))
                hermes = (meta.get("hermes") or {}) | (p.get("hermes") or {})
                hermes.pop("pending_sha", None)
                store.write_sidecar(sk[target].path, meta | {"hermes": hermes})
                store.write_sidecar(sk[target].path, meta | {"hermes": hermes, "store_sha": store.tree_hash(sk[target].path)})
            c = ctx.commit(f"curator: accept {kind} {target} ({str(p.get('reason'))[:100]})" + issues_body(verdict),
                           f"draft_{kind}", target,
                           {"draft": p["draft"], "judge": verdict}, paths=["skills", "drafts"])
            return {"status": "done", "commit": c, "judge": verdict}
        shutil.rmtree(d)
        shown = (verdict or {}).get("blocking") or (verdict or {}).get("issues") or ["no verdict"]
        c = ctx.commit(f"curator: reject {kind} {target} ({'; '.join(shown)[:150]})" + issues_body(verdict),
                       f"draft_{kind}_rejected", target, {"draft": p["draft"], "judge": verdict}, paths=["drafts"])
        return {"status": "rejected", "commit": c, "judge": verdict}


class Organize:
    """Domains that help the agent: the editor proposes a taxonomy (~20 domains) and assigns every walter-owned skill;
    folders move (git mv), names never change — retrieval, links and Hermes sync are unaffected."""
    name, limit, editor = "organize", "max_moves", True

    def propose(self, ctx: base.Context) -> list[dict]:
        sk = ctx.skills()
        sizes = {}
        for s in sk.values():
            d = (s.domain or "misc").split("/")[0]
            sizes[d] = sizes.get(d, 0) + 1
        if max(sizes.values(), default=0) <= ctx.cfg["max_domain_size"] and "misc" not in sizes:
            return []
        lines = "\n".join(f"{s.name} [{(s.domain or 'misc').split('/')[0]}]: {(ctx.cards.get(s.name) or {}).get('summary') or s.description}"[:220]
                          for s in sorted(sk.values(), key=lambda x: x.name))
        obj, _ = postes.ask_json("editor", (
            "Organise W.Alter's skill library into 15–25 domains that an agent would recognise at a glance (by "
            "service/activity, e.g. 'hermes-runtime', 'video-production', 'web-browsing-auth', 'messaging', "
            f"'model-routing'…), each with at most {ctx.cfg['max_domain_size']} skills; no 'misc'. Keep a skill's "
            "current domain when it already fits. Return JSON only: {\"domains\": {\"<domain>\": \"one-line scope\"}, "
            "\"assign\": {\"<skill name>\": \"<domain>\"}}\n\nSkills [current domain]: summary\n" + lines),
            require="assign", timeout=1200)
        if not obj:
            return []
        out = []
        for name, dom in (obj.get("assign") or {}).items():
            dom = re.sub(r"[^a-z0-9-]", "-", str(dom).lower()).strip("-")
            s = sk.get(name)
            if s and dom and s.meta.get("owner") != "upstream" and (s.domain or "misc").split("/")[0] != dom:
                out.append({"skill": name, "from": s.domain or "misc", "to": dom,
                            "scope": (obj.get("domains") or {}).get(dom, "")})
        return out

    def apply(self, ctx: base.Context, p: dict) -> dict:
        s = ctx.skills().get(p["skill"])
        if not s:
            return {"status": "skipped"}
        dst = ctx.root / "skills" / p["to"] / s.name
        if dst.exists():
            return {"status": "skipped", "reason": "target exists"}
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s.path), str(dst))
        c = ctx.commit(f"curator: organise {s.name}: {p['from']} → {p['to']}", "organize", s.name, p)
        return {"status": "done", "commit": c}


class Flags:
    """Report only: mentions of retired services, Hermes conflicts."""
    name, limit, editor = "flags", None, False

    def propose(self, ctx: base.Context) -> list[dict]:
        out = []
        for s in ctx.skills().values():
            blob = "\n".join(p.read_text(errors="replace") for p in s.path.rglob("*.md"))
            hits = [label for label, rx in RETIRED.items() if re.search(rx, blob, re.I)]
            if hits:
                out.append({"skill": s.name, "retired_services": hits})
        return out

    def apply(self, ctx: base.Context, p: dict) -> dict:
        return {"status": "reported"}


OPERATORS = [Drafts(), Archive(), Links(), Merge(), Split(), Workflow(), Organize(), Flags()]
