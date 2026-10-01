-- Walter Memory P1.5 — privacy classes (A6, D5). 2026-10-01.
begin;
create schema if not exists privacy;
comment on schema privacy is 'Walter Memory privacy: policies deciding local_only / redacted_cloud / cloud_allowed (most restrictive wins).';

create table if not exists privacy.policies (
    policy_id  bigserial primary key,
    name       text not null unique,
    match      jsonb not null,             -- keys (all must match): source, source_account, event_type, thread_id,
                                           -- identity_id, kardex_contact_id, mime_prefix, category, object_kind
    class      text not null check (class in ('local_only','redacted_cloud','cloud_allowed')),
    reason     text not null,
    enabled    boolean not null default true,
    created_by text not null default 'claude',
    created_at timestamptz not null default now()
);

-- Detected sensitive spans are never stored here: only which rule fired, for audit and purge candidates.
create table if not exists privacy.detections (
    detection_id bigserial primary key,
    at          timestamptz not null default now(),
    target_type text not null check (target_type in ('event','object','derived')),
    target_ref  text not null,             -- source:source_id or object sha256
    category    text not null,             -- secret | health | intimate | finance | identity_doc | …
    rule        text not null,
    action      text not null,             -- classified_local_only | flagged_for_purge
    reviewed_at timestamptz
);
create index if not exists detections_unreviewed on privacy.detections (category) where reviewed_at is null;

-- Default policy proposal (D5) — to be validated/edited by Monsieur. Categories come from privacy.py detectors.
insert into privacy.policies (name, match, class, reason) values
  ('secrets',            '{"category": "secret"}',        'local_only',     'Credentials, keys, OTP, card numbers: never leave the VM; flagged for break-glass purge'),
  ('identity-documents', '{"category": "identity_doc"}',  'local_only',     'Passport/ID/social security numbers'),
  ('health',             '{"category": "health"}',        'local_only',     'Health data stays local'),
  ('intimate',           '{"category": "intimate"}',      'local_only',     'Intimate/sexual content stays local; media go to the encrypted vault zone'),
  ('finance',            '{"category": "finance"}',       'redacted_cloud', 'Bank/finance details pseudonymised before any cloud call'),
  ('location-samples',   '{"event_type": "location.sample"}', 'local_only', 'Raw GPS never leaves the VM; only derived stays can be shared'),
  ('third-party-messaging', '{"source": "beeper"}',      'redacted_cloud', 'Other people''s messages: pseudonymise names/numbers before cloud models'),
  ('email',              '{"source": "gmail"}',           'redacted_cloud', 'E-mails: pseudonymise before cloud models')
on conflict (name) do nothing;
commit;
