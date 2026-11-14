"""Tiny CPU smoke job: run once from /content/walter-cache-store."""
import json
from pathlib import Path
import platform
import shutil

probe = Path('walter-probe.json')
output = Path('result.json')
if probe.is_symlink() or not probe.is_file() or output.exists() or output.is_symlink():
    raise ValueError('Smoke fixture requires a regular input and an absent output')
data = json.loads(probe.read_text(encoding='utf-8'))
nvidia_smi_present = shutil.which('nvidia-smi') is not None
if nvidia_smi_present:
    raise RuntimeError('CPU smoke expected no nvidia-smi; refusing to label a GPU runtime as CPU')
result = {'message': data['message'], 'machine': platform.machine(),
          'python_version': platform.python_version(), 'device': 'cpu',
          'nvidia_smi_present': nvidia_smi_present}
with output.open('x', encoding='utf-8') as handle:
    json.dump(result, handle, ensure_ascii=False)
    handle.write('\n')
