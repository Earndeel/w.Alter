#!/usr/bin/env python3
"""Compatibility entry point: PostgreSQL quarantine, no Qdrant and no deletion.
Default is dry-run. The supervised nightly unit invokes walter_memory.hygiene explicitly.
"""
import subprocess,sys
cmd=['/usr/local/bin/walter-python','-m','walter_memory.hygiene','--kind','ephemeral']
if '--apply' in sys.argv and '--dry-run' not in sys.argv:cmd.append('--apply')
raise SystemExit(subprocess.run(cmd,cwd='/opt/walter-memory').returncode)
