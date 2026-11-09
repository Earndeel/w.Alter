#!/usr/bin/env python3
"""Walter Memory — full backup and durable knowledge archive, taken from ONE PostgreSQL snapshot (cleanup phase 0).

    memory_archive.py create  <out-dir> --recipient-file <age.pub> [--container C] [--db D] [--user U]
                              [--host H] [--port P] [--min-free-gib N]
    memory_archive.py verify  <out-dir>                         hashes, sizes and modes of every file vs MANIFEST.json
    memory_archive.py restore-check <out-dir> --identity <age key> --image <postgres image>
                              full restore in a disposable PostgreSQL without network (roles first, then every
                              database), then compare every table (rows + content digest), roles, password hashes,
                              extensions, schemas, privileges and object counts with the snapshot; report written as
                              restore-check-<time>.json next to the archive; the container and its data are removed

What `create` writes (every file holding data is zstd-compressed then age-encrypted to the recipient; README.md and
MANIFEST.json hold no personal content):

    pg/globals.sql.age              roles (password hashes included), role memberships, tablespaces (pg_dumpall -g)
    pg/<db>.dump.age                pg_dump -Fc of every database; the main one taken at the archive's snapshot
    pg/cluster.json                 versions, extensions, settings, roles (attributes only), ACL digests, hba rules
    pg/tables.json                  exact row count + content digest of every table AT THE SNAPSHOT (restore proof)
    personal/ project/ observability/ technical/   the structured archive (see README.md written next to it)

Read-only on the database: one REPEATABLE READ transaction exports its snapshot to pg_dump and runs every count and
export inside it (temporary tables only), so dump, counts and archive describe the same instant. The password is
never handled here: libpq reads it from the user's pgpass file; pg_dump runs in the server container over its local
socket. Nothing is printed but counts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import psycopg
import zstandard
from psycopg import sql as pgsql

AGENT_SOURCES = ['hermes', 'claude_code', 'codex', 'dsh', 'walter', 'claude']
PERSONAL_SOURCES = ['beeper', 'gmail', 'calendar', 'overland', 'documents', 'kardex_legacy', 'location', 'vault']
OBSERVABILITY_TYPES = ['tool.called', 'skill.used', 'conversation.started', 'conversation.ended']
PERSONAL_KINDS = ['profile', 'preference', 'psych_hypothesis', 'bias_hypothesis', 'life_signal', 'visit',
                  'appointment', 'facet']
# Paths and names that only occur when the work is on Walter itself (tool arguments of agent conversations).
WALTER_RE = r'(/walter\M|/walter/|/opt/walter|/opt/dsh|\.hermes|/user/[A-Za-z]|walter[-_]|CLAUDE\.md|hindsight|kardex)'
OTHER_RE = r'(/projects/|/apps/|/srv/projects)'
ARTIFACT_SCHEMAS = ['public', 'legacy', 'walter_voice', 'walter_audit', 'user_model', 'x_research']


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Sealed:
    """Write a file as zstd → age, hashing the plaintext and counting lines on the way."""

    def __init__(self, path: Path, recipient: Path, compress: bool = True):
        self.path, self.compress = path, compress
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.proc = subprocess.Popen(['age', '-R', str(recipient), '-o', str(path)], stdin=subprocess.PIPE)
        self.sink = (zstandard.ZstdCompressor(level=10, threads=2).stream_writer(self.proc.stdin, closefd=False)
                     if compress else self.proc.stdin)
        self.h, self.bytes, self.lines = hashlib.sha256(), 0, 0

    def write(self, data: bytes):
        self.h.update(data)
        self.bytes += len(data)
        self.lines += data.count(b'\n')
        self.sink.write(data)

    def close(self) -> dict:
        if self.compress:
            self.sink.close()
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError(f'age failed for {self.path.name}')
        os.chmod(self.path, 0o600)
        return {'plain_sha256': self.h.hexdigest(), 'plain_bytes': self.bytes, 'lines': self.lines,
                'sha256': sha256_file(self.path), 'bytes': self.path.stat().st_size,
                'format': ('zstd+age' if self.compress else 'age')}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def stream_command(cmd: list[str], out: Path, recipient: Path, compress: bool, result: dict, key: str):
    """Run a command and seal its stdout; the result (or the error) lands in result[key]."""
    try:
        w = Sealed(out, recipient, compress)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        for chunk in iter(lambda: p.stdout.read(1 << 20), b''):
            w.write(chunk)
        rc = p.wait()
        info = w.close()
        if rc != 0:
            raise RuntimeError(f'{cmd[0:4]} exited {rc}')
        result[key] = info
    except Exception as exc:  # reported, never swallowed
        result[key] = {'error': str(exc)}


class Archive:
    def __init__(self, a):
        self.a = a
        self.out = Path(a.out)
        self.rcpt = Path(a.recipient_file)
        self.files: dict[str, dict] = {}
        self.meta: dict = {'created_at': now(), 'tool': 'walter-memory ops/memory_archive.py', 'format_version': 1}

    # ---- helpers ------------------------------------------------------------------------------------------------
    def export(self, cur_factory, rel: str, sql: str, params=None, category: str = '', describe: str = ''):
        """Stream `select row_to_json(...)` rows into a sealed JSONL file."""
        w = Sealed(self.out / (rel + '.zst.age'), self.rcpt)
        with cur_factory() as cur:
            cur.itersize = 5000
            cur.execute(f'select row_to_json(x)::text from ({sql}) x', params or {})
            for (line,) in cur:
                w.write(line.encode() + b'\n')
        info = w.close()
        info.update({'category': category, 'content': describe})
        self.files[rel + '.zst.age'] = info
        print(f'  {rel}: {info["lines"]} lignes', flush=True)

    def write_json(self, rel: str, data, sealed: bool = False, category: str = '', describe: str = ''):
        raw = (json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True, default=str) + '\n').encode()
        if sealed:
            w = Sealed(self.out / (rel + '.zst.age'), self.rcpt)
            w.write(raw)
            info = w.close()
            rel = rel + '.zst.age'
        else:
            p = self.out / rel
            p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            p.write_bytes(raw)
            os.chmod(p, 0o600)
            info = {'sha256': sha256_file(p), 'bytes': p.stat().st_size, 'format': 'json'}
        info.update({'category': category, 'content': describe})
        self.files[rel] = info

    # ---- main -------------------------------------------------------------------------------------------------
    def run(self):
        a = self.a
        if self.out.exists() and any(self.out.iterdir()):
            sys.exit(f'output not empty: {self.out}')
        free = shutil.disk_usage(self.out.parent if self.out.parent.exists() else '/').free / 2**30
        self.meta['disk_free_gib_before'] = round(free, 1)
        if free < a.min_free_gib:
            sys.exit(f'not enough disk: {free:.1f} GiB free, {a.min_free_gib} required')
        old = os.umask(0o077)
        self.out.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = psycopg.connect(host=a.host, port=a.port, dbname=a.db, user=a.user, autocommit=False,
                               application_name='memory_archive')
        cur = conn.cursor()
        cur.execute('set transaction isolation level repeatable read')
        cur.execute("select pg_export_snapshot(), now(), current_setting('server_version'), pg_current_snapshot()::text")
        snap, at, version, xsnap = cur.fetchone()
        self.meta['snapshot'] = {'at': at.isoformat(), 'server_version': version, 'txid_snapshot': xsnap,
                                 'database': a.db}
        print(f'instantané {at.isoformat()}', flush=True)
        dumps: dict = {}
        dump_thread = threading.Thread(target=stream_command, args=(
            ['docker', 'exec', a.container, 'pg_dump', '-U', a.user, '-d', a.db, '-Fc', '-Z', '6',
             f'--snapshot={snap}'], self.out / 'pg' / f'{a.db}.dump.age', self.rcpt, False, dumps, a.db))
        dump_thread.start()

        named = iter(range(10**6))

        def cursor():
            return conn.cursor(name=f'c{next(named)}')

        try:
            self.tables(cur)
            self.cluster(cur)
            self.classify(cur)
            self.export_all(cursor, cur)
        finally:
            dump_thread.join()
        conn.rollback()  # nothing was written but temporary tables
        conn.close()
        if 'error' in dumps.get(a.db, {'error': 'missing'}):
            sys.exit(f'dump of {a.db} failed: {dumps.get(a.db)}')
        dumps[a.db].update({'category': 'backup', 'content': f'pg_dump -Fc of {a.db} at the archive snapshot'})
        self.files[f'pg/{a.db}.dump.age'] = dumps.pop(a.db)
        # globals and the other databases (not part of the snapshot: they are static or tiny)
        other = {}
        stream_command(['docker', 'exec', a.container, 'pg_dumpall', '-U', a.user, '--globals-only'],
                       self.out / 'pg' / 'globals.sql.age', self.rcpt, True, other, 'globals')
        for db in self.meta['cluster']['other_databases']:
            stream_command(['docker', 'exec', a.container, 'pg_dump', '-U', a.user, '-d', db, '-Fc'],
                           self.out / 'pg' / f'{db}.dump.age', self.rcpt, False, other, db)
        for k, v in other.items():
            if 'error' in v:
                sys.exit(f'backup {k} failed: {v}')
            name = 'pg/globals.sql.zst.age' if k == 'globals' else f'pg/{k}.dump.age'
            if k == 'globals':
                (self.out / 'pg' / 'globals.sql.age').rename(self.out / name)
            v.update({'category': 'backup', 'content': 'roles, memberships, tablespaces (pg_dumpall --globals-only)'
                      if k == 'globals' else f'pg_dump -Fc of {k}'})
            self.files[name] = v
        self.meta['disk_free_gib_after'] = round(shutil.disk_usage(self.out).free / 2**30, 1)
        self.write_manifest()
        os.umask(old)
        print('fini', flush=True)

    # ---- exact state at the snapshot ----------------------------------------------------------------------------
    def tables(self, cur):
        cur.execute("""select n.nspname, c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                       where c.relkind in ('r','m') and n.nspname not in ('pg_catalog','information_schema')
                         and n.nspname !~ '^pg_' order by 1, 2""")
        rels = cur.fetchall()
        out = {}
        for i, (s, t) in enumerate(rels):
            q = pgsql.SQL('select count(*), md5(coalesce(string_agg(h, \'\' order by h), \'\')) '
                                'from (select md5(x::text) h from {}.{} x) y').format(
                pgsql.Identifier(s), pgsql.Identifier(t))
            cur.execute(q)
            n, digest = cur.fetchone()
            out[f'{s}.{t}'] = {'rows': n, 'digest': digest}
            if i % 50 == 0:
                print(f'  tables {i}/{len(rels)}', flush=True)
        self.table_state = out
        self.write_json('pg/tables.json', {'snapshot': self.meta['snapshot'], 'tables': out}, category='backup',
                        describe='exact row count and content digest (md5 of the sorted md5 of every row) per table')

    def cluster(self, cur):
        q = lambda sql: (cur.execute(sql), cur.fetchall())[1]
        info = {
            'server_version': q('show server_version')[0][0],
            'databases': [dict(zip(('name', 'owner', 'encoding', 'collate', 'ctype', 'acl_md5'), r)) for r in q(
                """select datname, pg_get_userbyid(datdba), pg_encoding_to_char(encoding), datcollate, datctype,
                          md5(coalesce(datacl::text,'')) from pg_database where not datistemplate order by 1""")],
            'roles': [dict(zip(('name', 'super', 'login', 'createdb', 'createrole', 'replication', 'bypassrls',
                                'password_md5'), r)) for r in q(
                """select rolname, rolsuper, rolcanlogin, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls,
                          md5(coalesce(rolpassword,'')) from pg_authid where rolname !~ '^pg_' order by 1""")],
            'extensions': [dict(zip(('name', 'version', 'schema'), r)) for r in q(
                "select extname, extversion, extnamespace::regnamespace::text from pg_extension order by 1")],
            'schemas': [dict(zip(('name', 'owner', 'acl_md5'), r)) for r in q(
                """select nspname, pg_get_userbyid(nspowner), md5(coalesce(nspacl::text,'')) from pg_namespace
                   where nspname !~ '^pg_' and nspname <> 'information_schema' order by 1""")],
            'object_counts': dict(q("""select 'relkind_' || relkind::text, count(*) from pg_class c join pg_namespace n
                   on n.oid=c.relnamespace where nspname !~ '^pg_' and nspname <> 'information_schema' group by 1
                   union all select 'functions', count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                   where nspname !~ '^pg_' and nspname <> 'information_schema'
                   union all select 'triggers', count(*) from pg_trigger where not tgisinternal
                   union all select 'constraints', count(*) from pg_constraint c join pg_namespace n
                   on n.oid=c.connamespace where nspname !~ '^pg_' and nspname <> 'information_schema'""")),
            'acl_digest': q("""select md5(string_agg(n.nspname||'.'||c.relname||'='||coalesce(c.relacl::text,'')||
                   '/'||pg_get_userbyid(c.relowner), ',' order by n.nspname, c.relname)) from pg_class c
                   join pg_namespace n on n.oid=c.relnamespace where nspname !~ '^pg_'
                   and nspname <> 'information_schema'""")[0][0],
            'default_acl_digest': q("select md5(coalesce(string_agg(defaclacl::text, ',' order by defaclacl::text),''))"
                                    " from pg_default_acl")[0][0],
            'settings': dict(q("""select name, setting from pg_settings where source not in ('default','override')
                                  and name not like '%password%' order by 1""")),
            'hba_rules': [list(map(str, r)) for r in q(
                "select type, database, user_name, address, netmask, auth_method from pg_hba_file_rules "
                "order by line_number")],
            'sizes_mb': dict(q("""select n.nspname, round(sum(pg_total_relation_size(c.oid))/1048576.0) from pg_class c
                   join pg_namespace n on n.oid=c.relnamespace where relkind in ('r','m')
                   and nspname !~ '^pg_' group by 1""")),
        }
        info['other_databases'] = [d['name'] for d in info['databases'] if d['name'] != self.a.db]
        self.meta['cluster'] = info
        self.write_json('pg/cluster.json', info, category='backup',
                        describe='server state needed to judge a restore (no secret: password hashes as md5 digests)')

    # ---- classification -----------------------------------------------------------------------------------------
    def classify(self, cur):
        """Thread → class, then derived item → class, then view → class. Rules only (no model), each row keeps
        the rule that decided it; cleanup phase 5 refines the 'unclassified' ones."""
        cur.execute("""create temp table arch_threads as
            with m as (
              select source, thread_id, min(occurred_at) first_at, max(occurred_at) last_at,
                     count(*) filter (where event_type like 'message.%%') messages,
                     count(*) filter (where event_type = 'tool.called') tools,
                     count(*) filter (where event_type = 'tool.called' and payload->>'args_summary' ~* %(w)s) walter_hits,
                     count(*) filter (where event_type = 'tool.called' and payload->>'args_summary' ~* %(o)s) other_hits,
                     max(payload->>'cwd') filter (where payload ? 'cwd') cwd_ev
              from core.events where source = any(%(agents)s) and thread_id is not null group by 1, 2)
            select m.*, coalesce(m.cwd_ev, s.cwd) cwd, s.session_id log_session, s.runtime, s.title_present
            from m left join lateral (
              select session_id, cwd, runtime, title is not null title_present from walter_logs.sessions s
              where s.native_id = m.thread_id or s.session_id = m.thread_id
              order by (s.native_id = m.thread_id) desc limit 1) s on true""",
                    {'w': WALTER_RE, 'o': OTHER_RE, 'agents': AGENT_SOURCES})
        cur.execute("""alter table arch_threads add column class text, add column rule text""")
        cur.execute("""update arch_threads set
              class = case when other_hits > walter_hits then 'other_project' when walter_hits > 0 then 'walter_project'
                    when cwd ~ '^/(projects|apps|srv)/' then 'other_project'
                    when source in ('claude_code','codex','dsh') and cwd is not null then 'walter_project'
                    when source in ('walter','claude') then 'walter_project'
                    else 'unclassified' end,
              rule = case when other_hits > walter_hits then 'tool paths: other projects'
                    when walter_hits > 0 then 'tool paths: Walter'
                    when cwd ~ '^/(projects|apps|srv)/' then 'working directory: other project'
                    when source in ('claude_code','codex','dsh') and cwd is not null then 'development tool on the VM'
                    when source in ('walter','claude') then 'Walter internal note'
                    when tools > 0 then 'technical work, project not identified'
                    else 'conversation without technical work' end""")
        cur.execute("create index on arch_threads (source, thread_id)")
        cur.execute("create index on arch_threads (log_session)")
        # derived items
        cur.execute("""create temp table arch_items as
            with ev as (
              select d.item_id, e.source, e.thread_id
              from core.derived_items d cross join lateral unnest(d.source_event_ids) u(eid)
              join core.events e on e.event_id = u.eid),
            agg as (
              select ev.item_id, bool_or(ev.source = any(%(personal)s)) personal_src,
                     array_agg(distinct t.class) filter (where t.class is not null) classes
              from ev left join arch_threads t on t.source = ev.source and t.thread_id = ev.thread_id
              group by 1),
            ses as (
              select d.item_id, array_agg(distinct t.class) classes from core.derived_items d
              join arch_threads t on t.thread_id = d.source_refs->>'session' or t.log_session = d.source_refs->>'session'
              where jsonb_typeof(d.source_refs) = 'object' and d.source_refs ? 'session' group by 1)
            select d.item_id, d.kind,
              case when agg.personal_src then 'personal'
                   when d.kind = any(%(pkinds)s) then 'personal'
                   when coalesce(agg.classes, ses.classes) = array['walter_project'] then 'walter_project'
                   when 'other_project' = any(coalesce(agg.classes, ses.classes)) then 'other_project'
                   when 'walter_project' = any(coalesce(agg.classes, ses.classes)) then 'mixed'
                   else 'unclassified' end class,
              case when agg.personal_src then 'source: personal source'
                   when d.kind = any(%(pkinds)s) then 'kind: personal'
                   when agg.classes is not null then 'source threads'
                   when ses.classes is not null then 'source session'
                   else 'no traceable source thread' end rule
            from core.derived_items d left join agg using (item_id) left join ses using (item_id)""",
                    {'personal': PERSONAL_SOURCES, 'pkinds': PERSONAL_KINDS})
        cur.execute("create index on arch_items (item_id)")
        # views: majority class of their member log events' sessions
        cur.execute("""create temp table arch_views as
            select v.view_key, coalesce((select t.class from views.member m join arch_threads t
                        on t.log_session = m.session_id where m.view_key = v.view_key
                        group by 1 order by count(*) desc limit 1), 'unclassified') class
            from views.view v""")
        q = lambda sql: (cur.execute(sql), cur.fetchall())[1]
        self.meta['classification'] = {
            'rules': {'walter_re': WALTER_RE, 'other_re': OTHER_RE, 'agent_sources': AGENT_SOURCES,
                      'personal_sources': PERSONAL_SOURCES, 'personal_kinds': PERSONAL_KINDS},
            'threads': [dict(zip(('source', 'class', 'rule', 'threads', 'messages'), r)) for r in q(
                "select source, class, rule, count(*), sum(messages) from arch_threads group by 1,2,3 order by 1,2,3")],
            'items': [dict(zip(('class', 'rule', 'items'), r)) for r in q(
                "select class, rule, count(*) from arch_items group by 1,2 order by 1,2")],
            'items_by_kind': [dict(zip(('class', 'kind', 'items'), r)) for r in q(
                "select class, kind, count(*) from arch_items group by 1,2 order by 1,3 desc")],
            'views': [dict(zip(('class', 'kind', 'views'), r)) for r in q(
                "select a.class, v.kind, count(*) from arch_views a join views.view v using (view_key) group by 1,2")],
        }
        print('  classement fait', flush=True)

    # ---- exports ------------------------------------------------------------------------------------------------
    def export_all(self, cursor, cur):
        item_cols = """d.item_id, d.kind, d.content, d.attributes, d.status, d.generation, d.stage, d.scope, d.epistemic,
            d.derived_by, d.processor_version, d.model, d.source_event_ids, d.source_object_ids, d.source_refs,
            d.subject_entity_ids, d.confidence, d.valid_from, d.valid_to, d.privacy_class, d.created_at,
            d.lineage_id, a.class, a.rule"""
        view_cols = """v.view_key, v.kind, v.domain, v.horizon, v.title, v.status, v.merged_into, v.generation,
            v.first_at, v.last_at, v.starts_at, v.ends_at, v.tz, v.epistemic, v.confidence, v.entity_ids,
            v.attributes, v.privacy_class, v.created_at, v.updated_at, a.class,
            (select json_agg(json_build_object('depth', x.depth, 'version', x.version, 'content', x.content,
                     'source_refs', x.source_refs, 'built_at', x.built_at, 'model', x.model) order by x.depth)
             from (select distinct on (depth) * from views.version where view_key = v.view_key
                   order by depth, version desc) x) latest_versions,
            (select json_agg(json_build_object('ref_kind', e.ref_kind, 'ref_id', e.ref_id, 'role', e.role))
             from views.evidence e where e.view_key = v.view_key) evidence"""
        msg_cols = """e.event_id, e.source, e.thread_id, e.event_type, e.occurred_at, e.payload->>'role' role,
            e.content, e.privacy_class, e.object_refs, t.log_session, t.class"""
        print('projet Walter', flush=True)
        self.export(cursor, 'project/knowledge.jsonl', f"""select {item_cols} from core.derived_items d
            join arch_items a using (item_id) where a.class in ('walter_project') order by d.created_at""",
                    category='walter_project', describe='derived knowledge from Walter development conversations')
        self.export(cursor, 'project/views.jsonl', f"""select {view_cols} from views.view v join arch_views a
            using (view_key) where a.class = 'walter_project' order by v.first_at""",
                    category='walter_project', describe='subjects, episodes, periods (g0 and g1) with latest texts')
        self.export(cursor, 'project/threads.jsonl', """select source, thread_id, log_session, runtime, first_at,
            last_at, messages, tools, walter_hits, other_hits, cwd, class, rule from arch_threads
            where class = 'walter_project' order by first_at""", category='walter_project',
                    describe='conversation index: one row per thread, with its walter_logs session')
        self.export(cursor, 'project/conversations.jsonl', f"""select {msg_cols} from core.events e
            join arch_threads t on t.source = e.source and t.thread_id = e.thread_id
            where t.class = 'walter_project' and e.event_type like 'message.%%' order by e.occurred_at""",
                    category='walter_project', describe='original messages of the Walter development threads')
        self.export(cursor, 'project/timeline.jsonl', f"""select date_trunc('month', coalesce(d.valid_from,
            d.created_at))::date as month, coalesce(d.valid_from, d.created_at) at, d.kind, d.item_id,
            left(d.content, 600) as text, d.generation, d.status, d.source_event_ids[1:5] as first_sources
            from core.derived_items d join arch_items a using (item_id)
            where a.class = 'walter_project' and d.kind in ('decision','summary','work_session','outcome',
              'correction','constraint','goal','open_loop','plan','commitment')
              and d.status not in ('retracted','superseded') order by 2""", category='walter_project',
                    describe='chronology of decisions, work sessions, summaries, outcomes (feeds timeline.md)')
        self.timeline_md(cursor)
        self.docs()
        print('mémoire personnelle', flush=True)
        self.export(cursor, 'personal/knowledge.jsonl', f"""select {item_cols} from core.derived_items d
            join arch_items a using (item_id) where a.class <> 'walter_project' order by d.created_at""",
                    category='personal', describe='derived knowledge: personal, other projects, mixed, unclassified')
        self.export(cursor, 'personal/views.jsonl', f"""select {view_cols} from views.view v join arch_views a
            using (view_key) where a.class <> 'walter_project' order by v.first_at""", category='personal',
                    describe='subjects, episodes, periods not identified as Walter development')
        self.export(cursor, 'personal/threads.jsonl', """select source, thread_id, log_session, runtime, first_at,
            last_at, messages, tools, walter_hits, other_hits, cwd, class, rule from arch_threads
            where class <> 'walter_project' order by first_at""", category='personal',
                    describe='conversations with Walter not identified as Walter development (other projects, '
                             'personal requests, unclassified)')
        self.export(cursor, 'personal/conversations.jsonl', f"""select {msg_cols} from core.events e
            join arch_threads t on t.source = e.source and t.thread_id = e.thread_id
            where t.class <> 'walter_project' and e.event_type like 'message.%%' order by e.occurred_at""",
                    category='personal', describe='original messages of those conversations')
        for src in PERSONAL_SOURCES:
            cur.execute('select count(*) from core.events where source = %s', (src,))
            if cur.fetchone()[0]:
                self.export(cursor, f'personal/events/{src}.jsonl', """select event_id, event_type, type_version,
                    source, source_account, source_id, occurred_at, ingested_at, actor_identity_id, thread_id,
                    reply_to, content, content_hash, object_refs, payload, privacy_class, epistemic_status
                    from core.events where source = %(s)s order by occurred_at""", {'s': src}, category='personal',
                            describe=f'every canonical event of source {src}')
        for t, order in (('entities', 'created_at'), ('source_identities', '1'), ('identity_links', '1'),
                         ('relationships', '1'), ('objects', '1'), ('object_links', '1')):
            self.export(cursor, f'personal/core/{t}.jsonl', f'select * from core.{t} order by {order}',
                        category='personal', describe=f'core.{t} (complete)')
        cur.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                       where n.nspname = 'kardex' and c.relkind = 'r' order by 1""")
        for (t,) in cur.fetchall():
            self.export(cursor, f'personal/kardex/{t}.jsonl', f'select * from kardex.{t}', category='personal',
                        describe=f'kardex.{t} (complete; social layer)')
        print('observabilité', flush=True)
        self.export(cursor, 'observability/sessions.jsonl', """select session_id, runtime, native_id, profile,
            platform, cwd, parent_session_id, started_at, ended_at, last_event_at, privacy_class, last_seq, turns
            from walter_logs.sessions order by started_at""", category='observability',
                    describe='index of every agent session in walter_logs (content stays in the database and dump)')
        q = lambda sql, p=None: (cur.execute(sql, p), cur.fetchall())[1]
        obs = {
            'walter_logs_by_runtime_type': [dict(zip(('runtime', 'type', 'events', 'chars'), r)) for r in q(
                """select s.runtime, e.type, count(*), sum(e.chars) from walter_logs.events e
                   join walter_logs.sessions s using (session_id) group by 1,2 order by 1,3 desc""")],
            'walter_logs_by_month': [dict(zip(('month', 'events'), r)) for r in q(
                "select to_char(occurred_at,'YYYY-MM'), count(*) from walter_logs.events group by 1 order by 1")],
            'core_events_observability': [dict(zip(('source', 'type', 'events'), r)) for r in q(
                """select source, event_type, count(*) from core.events where event_type = any(%s)
                   group by 1,2 order by 1,2""", (OBSERVABILITY_TYPES,))],
        }
        self.write_json('observability/inventory.json', obs, category='observability',
                        describe='volumes of the observability data (counts only)')
        tech = {'schemas': {s: {'size_mb': self.meta['cluster']['sizes_mb'].get(s),
                                'tables': {k: v['rows'] for k, v in self.table_state.items()
                                           if k.startswith(s + '.')}} for s in ARTIFACT_SCHEMAS}}
        self.write_json('technical/inventory.json', tech, category='technical_artifact',
                        describe='historical schemas (Hindsight, legacy pipeline, voice, old profile compiler)')
        overview = {
            'events_by_source_type': [dict(zip(('source', 'type', 'privacy', 'events', 'first', 'last'), r))
                                      for r in q("""select source, event_type, privacy_class, count(*),
                                      min(occurred_at)::date, max(occurred_at)::date from core.events
                                      group by 1,2,3 order by 1,4 desc""")],
            'derived_by_kind': [dict(zip(('generation', 'status', 'kind', 'items'), r)) for r in q(
                "select generation, status, kind, count(*) from core.derived_items group by 1,2,3 order by 4 desc")],
        }
        self.write_json('personal/inventory.json', overview, category='personal',
                        describe='what Memory holds: events per source and type, knowledge per kind (counts only)')

    def timeline_md(self, cursor):
        """Human-readable history of the Walter project, month by month (sealed: it quotes conversations)."""
        w = Sealed(self.out / 'project/timeline.md.zst.age', self.rcpt)
        w.write(b'# Histoire du projet Walter (connaissances derivees, par mois)\n\n'
                b'Chaque ligne : date, nature, debut du texte, identifiant de l element (core.derived_items) et '
                b'premiers evenements sources (core.events). Source complete : project/knowledge.jsonl.\n')
        month = None
        with cursor() as cur:
            cur.itersize = 2000
            cur.execute("""select to_char(coalesce(d.valid_from, d.created_at), 'YYYY-MM') m,
                   to_char(coalesce(d.valid_from, d.created_at), 'YYYY-MM-DD') d_day, d.kind, d.item_id::text,
                   regexp_replace(left(d.content, 400), '\\s+', ' ', 'g'), d.source_event_ids[1:3]::text
                   from core.derived_items d join arch_items a using (item_id)
                   where a.class = 'walter_project' and d.kind in ('decision','work_session','outcome',
                     'correction','constraint','goal','plan','commitment','summary')
                     and d.status not in ('retracted','superseded') order by 2, 3""")
            for m, day, kind, iid, text, srcs in cur:
                if m != month:
                    w.write(f'\n## {m}\n\n'.encode())
                    month = m
                w.write(f'- {day} · **{kind}** · {text} `[{iid}]` sources {srcs}\n'.encode())
        info = w.close()
        info.update({'category': 'walter_project', 'content': 'month-by-month history (Markdown)'})
        self.files['project/timeline.md.zst.age'] = info

    def docs(self):
        """The written history next to the data: global and module documentation, and every repository's log."""
        root = Path(self.a.docs_root)
        files = sorted({p for pat in ('docs/*.md', '*/README.md', '*/docs/*.md', '*/*/README.md', '*/*/docs/*.md',
                                       '*/*/docs/**/*.md', '*/contracts/*.json')
                        for p in root.glob(pat) if p.is_file() and 'node_modules' not in p.parts})
        tar = subprocess.Popen(['tar', '-C', str(root), '-cf', '-', '--', *[str(p.relative_to(root)) for p in files]],
                               stdout=subprocess.PIPE)
        w = Sealed(self.out / 'project/docs.tar.zst.age', self.rcpt)
        for chunk in iter(lambda: tar.stdout.read(1 << 20), b''):
            w.write(chunk)
        if tar.wait() != 0:
            raise RuntimeError('tar of the documentation failed')
        info = w.close()
        info.update({'category': 'walter_project', 'content': f'{len(files)} documentation files (tar)'})
        self.files['project/docs.tar.zst.age'] = info
        w = Sealed(self.out / 'project/git-history.jsonl.zst.age', self.rcpt)
        repos = sorted({p.parent for pat in ('.git', '*/.git', '*/*/.git') for p in root.glob(pat)}, key=str)
        for repo in repos:
            log = subprocess.run(['git', '-C', str(repo), 'log', '--all', '--date=iso-strict',
                                  '--format=%H%x1f%aI%x1f%an%x1f%s'], capture_output=True, text=True)
            for line in log.stdout.splitlines():
                h, date, author, subject = (line.split('\x1f') + ['', '', '', ''])[:4]
                w.write((json.dumps({'repo': str(repo.relative_to(root)), 'commit': h, 'date': date,
                                     'author': author, 'subject': subject}, ensure_ascii=False) + '\n').encode())
        info = w.close()
        info.update({'category': 'walter_project', 'content': f'commit history of {len(repos)} repositories'})
        self.files['project/git-history.jsonl.zst.age'] = info

    def write_manifest(self):
        m = dict(self.meta)
        m['files'] = self.files
        m.pop('cluster', None)  # in pg/cluster.json
        p = self.out / 'MANIFEST.json'
        p.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True, default=str) + '\n')
        os.chmod(p, 0o600)


