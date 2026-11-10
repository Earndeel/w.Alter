"""E9 move tool: a module and an installed environment moved, verified and rolled back in a scratch tree."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_platform import move  # noqa: E402


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root = tmp_path / 'walter'
    mod = root / 'colab'
    (mod / 'bin').mkdir(parents=True)
    (mod / 'contracts').mkdir()
    (mod / 'contracts' / 'colab.json').write_text(json.dumps({'id': 'colab', 'services': []}))
    (mod / 'README.md').write_text(f'Lives in {mod}; legacy {tmp_path}/opt/walter-colab/run.py; not {mod}-old\n')
    (mod / 'tests').mkdir()
    (mod / 'tests' / 'test_x.py').write_text(f'P = "{mod}"\n')
    subprocess.run(['git', 'init', '-q', str(mod)], check=True)
    subprocess.run(['git', '-C', str(mod), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(mod), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'x'], check=True)
    other = root / 'skills'
    other.mkdir()
    (other / 'SKILL.md').write_text(f'run {mod}/bin/go\n')
    (root / 'docs').mkdir()
    (root / 'docs' / 'DECISIONS.md').write_text(f'history: {mod}\n')
    (tmp_path / 'opt').mkdir()
    os.symlink(str(mod), tmp_path / 'opt' / 'walter-colab')
    (tmp_path / 'bin').mkdir()
    os.symlink(str(mod / 'bin'), tmp_path / 'bin' / 'walter-colab')
    units = tmp_path / 'units'
    units.mkdir()
    (units / 'x.service').write_text(f'[Service]\nExecStart={tmp_path}/opt/walter-colab/bin/go\n')
    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'schema_version': 1, 'modules': [
        {'id': 'colab', 'target': 'colab', 'legacy': f'{tmp_path}/opt/walter-colab', 'manifest': 'contracts/colab.json',
         'vision_target': 'capabilities/colab'}]}))
    monkeypatch.setenv('WALTER_ROOT', str(root))
    return tmp_path, root, catalog


def _move(tmp_path, catalog):
    return move.Move('colab', catalog=catalog, reference_roots=(str(tmp_path / 'units'),),
                     link_roots=((str(tmp_path / 'opt'), 1), (str(tmp_path / 'bin'), 1)))


def test_move_apply_verify_rollback(tree):
    tmp_path, root, catalog = tree
    m = _move(tmp_path, catalog)
    plan = m.plan()
    assert plan['ok'], plan['problems']
    assert str(root / 'skills' / 'SKILL.md') in plan['rewrite']
    assert str(root / 'docs' / 'DECISIONS.md') in plan['report_only']
    assert str(root / 'colab' / 'tests' / 'test_x.py') in plan['report_only']

    man = m.apply(tmp_path / 'backup', systemd=False)
    new = root / 'capabilities' / 'colab'
    assert new.is_dir() and (root / 'colab').is_symlink()
    assert os.readlink(tmp_path / 'opt' / 'walter-colab') == str(new)
    assert os.readlink(tmp_path / 'bin' / 'walter-colab') == str(new / 'bin')
    readme = (new / 'README.md').read_text()
    assert f'Lives in {new};' in readme and f'legacy {new}/run.py' in readme and f'not {root}/colab-old' in readme
    assert (root / 'skills' / 'SKILL.md').read_text() == f'run {new}/bin/go\n'
    assert str(new) in (tmp_path / 'units' / 'x.service').read_text()
    assert (root / 'docs' / 'DECISIONS.md').read_text() == f'history: {root}/colab\n'   # history untouched
    entry = json.loads(catalog.read_text())['modules'][0]
    assert entry['target'] == 'capabilities/colab' and entry['compat_links'] == [str(root / 'colab')]
    assert (new / '.git').is_dir()

    check = move.Move.from_manifest(man, reference_roots=(str(tmp_path / 'units'),)).verify(man)
    assert check['ok'], check

    back = move.rollback(tmp_path / 'backup', systemd=False)
    assert back['ok']
    assert (root / 'colab').is_dir() and not (root / 'colab').is_symlink() and not new.exists()
    assert os.readlink(tmp_path / 'opt' / 'walter-colab') == str(root / 'colab')
    assert (root / 'skills' / 'SKILL.md').read_text() == f'run {root}/colab/bin/go\n'
    assert json.loads(catalog.read_text())['modules'][0]['target'] == 'colab'


def test_move_refuses_twice(tree):
    tmp_path, root, catalog = tree
    _move(tmp_path, catalog).apply(tmp_path / 'b1', systemd=False)
    with pytest.raises((RuntimeError, ValueError)):
        move.Move('colab', 'capabilities/colab', catalog=catalog).apply(tmp_path / 'b2', systemd=False)


def test_env_relocation_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv('WALTER_ROOT', str(tmp_path / 'walter'))
    mod = tmp_path / 'walter' / 'router'
    env = mod / 'venv'
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(env)], check=True)
    subprocess.run(['git', 'init', '-q', str(mod)], check=True)
    (mod / '.gitignore').write_text('venv/\n')
    site = next(env.glob('lib/python*/site-packages'))
    (site / 'mods.pth').write_text(f'{tmp_path}/walter/router\n')
    (env / 'bin' / 'tool').write_text(f'#!{env}/bin/python3\nprint(1)\n')
    monkeypatch.setattr(move.paths, 'CATALOG', tmp_path / 'catalog.json')
    (tmp_path / 'catalog.json').write_text(json.dumps({'schema_version': 1, 'modules': []}))
    dest = tmp_path / 'services' / 'python' / 'router'
    man = move.env_apply(env, dest, tmp_path / 'backup')
    assert env.is_symlink() and dest.is_dir()
    assert (dest / 'bin' / 'tool').read_text().startswith(f'#!{dest}/bin/python3')
    assert (dest / 'pyvenv.cfg').read_text().count(str(env)) == 0
    assert (site.parent.parent.parent.name == 'venv')
    assert next(dest.glob('lib/python*/site-packages/mods.pth')).read_text() == f'{tmp_path}/walter/router\n'
    assert subprocess.run(['git', '-C', str(mod), 'check-ignore', '-q', 'venv']).returncode == 0
    assert move.env_verify(man)['ok']
    assert move.env_rollback(tmp_path / 'backup')['ok']
    assert env.is_dir() and not env.is_symlink() and not dest.exists()
    assert (mod / '.gitignore').read_text() == 'venv/\n'
    assert (env / 'bin' / 'tool').read_text().startswith(f'#!{env}/bin/python3')
