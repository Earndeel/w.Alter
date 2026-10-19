import io
import tarfile
from pathlib import Path
import pytest
from walter_memory.restore_drill import restore_tree,container_command,check_sqlite


def archive(tmp,entries):
    path=tmp/'fixture.tar'
    with tarfile.open(path,'w') as f:
        for name,body,link in entries:
            info=tarfile.TarInfo(name);info.mode=0o600
            if link:
                info.type=tarfile.SYMTYPE;info.linkname=link;f.addfile(info)
            else:
                data=body.encode();info.size=len(data);f.addfile(info,io.BytesIO(data))
    return path


def test_absolute_links_rebased_inside_restored_root(tmp_path):
    fixture=archive(tmp_path,[('opt/module/a.py','synthetic',None),('usr/bin/test',None,'/opt/module/a.py')])
    root=tmp_path/'restore'; result=restore_tree(fixture,root)
    assert result=={'files':1,'rebased_links':1}
    assert (root/'usr/bin/test').resolve()==root/'opt/module/a.py'
    assert (root/'opt/module/a.py').stat().st_mode & 0o777==0o600


def test_escape_and_symlink_parent_members_refused(tmp_path):
    for i,entries in enumerate([
        [('../outside','bad',None)],
        [('x',None,'../../escape')],
        [('x',None,'/elsewhere'),('x/y','bad',None)],
    ]):
        case=tmp_path/str(i);case.mkdir()
        with pytest.raises((ValueError,FileExistsError)):
            restore_tree(archive(case,entries),case/'root')
    assert not (tmp_path/'outside').exists()


def test_container_has_no_network_or_ports_or_production_mounts():
    argv=container_command('test','sha256:fixture',Path('/tmp/isolated-data'))
    assert argv[argv.index('--network')+1]=='none'
    assert argv[argv.index('--pull')+1]=='never'
    assert '--read-only' in argv and '-p' not in argv and '--privileged' not in argv
    assert argv.count('--mount')==1 and 'source=/tmp/isolated-data,' in argv[argv.index('--mount')+1]
    assert all('docker.sock' not in word and '/root/.hermes' not in word for word in argv)


def test_sqlite_counts_without_content(tmp_path):
    import sqlite3
    db=tmp_path/'state.db';c=sqlite3.connect(db)
    c.execute('create table messages(id integer, content text)');c.execute("insert into messages values(1,'synthetic')");c.commit();c.close()
    assert check_sqlite(db)=={'ok':True,'tables':1,'counts':{'messages':1}}


def test_source_validation_distinguishes_knowledge_templates_and_executable_code(tmp_path):
    from walter_memory.restore_drill import validate_sources,DrillError
    root=tmp_path/'opt/walter-skills';root.mkdir(parents=True)
    code=root/'service.py';code.write_text('valid = True\n')
    example=root/'skills/example/templates/broken.py';example.parent.mkdir(parents=True)
    example.write_text('bad = "unterminated\n')
    report=validate_sources(tmp_path)
    assert report['parsed']==1 and len(report['non_runtime_artifacts'])==1
    code.write_text('runtime = "unterminated\n')
    with pytest.raises(DrillError,match='restored Python source invalid: opt/walter-skills/service.py:1'):
        validate_sources(tmp_path)