def verify(out: Path) -> int:
    m = json.loads((out / 'MANIFEST.json').read_text())
    bad = []
    for rel, info in m['files'].items():
        p = out / rel
        if not p.is_file():
            bad.append((rel, 'missing'))
            continue
        if sha256_file(p) != info['sha256']:
            bad.append((rel, 'sha256'))
        if p.stat().st_mode & 0o077:
            bad.append((rel, 'mode'))
    for d in [out, *[p for p in out.rglob('*') if p.is_dir()]]:
        if d.stat().st_mode & 0o077:
            bad.append((str(d), 'dir mode'))
    extra = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()
                   and str(p.relative_to(out)) not in m['files'] and p.name not in ('MANIFEST.json', 'README.md')
                   and not p.name.startswith('restore-check-'))
    print(json.dumps({'files': len(m['files']), 'problems': bad, 'unlisted': extra, 'ok': not bad and not extra}))
    return 0 if not bad and not extra else 1


CLUSTER_CHECKS = {
    'roles': """select json_agg(json_build_object('name', rolname, 'super', rolsuper, 'login', rolcanlogin,
        'createdb', rolcreatedb, 'createrole', rolcreaterole, 'replication', rolreplication, 'bypassrls', rolbypassrls,
        'password_md5', md5(coalesce(rolpassword,''))) order by rolname) from pg_authid where rolname !~ '^pg_'
        and rolname <> 'postgres'""",
    'extensions': """select json_agg(json_build_object('name', extname, 'version', extversion, 'schema',
        extnamespace::regnamespace::text) order by extname) from pg_extension""",
    'schemas': """select json_agg(json_build_object('name', nspname, 'owner', pg_get_userbyid(nspowner), 'acl_md5',
        md5(coalesce(nspacl::text,''))) order by nspname) from pg_namespace where nspname !~ '^pg_'
        and nspname <> 'information_schema'""",
    'acl_digest': """select to_json(md5(string_agg(n.nspname||'.'||c.relname||'='||coalesce(c.relacl::text,'')||'/'||
        pg_get_userbyid(c.relowner), ',' order by n.nspname, c.relname))) from pg_class c join pg_namespace n
        on n.oid=c.relnamespace where nspname !~ '^pg_' and nspname <> 'information_schema'""",
    'default_acl_digest': """select to_json(md5(coalesce(string_agg(defaclacl::text, ',' order by defaclacl::text),'')))
        from pg_default_acl""",
    'object_counts': """select json_object_agg(k, n) from (select 'relkind_' || relkind::text k, count(*) n
        from pg_class c join pg_namespace n on n.oid=c.relnamespace where nspname !~ '^pg_'
        and nspname <> 'information_schema' group by 1 union all select 'functions', count(*) from pg_proc p
        join pg_namespace n on n.oid=p.pronamespace where nspname !~ '^pg_' and nspname <> 'information_schema'
        union all select 'triggers', count(*) from pg_trigger where not tgisinternal union all select 'constraints',
        count(*) from pg_constraint c join pg_namespace n on n.oid=c.connamespace where nspname !~ '^pg_'
        and nspname <> 'information_schema') x""",
    'databases': """select json_agg(json_build_object('name', datname, 'owner', pg_get_userbyid(datdba), 'encoding',
        pg_encoding_to_char(encoding), 'collate', datcollate, 'ctype', datctype, 'acl_md5',
        md5(coalesce(datacl::text,''))) order by datname) from pg_database where not datistemplate""",
}

