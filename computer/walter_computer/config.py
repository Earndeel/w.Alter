"""Module-owned configuration; adapter translates Hermes settings at its boundary."""
from pathlib import Path
import json
import sys
import os
import stat
from .operator import Operator
from .policy import _configured_driver_command
from .transport import DriverSession

DEFAULT_CONFIG = Path('/opt/walter-computer/config.json')


def load_config(path=DEFAULT_CONFIG):
    config = json.loads(Path(path).read_text())
    _configured_driver_command(config)  # Validate executable ownership/mode before any use.
    return config


def make_operator(config=None, *, vision_sensor=None):
    config = load_config() if config is None else config
    source = Path(config.get('device_node_python_path', '/root/walter-computer-use/src'))
    info = source.stat()
    if not source.is_absolute() or not source.is_dir() or info.st_uid not in {0, os.getuid()} or stat.S_IMODE(info.st_mode) & 0o022:
        raise PermissionError('untrusted device-node Python dependency')
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    command = _configured_driver_command(config)
    if command is None:
        raise ValueError('computer_use.walter.driver_command is required')
    return Operator(config=config, transport=DriverSession([command, 'mcp']), vision_sensor=vision_sensor)
