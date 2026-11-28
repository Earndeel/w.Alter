# walter-runtime

**Role.** One Python environment for the modules that share the same dependencies (memory, logs, bus, skills,
secrets, context, core hooks). Interface: the `walter-python` command on the PATH, never the interpreter's path.
Modules with their own incompatible dependencies keep their own environment (core, llm…).

**Organisation.** `requirements.lock` (exact production versions), `requirements-dev.lock` (test tools), a rebuildable
`venv/` outside git. Adding a dependency: add it to the lock, reinstall, rerun the consumer modules' tests;
`walter-runtime sync` after moving a library module.
