---
name: walter-stale-service-recovery
description: Use when W.Alter services fail after Python library or secrets migrations, especially when logs reference retired files despite corrected code on disk, or context silently falls back to a weaker plan.
---

# Recover stale W.Alter service processes

## Recognize the failure

Long-running Python services retain imported code after source files change. A successful migration on disk does not update running processes. After retiring `/root/.hermes/.env`, old processes continued trying to read it even though `walter_memory.llm._secret` had already been migrated to Walter Secrets.

Do not recreate the retired file or restore plaintext credentials. Distinguish stale imports from a missing Secrets grant before changing configuration.

## Trace the affected turn

Use the log CLI rather than guessing database columns or connection credentials:

```sh
walter-memory logs sessions --limit 10
walter-memory logs timeline SESSION_ID --seq SEQUENCE --before 120 --after 40 --max-chars 900
walter-memory logs get SESSION_ID --seq SEQUENCE --max-chars 3000
```

Find the actual context decision and tool failure, not only the final assistant reply.

## Compare source and process age

```sh
grep -n 'def _secret\|hermes\|\.env' /walter/cognition/memory/walter_memory/llm.py
stat -c '%y %n' /walter/cognition/memory/walter_memory/llm.py
for u in walter-context-preflight walter-memory-pipeline walter-memory-gateway; do
  systemctl show "$u" -p ActiveEnterTimestamp -p ExecMainStartTimestamp
  journalctl -u "$u" --since '6 hours ago' --no-pager | grep -F 'hermes/.env'
done
```

Check preflight shadow records under `/user/Lucas/state/context/shadow/preflight-*.jsonl`. Each record's `plan` may be an object or a JSON-encoded string; decode it accordingly. Inspect `plan.decision.error` for provider failures and compare the resulting level with the task's needs. A silent L1 fallback can hide a broken decision model.

## Restart the affected dependents

After confirming that the code on disk is correct, restart the stale consumers, accounting for interruption of active work:

```sh
systemctl restart walter-context-preflight
systemctl restart walter-memory-pipeline walter-memory-gateway
sleep 6
systemctl is-active walter-context-preflight walter-memory-pipeline walter-memory-gateway
```

These three services were affected in the observed incident; do not assume they are an exhaustive dependency list for future migrations.

## Verify a real decision, not just liveness

```sh
curl -sS --max-time 30 http://127.0.0.1:8897/preflight \
  -H 'Content-Type: application/json' \
  -d '{"message":"Analyse mes échanges des dernières 48 heures et propose une réponse fondée sur leur historique.","runtime":"test","session_id":"test/stale-service-recovery"}'
```

Inspect the complete returned plan: decision errors must be absent and the plan must request the memory/context appropriate to the task. Recheck fresh shadow records and journals after the restart. `/health` only reports liveness and router-cache state; it does not prove that decision-model calls work.

Optionally run the broader memory check:

```sh
systemctl start memory-autopilot
cat /user/Lucas/logs/memory-autopilot/latest.json
```

Treat that report as supplementary. In this incident it reported 100/100 despite having missed the decision-path outage. Require a successful functional preflight replay before declaring recovery.
