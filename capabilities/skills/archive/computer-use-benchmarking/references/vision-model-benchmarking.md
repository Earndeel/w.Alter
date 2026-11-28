# Computer Use Vision Benchmark — Reporting Template

## Test definition

- Date/time:
- Fixture path or fixture ID:
- Fixture type: screenshot / controlled app / sandbox
- Prompt:
- Expected visual markers:
- Models and exact provider routes:
- Hermes command/API flags:
- Reasoning setting:
- Fresh process or persistent session:
- Timeout:
- Image dimensions/format:

## Perception results

| Model | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Median | Mean | Min | Max | Verified |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Candidate A | | | | | | | | | | |
| Candidate B | | | | | | | | | | |

Record every run, including failures, retries, timeouts, and cold-start spikes. A run is verified only when the response contains every expected image-grounded marker.

## Action results

Use a separate controlled fixture; do not alter the user's live desktop merely to benchmark. Capture before each action and capture after each state-changing action.

| Model | Task | Correct target | Dispatch effect | Verified final state | Retries | Total seconds | Notes |
|---|---|---|---|---|---:|---:|---|
| Candidate A | | yes/no | confirmed/unverifiable/suspected_noop | yes/no | | | |
| Candidate B | | yes/no | confirmed/unverifiable/suspected_noop | yes/no | | | |

## Decision summary

- Fastest typical perception:
- Most stable tail latency:
- Best verified action accuracy:
- Safest primary for this workload:
- Fallback and timeout policy:
- What remains untested:

## Interpretation rules

- Do not compare external scores as a clean head-to-head when benchmark versions or task cohorts differ.
- Do not substitute provider token speed for end-to-end Hermes wall-clock latency.
- Do not call a vision-only fixture a full Computer Use benchmark.
- A small median advantage does not outweigh a timeout-scale tail for sensitive or irreversible actions.
