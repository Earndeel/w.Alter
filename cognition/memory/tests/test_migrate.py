"""walter-memory migrate (2026-10-29, Walter Clean): psql-like statement splitting; the migrations build a blank
database (the full replay is the bench scenario clean-migrations, run against a disposable PostgreSQL)."""
from walter_memory import migrate


def test_split_respects_strings_comments_and_dollar_quotes():
    sql = ("select ';' as a; -- not; a split\n/* nor ; this */ select 2;\n"
           "create function f() returns int as $$ select 1; $$ language sql;\n"
           "do $tag$ begin execute $ddl$ create table t (x int); create view v as select 1; $ddl$; end $tag$;\n"
           "select \"odd;name\" from t; select 'it''s;fine'")
    out = migrate.statements(sql)
    assert len(out) == 6
    assert out[0] == "select ';' as a" and out[2].startswith("create function") and "$ddl$;" in out[3]
    assert out[-1] == "select 'it''s;fine'"


def test_comment_only_tail_is_not_a_statement():
    assert migrate.statements("select 1;\n-- trailing note;\n") == ["select 1"]


def test_every_migration_splits_and_is_ordered():
    names = [p.name for p in migrate.files()]
    assert names == sorted(names) and names[0] == "000_extensions.sql" and "019_schema_migrations.sql" in names
    for p in migrate.files():
        assert migrate.statements(p.read_text()), p.name


def test_kardex_base_is_one_guarded_statement():
    body = (migrate.DIR / "004b_kardex_base.sql").read_text()
    (stmt,) = migrate.statements(body)
    assert "to_regnamespace('kardex') is null" in stmt and "CREATE SCHEMA kardex" in stmt


def test_foundation_never_casts_a_missing_relation():
    text = (migrate.DIR / "001_foundation.sql").read_text()
    assert "'vault.objects'::regclass" not in text and "to_regclass('vault.objects')" in text
    assert "create table if not exists core.object_links" in text


def test_kardex_base_already_has_the_names_020_gives():
    import re
    renames = re.findall(r"\('(\w+)', '(\w+)', '(\w+)'\)", (migrate.DIR / "020_kardex_neutral_names.sql").read_text())
    base = (migrate.DIR / "004b_kardex_base.sql").read_text()
    assert len(renames) == 4
    for _table, old, new in renames:
        assert f"    {new} " in base and f"    {old} " not in base
