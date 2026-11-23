---
name: browse-egress-fail-closed
description: Use when the Browse guardian reports a Chromium egress violation or when changing the default SOCKS selector's Mac-to-France failover behavior.
---

## Establish what the probe actually saw

1. On Monsieur's VM, run `cd /walter/capabilities/browse`, read `README.md` and the relevant runbook, and run `git status --short`. Inspect `guardian/check`, `network/exit-local/bin/walter-exit-local`, and `network/exit-default/bin/walter-exit-default`.
2. Run `walter-exit-local probe` and inspect its JSON, especially `violations`. A missing IP/country response is not evidence of wrong egress; see `git show e2990c6`. A successful response through Chromium's default SOCKS listener (`127.0.0.1:1083`) showing the Mac's non-France egress is a real violation. The Mac sleeping or leaving the network is normal; keep that as informational if routing fails closed.
3. Correlate the incident in UTC across `$(walter instance path)/state/guardians/incidents.jsonl`, `/var/log/walter-exit-local.log`, and `/var/log/walter-exit-default.log`. Check `walter-exit-default status` and `cat /run/walter-exit-default.json` for the current route, not the historical one. If the fallback is `freebox-fr`, use `docker inspect -f '{{.State.StartedAt}} {{.Created}}' walter-wg-freebox-fr` to compare its startup with the incident. A healthy fallback now does not disprove a wrong exit during the transition. Do not read SSH configuration or credential files to diagnose this.

## Preserve the fail-closed transition

4. Inspect `decide()` in `network/exit-default/bin/walter-exit-default`. If the Mac is no longer verified to be on its France tunnel, including when its status check stops answering, withdraw `primary` **before** any potentially blocking `walter-wg-exit up` call. Use the selector's route-change mechanism so new connections cannot use the old route and existing primary streams do not survive withdrawal. Keep the route closed until an eligible fallback is ready. Do not suppress a valid wrong-egress report to fix this race.
5. Add deterministic regression coverage in `network/exit-default/tests/test_exit_default.py`: stub fallback startup and assert that `primary` is already withdrawn when startup begins, both when the Mac has left its tunnel and when its status is unavailable. Check that the new tests fail against the old implementation and pass after the fix: `python3 -m pytest -q network/exit-default/tests/test_exit_default.py`. If the wider suite fails, reproduce the same failure against the unchanged source before classifying it as pre-existing; do not stash or discard unrelated edits. The known baseline failure in this session was reproduced with `python3 -m pytest -q runtime/test_universal_extractor.py -k test_replay_fetches` and raised `scrapling is required for the live extractor`.

## Verify the running service

6. Check `systemctl cat walter-exit-default` to confirm which executable the unit runs. Back up the touched file, then restart only the affected unit when authorized: `systemctl restart walter-exit-default`. Run `systemctl is-active walter-exit-default`, `walter-exit-default status`, `tail -n 20 /var/log/walter-exit-default.log`, and `walter-exit-local probe`. Confirm there are no violations and record whether the proxy actually returned a valid France result or was closed. An empty `violations` list with no answer does not prove working France egress. Use the regression tests to prove transition ordering without deliberately dropping the owner's live tunnel. For guardian-delegated maintenance, return the requested JSON verdict with evidence, not a user-facing recap.
