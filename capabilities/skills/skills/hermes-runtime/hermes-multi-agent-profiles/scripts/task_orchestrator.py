#!/usr/bin/env python3
"""
Héphaistos Task Orchestrator — Autonomous execution loop.

Plans subtasks, routes to best model, executes, evaluates, escalates on failure,
iterates until satisfied, updates EVOLUTION.md, returns structured report.

Usage:
  python3 ~/.hermes/scripts/task_orchestrator.py \
    --task "Fix webhook Stripe + add retry + tests" \
    --profile hephaestus \
    --max-iterations 3 \
    --json
"""
import argparse, json, os, re, subprocess, sys, yaml
from datetime import datetime
from pathlib import Path

AGENTS_DIR = Path.home() / ".hermes" / "agents"

ROUTES = {
    "backend": {"model": "claude-opus-4-7", "provider": "kie-claude",
                "keywords": ["api", "endpoint", "database", "stripe", "webhook", "auth", "worker", "migration", "sql", "server"]},
    "frontend": {"model": "kimi-k2.6", "provider": "opencode-go",
                 "keywords": ["ui", "css", "html", "react", "tailwind", "gsap", "animation", "design", "layout", "component"]},
    "debug": {"model": "mimo-v2.5-pro", "provider": "xiaomi",
              "keywords": ["bug", "error", "traceback", "exception", "fix", "broken", "fail", "crash"]},
    "review": {"model": "claude-sonnet-4.5", "provider": "nous",
               "keywords": ["review", "audit", "security", "check", "validate", "verify"]},
    "quick": {"model": "deepseek/deepseek-v4-flash", "provider": "openrouter",
              "keywords": ["rename", "format", "typo", "lint", "cleanup", "comment"]},
}
DEFAULT_ROUTE = {"model": "mimo-v2.5-pro", "provider": "xiaomi"}
ESCALATION_CHAIN = [{"model": "claude-opus-4-7", "provider": "kie-claude"},
                     {"model": "claude-sonnet-4.5", "provider": "nous"}]

def route_subtask(desc):
    words = set(re.findall(r'\w+', desc.lower()))
    best, best_score = None, 0
    for name, cfg in ROUTES.items():
        score = sum(1 for kw in cfg["keywords"] if kw in words)
        if score > best_score:
            best_score = score
            best = {"route": name, "model": cfg["model"], "provider": cfg["provider"], "score": score}
    return best if best and best["score"] > 0 else {"route": "default", **DEFAULT_ROUTE, "score": 0}

def plan_subtasks(task):
    parts = re.split(r'\s*[+&]\s*|\s+et\s+|\s+then\s+|\s+ensuite\s+|\d+[.)]\s*', task)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]
    if len(parts) <= 1:
        r = route_subtask(task)
        return [{"id": 1, "description": task, "route": r, "status": "pending", "attempts": []}]
    return [{"id": i, "description": p, "route": route_subtask(p), "status": "pending", "attempts": []}
            for i, p in enumerate(parts, 1)]

def execute_subtask(profile, st, repo=None):
    prompt = st["description"]
    if repo: prompt = f"Working in repo: {repo}\n{prompt}"
    prompt += "\n\nAfter completing the task, verify it works. Show the verification output."
    cmd = ["hermes", "-p", profile, "chat", "-Q", "--source", "orchestrator", "--skills", "",
           "-m", st["route"]["model"], "--provider", st["route"]["provider"], "-q", prompt]
    start = datetime.now()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env={**os.environ, "HERMES_NO_BANNER": "1"})
        elapsed = (datetime.now() - start).total_seconds()
        return {"success": r.returncode == 0 and len(r.stdout.strip()) > 0, "output": r.stdout.strip(),
                "error": r.stderr.strip() if r.returncode != 0 else "", "model": st["route"]["model"],
                "provider": st["route"]["provider"], "elapsed": round(elapsed, 1), "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Timeout (120s)", "model": st["route"]["model"],
                "provider": st["route"]["provider"], "elapsed": 120, "returncode": -1}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e), "model": st["route"]["model"],
                "provider": st["route"]["provider"], "elapsed": 0, "returncode": -1}

def escalate(st):
    models_tried = {a["model"] for a in st.get("attempts", [])}
    for esc in ESCALATION_CHAIN:
        if esc["model"] not in models_tried: return esc
    return None

