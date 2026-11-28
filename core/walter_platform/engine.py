"""`walter engine kernel`: is the installed engine kernel still the frozen one (lot E1)?

Read-only. Compares the live installation (packages, composition files, composed configuration of each profile)
with core/engine/kernel/installed.json through core/engine/kernel/verify.py. Location of the live installation:
DSH_HOME (default /opt/dsh/home, as for `walter harness ... dsh`) and its parent for the packages, or DSH_INSTALL.
No kernel installed at all (neither the packages nor the home): `installed: false`, nothing to compare — the normal
state since DSH was uninstalled on 2026-11-18 (the production engine is native; the frozen kernel is a rollback kit).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

KERNEL = Path(__file__).resolve().parent.parent / 'engine' / 'kernel'


def _verify():
    spec = importlib.util.spec_from_file_location('walter_engine_kernel_verify', KERNEL / 'verify.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def kernel(install: str | None = None, home: str | None = None) -> dict:
    home_p = Path(home or os.environ.get('DSH_HOME', '/opt/dsh/home'))
    install_p = Path(install or os.environ.get('DSH_INSTALL') or home_p.parent)
    base = {'install': str(install_p), 'home': str(home_p), 'manifest': str(KERNEL / 'installed.json')}
    if not install_p.exists() and not home_p.exists():
        return {**base, 'installed': False, 'ok': True}
    try:
        return {**base, 'installed': True, **_verify().check(install_p, home_p)}
    except OSError as exc:                       # a partial installation (home without packages…): a drift, said
        return {**base, 'installed': True, 'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
