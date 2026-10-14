-- A correction outbox row points at the audit row that says what changed, so the worker can
-- write the Zoho note from it. Intake rows have no audit row.
ALTER TABLE outbox ADD COLUMN audit_id bigint REFERENCES audit_log (id);
ALTER TABLE outbox ADD CONSTRAINT outbox_kind_matches_audit
    CHECK ((kind = 'correction') = (audit_id IS NOT NULL));