FUNCTIONAL = {
    'full_text_search': "select count(*) > 0 from (select 1 from search.chunks where tsv @@ "
                        "to_tsquery('simple', 'walter') limit 5) x",
    'vector_search': "select count(*) = 5 from (select 1 from search.chunks where embedding is not null order by "
                     "embedding <=> (select embedding from search.chunks where embedding is not null limit 1) limit 5) x",
    'append_only_trigger_present': "select count(*) > 0 from pg_trigger where tgname = 'events_append_only'",
}


def restore_check(a) -> int:
    out = Path(a.out)
    manifest = json.loads((out / 'MANIFEST.json').read_text())
    want_tables = json.loads((out / 'pg/tables.json').read_text())['tables']
    want_cluster = json.loads((out / 'pg/cluster.json').read_text())
    db = manifest['snapshot']['database']
    dumps = {k: v for k, v in manifest['files'].items() if k.startswith('pg/') and k.endswith('.dump.age')}
    need = sum(v['bytes'] for v in dumps.values()) * 6 / 2**30 + 3
    free = shutil.disk_usage(a.workdir).free / 2**30
    report = {'at': now(), 'archive': str(out), 'snapshot': manifest['snapshot'], 'disk_free_gib': round(free, 1),
              'disk_needed_gib': round(need, 1), 'steps': {}}
    if free < need:
        sys.exit(f'not enough disk for the restore: {free:.1f} GiB free, {need:.1f} needed')
    work = Path(a.workdir) / 'walter-pg-restore-check'
    name = 'walter-pg-restore-check'
    if work.exists() or subprocess.run(['docker', 'inspect', name], capture_output=True).returncode == 0:
        sys.exit(f'{work} or container {name} already exists')
    old = os.umask(0o077)
    (work / 'data').mkdir(parents=True)
    (work / 'in').mkdir()
    os.chmod(work, 0o700)
    t0 = dt.datetime.now(dt.timezone.utc)

    def step(key, fn):
        s = dt.datetime.now(dt.timezone.utc)
        res = fn()
        report['steps'][key] = {'seconds': round((dt.datetime.now(dt.timezone.utc) - s).total_seconds()), **(res or {})}
        print(f'  {key}: {report["steps"][key]}', flush=True)

    def psql(sql, dbname='postgres'):
        r = subprocess.run(['docker', 'exec', '-i', name, 'psql', '-U', 'postgres', '-d', dbname, '-At', '-q', '-v',
                            'ON_ERROR_STOP=1'], input=sql, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-500:])
        return r.stdout

    try:
        # 1. decrypt + check every plaintext hash against the manifest (proves the backup is the one recorded)
        def decrypt():
            ok = {}
            for rel, info in manifest['files'].items():
                if not rel.startswith('pg/') or not rel.endswith('.age'):
                    continue
                target = work / 'in' / Path(rel).name.removesuffix('.age').removesuffix('.zst')
                with open(target, 'wb') as f:
                    dec = subprocess.Popen(['age', '-d', '-i', a.identity, str(out / rel)], stdout=subprocess.PIPE)
                    src = dec.stdout
                    if info['format'] == 'zstd+age':
                        src = zstandard.ZstdDecompressor().stream_reader(dec.stdout)
                    h = hashlib.sha256()
                    for chunk in iter(lambda: src.read(1 << 20), b''):
                        h.update(chunk)
                        f.write(chunk)
                    if dec.wait():
                        raise RuntimeError(f'age -d failed for {rel}')
                ok[rel] = h.hexdigest() == info['plain_sha256']
                os.chmod(target, 0o644)  # read by the server's uid inside the container, folder stays 0700
            if not all(ok.values()):
                raise RuntimeError(f'plaintext hash mismatch: {ok}')
            return {'files': ok}
        step('decrypt_and_hash', decrypt)
        os.chmod(work / 'in', 0o755)

        def start():
            pw = hashlib.sha256(os.urandom(32)).hexdigest()  # throwaway superuser of the disposable server
            subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none', '--shm-size', '1g',
                            '-e', 'POSTGRES_USER=postgres', '-e', f'POSTGRES_PASSWORD={pw}',
                            '-v', f'{work}/data:/var/lib/postgresql/data', '-v', f'{work}/in:/restore:ro',
                            a.image], check=True, capture_output=True)
            for _ in range(90):
                logs = subprocess.run(['docker', 'logs', name], capture_output=True, text=True)
                if 'init process complete' in (logs.stdout + logs.stderr) and \
                        subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'postgres', '-q'],
                                  capture_output=True).returncode == 0 and \
                        subprocess.run(['docker', 'exec', name, 'psql', '-U', 'postgres', '-Atc', 'select 1'],
                                       capture_output=True).returncode == 0:
                    break
                import time
                time.sleep(2)
            ver = psql('show server_version').strip()
            return {'network': 'none', 'server_version': ver,
                    'same_version': ver == want_cluster['server_version']}
        step('start_isolated_server', start)
        step('restore_globals', lambda: (psql(open(work / 'in' / 'globals.sql').read()), {'ok': True})[1])

        def restore_dbs():
            res = {}
            for rel in dumps:
                d = Path(rel).name.removesuffix('.dump.age')
                # Sections in order, never one parallel run: in a single `-j` run pg_restore may create the trigger
                # of a partitioned table (it depends on the parent only) while partitions are still loading, and
                # the trigger then fires on restored rows (seen 2026-11-09 with core.events → core.publish_event).
                base = ['pg_restore', '-U', 'postgres', '--exit-on-error']
                if d == 'postgres':
                    runs = [[*base, '-d', 'postgres', f'/restore/{d}.dump']]
                else:
                    runs = [[*base, '-C', '-d', 'postgres', '--section=pre-data', f'/restore/{d}.dump'],
                            [*base, '-d', d, '-j', '4', '--section=data', f'/restore/{d}.dump'],
                            [*base, '-d', d, '-j', '4', '--section=post-data', f'/restore/{d}.dump']]
                for cmd in runs:
                    r = subprocess.run(['docker', 'exec', name, *cmd], capture_output=True, text=True)
                    res.setdefault(d, []).append({'section': next((c for c in cmd if c.startswith('--section')),
                                                                  'all'), 'rc': r.returncode})
                    if r.returncode:
                        raise RuntimeError(f'pg_restore {d}: {r.stderr[-400:]}')
            return res
        step('restore_databases', restore_dbs)

        def compare_tables():
            lines = []
            for key in want_tables:
                s_, t_ = key.split('.', 1)
                ident = '"' + s_.replace('"', '""') + '"."' + t_.replace('"', '""') + '"'
                lines.append(f"select '{key}', count(*), md5(coalesce(string_agg(h, '' order by h), '')) "
                             f"from (select md5(x::text) h from {ident} x) y;")
            got = {}
            for row in psql('\n'.join(lines), db).splitlines():
                k, n, dg = row.split('|')
                got[k] = {'rows': int(n), 'digest': dg}
            # Materialized views are not data: pg_restore recomputes them (REFRESH) from the restored tables, so a
            # view left stale on the live server (never refreshed since its tables changed) differs after a restore.
            # They are reported apart; exactness is judged on real tables.
            mv = set(psql("""select n.nspname || '.' || c.relname from pg_class c join pg_namespace n
                             on n.oid = c.relnamespace where c.relkind = 'm'""", db).split())
            tabs = {k: v for k, v in want_tables.items() if k not in mv}
            rows_diff = {k: (v['rows'], got.get(k, {}).get('rows')) for k, v in tabs.items()
                         if got.get(k, {}).get('rows') != v['rows']}
            digest_diff = sorted(k for k, v in tabs.items() if got.get(k, {}).get('digest') != v['digest'])
            mviews = {k: {'rows_snapshot': want_tables[k]['rows'], 'rows_restored': got.get(k, {}).get('rows'),
                          'same': got.get(k) == want_tables[k]} for k in sorted(mv) if k in want_tables}
            return {'tables': len(tabs), 'rows_total_snapshot': sum(v['rows'] for v in tabs.values()),
                    'rows_total_restored': sum(got.get(k, {}).get('rows') or 0 for k in tabs),
                    'row_mismatches': rows_diff, 'digest_mismatches': digest_diff,
                    'exact': not rows_diff and not digest_diff,
                    'materialized_views_recomputed': mviews}
        step('compare_every_table', compare_tables)

        def compare_cluster():
            res = {}
            for key, sql in CLUSTER_CHECKS.items():
                got = json.loads(psql(sql, db) or 'null')
                want = want_cluster.get(key)
                if key == 'roles':
                    want = [r for r in want if r['name'] != 'postgres']
                if key == 'databases':  # the maintenance database belongs to each server's own bootstrap role
                    got = [d for d in got if d['name'] != 'postgres']
                    want = [d for d in want if d['name'] != 'postgres']
                res[key] = got == want
            return {'equal': res, 'all_equal': all(res.values())}
        step('compare_roles_privileges_extensions', compare_cluster)

        def functional():
            res = {k: psql(sql, db).strip() == 't' for k, sql in FUNCTIONAL.items()}
            r = subprocess.run(['docker', 'exec', '-i', name, 'psql', '-U', 'postgres', '-d', db, '-Atq'],
                               input='begin; update core.events set content = content where event_id = '
                                     '(select event_id from core.events limit 1); rollback;',
                               capture_output=True, text=True)
            res['append_only_refuses_update'] = r.returncode != 0 or 'ERROR' in r.stderr
            return {'checks': res, 'all_ok': all(res.values())}
        step('functional_checks', functional)
    except Exception as e:  # recorded in the report (ok = false) instead of vanishing with the disposable server
        report['error'] = f'{type(e).__name__}: {str(e)[-800:]}'
        print(f'  ERROR {report["error"]}', flush=True)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)
        os.umask(old)
    report['seconds_total'] = round((dt.datetime.now(dt.timezone.utc) - t0).total_seconds())
    st = report['steps']
    report['ok'] = bool(st.get('compare_every_table', {}).get('exact')
                        and st.get('compare_roles_privileges_extensions', {}).get('all_equal')
                        and st.get('functional_checks', {}).get('all_ok')
                        and st.get('start_isolated_server', {}).get('same_version'))
    p = out / f"restore-check-{report['at'].replace(':', '')}.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    os.chmod(p, 0o600)
    print(json.dumps({'ok': report['ok'], 'report': str(p)}))
    return 0 if report['ok'] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('create')
    c.add_argument('out')
    c.add_argument('--recipient-file', required=True)
    c.add_argument('--container', default=os.environ.get('WALTER_PG_CONTAINER', 'hindsight-pg'))
    c.add_argument('--db', default=os.environ.get('WALTER_PG_DATABASE', 'hindsight'))
    c.add_argument('--user', default=os.environ.get('WALTER_PG_USER', 'hindsight'))
    c.add_argument('--host', default='127.0.0.1')
    c.add_argument('--port', default=os.environ.get('WALTER_PG_PORT', '5433'))
    c.add_argument('--min-free-gib', type=float, default=12.0)
    c.add_argument('--docs-root', default=os.environ.get('WALTER_ROOT', '/walter'))
    v = sub.add_parser('verify')
    v.add_argument('out')
    r = sub.add_parser('restore-check')
    r.add_argument('out')
    r.add_argument('--identity', required=True)
    r.add_argument('--image', required=True)
    r.add_argument('--workdir', default='/var/tmp')
    a = ap.parse_args(argv)
    if a.cmd == 'verify':
        return verify(Path(a.out))
    if a.cmd == 'restore-check':
        return restore_check(a)
    Archive(a).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
