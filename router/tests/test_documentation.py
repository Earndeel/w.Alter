"""The reference must drift visibly when the executable contract changes."""
import ast
import copy
import hashlib
import json

import pytest

from walter_router import documentation, paths
from walter_router.serve import api, brief


def test_generated_reference_is_current_without_private_data_or_a_db_call():
    result = documentation.maintain(offline=True)
    assert result['ok'], result
    assert documentation._neutral_metadata(
        {'description':'For OWNER', 'requirements':{'count':3, 'note':'ask Owner'}}, 'Owner'
    ) == {'description':'For l’utilisateur', 'requirements':{'count':3, 'note':'ask l’utilisateur'}}


def test_every_native_run_input_is_described():
    tree = ast.parse((paths.ROOT/'serve'/'run.py').read_text())
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='get'
                and isinstance(node.func.value,ast.Name) and node.func.value.id=='spec' and node.args
                and isinstance(node.args[0],ast.Constant)):
            keys.add(node.args[0].value)
        if (isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id=='spec'
                and isinstance(node.slice,ast.Constant)):
            keys.add(node.slice.value)
    assert keys <= api.RUN.keys(), keys-api.RUN.keys()


def test_unknown_database_fields_cannot_be_silently_documented():
    # A real metadata extension must receive an explanation, not a placeholder.
    class Rows(list):
        def fetchone(self): return self[0]
    class Conn:
        def execute(self,sql,args=None):
            if 'from pg_class c' in sql:
                return Rows([dict(oid=1,name='new_table',kind='r',description='Table')])
            if 'from pg_attribute' in sql:
                return Rows([dict(name='new_undocumented_parameter',type='text',nullable=True,default=None,comment=None)])
            return Rows([])
    with pytest.raises(ValueError,match='Undocumented database field'):
        documentation.database(Conn())


def test_note_is_versioned_bounded_and_has_no_live_model_choices():
    c = documentation.collect(offline=True)
    note = c['note']
    assert note['schema_version']==1 and note['id']=='walter-router.usage'
    assert note['chars'] == len(note['content']) <= brief.MAX_CHARS
    assert note['sha256'] == hashlib.sha256(note['content'].encode()).hexdigest()
    for text in ('walter_run','walter_decide','walter_plans','user_notice','context','local_only'):
        assert text in note['content']
    assert not any(name in note['content'] for name in ('OpenRouter','Codex','Kie','Claude','GPT-','Gemini'))


def test_check_reports_stale_outputs_instead_of_silently_updating(monkeypatch,tmp_path):
    catalog = documentation.collect(offline=True)
    monkeypatch.setattr(documentation,'collect',lambda offline=False: catalog)
    monkeypatch.setattr(paths,'ROOT',tmp_path)
    out=documentation.maintain(offline=True)
    assert not out['ok'] and 'docs/reference/API.md' in out['stale']
    assert not (tmp_path/'docs').exists()


def test_offline_catalog_and_render_are_deterministic():
    first=documentation.collect(offline=True)
    second=documentation.collect(offline=True)
    assert first==second and documentation.render(first)==documentation.render(second)


def test_api_and_cli_include_documentation_interfaces():
    c=documentation.collect(offline=True)
    names=next(a['subcommands'] for a in c['cli'] if 'subcommands' in a)
    assert {'schema','docs','brief'} <= names.keys()
    assert any('--json' in a['flags'] for a in names['brief'])
    assert {t['name'] for t in api.schema()['tools']} == {'walter_route','walter_run','walter_decide','walter_plans'}
