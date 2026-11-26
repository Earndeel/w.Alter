# Walter Lab

**Role.** W.Alter's research and evolution space. It compares a variant with the current behaviour on the same
end-to-end scenarios as the bench (`walter-scenario`), with interleaved trials and a decision rule written before the
trials, and may conclude "change nothing". It never modifies W.Alter: a proposal goes to the module's owner or to
{{owner.address}}. It also hosts harness studies (`harnesses/`, e.g. the Unharnessed Python-kernel trial).

**Use**: `walter-lab list`, `walter-lab run <experiment> [--repeats N]`, `walter-lab history <experiment>`. An
experiment = `experiments/<name>.yaml` (Experiment v1). External code: `walter-lab sandbox run --src <approved copy>
-- <command>` (local Docker without network, filtered source, copy limits, export to a new directory);
`walter-lab sandbox probe` checks the real backend. Bench scenarios keep the host permissions; they are not isolated.
Read the README before running external code.

Reports keep the protocol (scenario, rule, order, definition and code fingerprints), never environment values.
