-- Per-attempt telemetry: usage is measured, absence remains unknown and cost provenance stays explicit.
BEGIN;
ALTER TABLE models.exec_log ADD COLUMN IF NOT EXISTS usage jsonb;
ALTER TABLE models.exec_log ADD COLUMN IF NOT EXISTS cost_status text NOT NULL DEFAULT 'unknown';
UPDATE models.exec_log SET cost_status = 'legacy' WHERE cost_usd IS NOT NULL AND cost_status = 'unknown';
ALTER TABLE models.exec_log ADD CONSTRAINT exec_log_cost_status_check
    CHECK (cost_status IN ('unknown', 'reported', 'estimated', 'legacy'));
COMMENT ON COLUMN models.exec_log.usage IS
    'Measured token counts for this execution attempt (in/out/cached); NULL means unavailable, never zero by inference.';
COMMENT ON COLUMN models.exec_log.cost_status IS
    'Cost provenance: unknown when unavailable; reported from provider usage; estimated by transport; legacy for historical values with no provenance.';
INSERT INTO models.schema_migrations(version) VALUES ('036_exec_telemetry') ON CONFLICT DO NOTHING;
COMMIT;
