"""Non-secret deployment settings. Paths are explicit dependencies, not host imports."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / 'config/walter-secrets.toml'
INSTANCE = '@instance'


def _walter_instance(*args):
    """The active Walter instance, asked through its public interface; None when unavailable."""
    try:
        out = subprocess.run(['walter', 'instance', *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def _config_path():
    if os.environ.get('WALTER_SECRETS_CONFIG'):
        return Path(os.environ['WALTER_SECRETS_CONFIG'])
    return _walter_instance('config', 'secrets', 'walter-secrets.toml') or SHIPPED


CONFIG_PATH = _config_path()
try:
    with CONFIG_PATH.open('rb') as stream:
        CONFIG = tomllib.load(stream)
except FileNotFoundError:
    CONFIG = {}


def setting(section: str, key: str, default=None):
    return CONFIG.get(section, {}).get(key, default)


def expand(value: str | Path) -> Path:
    """Absolute, ~/... or @instance/... (the active instance)."""
    value = str(value)
    if value == INSTANCE or value.startswith(INSTANCE + '/'):
        root = _walter_instance('path')
        if root is None:
            raise RuntimeError('no active Walter instance for ' + value)
        return root / value[len(INSTANCE):].lstrip('/')
    return Path(value).expanduser()


def path(key: str, default: str | Path) -> Path:
    return expand(setting('paths', key, str(default)))


DATA_ROOT = path('legacy_data_root', Path.home() / '.hermes')
UNLOCK = path('unlock', ROOT / 'bin/bw-unlock')
SESSION = path('session', DATA_ROOT / 'vault/.bw_session_key')
VAULT_ENC = path('bootstrap_vault', DATA_ROOT / 'vault/vault.json.age')
VAULT_KEY = path('bootstrap_key', DATA_ROOT / 'vault/age-key.txt')
AUDIT = path('audit', DATA_ROOT / 'logs/walter-secrets.jsonl')
FILES = path('attachments', '/dev/shm/walter-secrets')
ENV_CONSUMERS = CONFIG.get('env_consumers', [])
# The bw CLI keeps its account database (the whole encrypted vault) under $HOME/.config, or under the *working
# directory* when HOME is unset (systemd units without HOME): a service started in another module's folder re-logged in and
# synced a full copy there (2026-11-07). Every bw call gets this one pinned location.
BW_APPDATA = path('bw_appdata', Path(os.path.expanduser('~')) / '.config/Bitwarden CLI')


def bw_env(**extra: str) -> dict:
    """Environment for a bw subprocess: the caller's, with HOME and the bw data directory pinned."""
    return {**os.environ, **extra, 'HOME': os.path.expanduser('~'), 'BITWARDENCLI_APPDATA_DIR': str(BW_APPDATA)}
