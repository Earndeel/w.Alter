"""walter-ops install migrations-check: structure comparison (no database here; the real replay is the bench scenario
clean-migrations)."""
from walter_ops import clean

LIVE = """--
-- Name: t; Type: TABLE; Schema: s; Owner: -
--

CREATE TABLE s.t (
    a integer,
    b text,
    c text
);
SET default_table_access_method = heap;
\\restrict abc
--
-- Name: t_pkey; Type: CONSTRAINT; Schema: s; Owner: -
--

ALTER TABLE ONLY s.t ADD CONSTRAINT t_pkey PRIMARY KEY (a);
--
-- Name: events_2026_10; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.events_2026_10 (x int);
"""


def test_objects_strip_noise_and_key_by_type_schema_name():
    objs = clean.objects(LIVE)
    assert set(objs) == {"TABLE s.t", "CONSTRAINT s.t_pkey", "TABLE core.events_2026_10"}
    assert "SET " not in objs["TABLE s.t"] and "restrict" not in objs["TABLE s.t"]


def test_compare_classes():
    live = clean.objects(LIVE)
    built = dict(live)
    built["TABLE s.t"] = "CREATE TABLE s.t (\n    a integer,\n    c text,\n    b text\n);"   # column order only
    built.pop("CONSTRAINT s.t_pkey")
    built["INDEX s.new"] = "CREATE INDEX new ON s.t (b);"
    d = clean.compare(live, built, ["TABLE core.events_*"])
    assert d == {"missing": ["CONSTRAINT s.t_pkey"], "extra": ["INDEX s.new"], "different": [],
                 "order_only": ["TABLE s.t"]}
    built["TABLE s.t"] = "CREATE TABLE s.t (\n    a bigint\n);"
    assert clean.compare(live, built, ["TABLE core.events_*"])["different"] == ["TABLE s.t"]
