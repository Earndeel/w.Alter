"""Non-secret deployment settings. Paths are explicit dependencies, not host imports."""
from __future__ import annotations
import os
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get('WALTER_SECRETS_CONFIG', str(ROOT / 'config/walter-secrets.toml')))
try:
    with CONFIG_PATH.open('rb') as stream:
        CONFIG = tomllib.load(stream)
except FileNotFoundError:
    CONFIG = {}


def setting(section: str, key: str, default=None):
    return CONFIG.get(section, {}).get(key, default)


def path(key: str, default: str | Path) -> Path:
    return Path(setting('paths', key, str(default))).expanduser()


DATA_ROOT = path('legacy_data_root', Path.home() / '.hermes')
UNLOCK = path('unlock', ROOT / 'bin/bw-unlock')
SESSION = path('session', DATA_ROOT / 'vault/.bw_session_key')
VAULT_ENC = path('bootstrap_vault', DATA_ROOT / 'vault/vault.json.age')
VAULT_KEY = path('bootstrap_key', DATA_ROOT / 'vault/age-key.txt')
AUDIT = path('audit', DATA_ROOT / 'logs/walter-secrets.jsonl')
FILES = path('attachments', '/dev/shm/walter-secrets')
ENV_CONSUMERS = CONFIG.get('env_consumers', [])
