"""Scenarios drive the live engine as the test account (`e2e`). A request they send can open a durable objective
(Run Plane) like any owner request: this closes those objectives when a scenario ends, so a test never stays in the
owner's task list nor is proposed to a real conversation.

Closed = `cancelled` with a note, through Walter Memory's own command (never deleted). Selected: objectives still
open or suspended whose owner-channel attempts ALL came from a test-account engine session (`<interface>/e2e/…`) and
none of which is still running. An objective the owner opened is never touched.

    walter-python /walter/core/scenarios/e2e_objectives.py        # also called at the end of each scenario
"""
import json
import subprocess

ACCOUNT = "e2e"


def close(note: str = "objectif de test (scénario)") -> list[str]:
    """The task ids closed. Never raises: a scenario's verdict does not depend on its cleanup."""
    try:
        from walter_memory import db
        with db.connect() as c:
            rows = c.execute("""
                select t.task_id::text task_id from runs.tasks t
                where t.kind = 'objective' and t.status in ('open', 'suspended')
                  and exists (select 1 from runs.task_runs tr join runs.runs r using (run_id)
                              where tr.task_id = t.task_id and coalesce(r.origin->>'channel', 'owner') = 'owner')
                  and not exists (select 1 from runs.task_runs tr join runs.runs r using (run_id)
                                  where tr.task_id = t.task_id
                                    and (r.status = 'open'
                                         or (coalesce(r.origin->>'channel', 'owner') = 'owner'
                                             and split_part(coalesce(r.origin->>'engine_session', ''), '/', 2) <> %s)))
                """, (ACCOUNT,)).fetchall()
        done = []
        for r in rows:
            p = subprocess.run(["walter-memory", "tasks", "update", r["task_id"]], text=True, capture_output=True,
                               timeout=60, input=json.dumps({"status": "cancelled", "note": note}))
            if p.returncode == 0:
                done.append(r["task_id"])
        return done
    except Exception:  # noqa: BLE001
        return []


if __name__ == "__main__":
    print(json.dumps({"closed": close()}))