def evaluate_result(output):
    if not output: return {"verdict": "fail", "reason": "empty output"}
    lo = output.lower()
    pos = sum(1 for p in ["success", "pass", "✅", "done", "complete", "verified", "ok", "created", "fixed"] if p in lo)
    neg = sum(1 for n in ["error", "fail", "❌", "exception", "traceback", "broken", "timeout", "denied"] if n in lo)
    if bool(re.search(r'all\s*(tests?\s*)?pass', lo)): return {"verdict": "pass", "reason": "all pass"}
    if neg > pos: return {"verdict": "fail", "reason": f"neg({neg}) > pos({pos})"}
    if pos > 0 and neg == 0: return {"verdict": "pass", "reason": "positive signals"}
    return {"verdict": "uncertain", "reason": "mixed signals"}

def update_evolution(profile, task, subtasks, verdict):
    path = AGENTS_DIR / profile / "EVOLUTION.md"
    if not path.exists(): return
    entry = f"\n### {datetime.now().strftime('%Y-%m-%d %H:%M')} — Task: {task}\n"
    entry += f"- **Verdict**: {'✅' if verdict == 'pass' else '⚠️' if verdict == 'uncertain' else '❌'} {verdict}\n"
    entry += f"- **Subtasks**: {len(subtasks)}\n"
    for st in subtasks:
        r = st.get("result", {})
        entry += f"  - #{st['id']}: {st['description'][:60]} → {'✅' if r.get('success') else '❌'} ({r.get('model','?')}, {r.get('elapsed','?')}s)\n"
    entry += f"- **Total time**: {sum(st.get('result',{}).get('elapsed',0) for st in subtasks):.0f}s\n"
    with open(path, 'a') as f: f.write(entry)

def orchestrate(task, profile, repo=None, max_iterations=3):
    print(f"\n{'='*60}\nHÉPHAISTOS ORCHESTRATOR\nTask: {task}\nProfile: {profile}\n{'='*60}\n")
    subtasks = plan_subtasks(task)
    print("📋 STEP 1: PLANNING")
    for st in subtasks:
        print(f"  #{st['id']}: {st['description'][:60]} → {st['route']['model']}")
    overall = "uncertain"
    for iteration in range(1, max_iterations + 1):
        print(f"\n🔄 ITERATION {iteration}/{max_iterations}\n{'─'*40}")
        for st in subtasks:
            if st["status"] == "pass":
                print(f"  #{st['id']}: SKIP (already passed)"); continue
            print(f"  #{st['id']}: Executing ({st['route']['model']})...")
            result = execute_subtask(profile, st, repo)
            st["attempts"].append(result); st["result"] = result
            ev = evaluate_result(result.get("output", "")); st["eval"] = ev
            if ev["verdict"] == "pass" or result["success"]:
                st["status"] = "pass"; print(f"  #{st['id']}: ✅ PASS ({result['elapsed']}s)")
            else:
                esc = escalate(st)
                if esc:
                    st["route"] = {"route": "escalated", "model": esc["model"], "provider": esc["provider"], "score": 0}
                    st["status"] = "retry"; print(f"  #{st['id']}: ❌ FAIL → Escalating to {esc['model']}")
                else:
                    st["status"] = "failed"; print(f"  #{st['id']}: ❌ FAIL (no escalation)")
        if all(st["status"] == "pass" for st in subtasks):
            print("\n✅ ALL SUBTASKS PASSED"); overall = "pass"; break
    else:
        print("\n⚠️ MAX ITERATIONS REACHED")
    update_evolution(profile, task, subtasks, overall)
    report = {"task": task, "profile": profile, "verdict": overall, "iterations": iteration,
              "subtasks": [{"id": s["id"], "description": s["description"], "status": s["status"],
                           "model": s.get("result",{}).get("model","?"), "elapsed": s.get("result",{}).get("elapsed",0),
                           "attempts": len(s.get("attempts",[]))} for s in subtasks],
              "total_time": sum(s.get("result",{}).get("elapsed",0) for s in subtasks)}
    print(f"\n{'='*60}\nREPORT\n{'='*60}")
    for sr in report["subtasks"]:
        print(f"  {'✅' if sr['status']=='pass' else '❌'} #{sr['id']}: {sr['description'][:50]} | {sr['model']} | {sr['elapsed']}s | {sr['attempts']} attempts")
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True); p.add_argument("--profile", default="hephaestus")
    p.add_argument("--repo"); p.add_argument("--max-iterations", type=int, default=3)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    report = orchestrate(args.task, args.profile, args.repo, args.max_iterations)
    if args.json: print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["verdict"] == "pass" else 1)

if __name__ == "__main__": main()
