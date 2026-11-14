"""Module-owned configuration; adapter translates Hermes settings at its boundary."""
from pathlib import Path
import json
import sys
import os
import stat
import subprocess
from .operator import Operator
from .policy import _configured_driver_command
from .transport import DriverSession
from .vision import GatewayVisionSensor

SHIPPED_CONFIG = Path(__file__).resolve().parent.parent / 'config' / 'config.json'


def default_config_path():
    """WALTER_COMPUTER_CONFIG, else the active instance's setting (`walter instance config`), else the shipped default."""
    if os.environ.get('WALTER_COMPUTER_CONFIG'):
        return Path(os.environ['WALTER_COMPUTER_CONFIG'])
    try:
        out = subprocess.run(['walter', 'instance', 'config', 'computer', 'config.json'],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return SHIPPED_CONFIG


def load_config(path=None):
    config = json.loads(Path(path or default_config_path()).read_text())
    _configured_driver_command(config)  # Validate executable ownership/mode before any use.
    return config


def make_operator(config=None, *, vision_sensor=None):
    config = load_config() if config is None else config
    if not config.get('device_node_python_path'):
        raise ValueError('no device configured for this instance (device_node_python_path)')
    source = Path(config['device_node_python_path'])
    info = source.stat()
    if not source.is_absolute() or not source.is_dir() or info.st_uid not in {0, os.getuid()} or stat.S_IMODE(info.st_mode) & 0o022:
        raise PermissionError('untrusted device-node Python dependency')
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    command = _configured_driver_command(config)
    if command is None:
        raise ValueError('computer_use.walter.driver_command is required')
    if vision_sensor is None and config.get('vision', {}).get('enabled') is True:
        vision_sensor = GatewayVisionSensor(config['vision'])
    return Operator(config=config, transport=DriverSession([command, 'mcp']), vision_sensor=vision_sensor)
