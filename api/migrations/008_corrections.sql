-- C1c: recruiter corrections.
-- A correction belongs to an applicant, not to a call, so an outbox row may have no call.
-- (UNIQUE stays: Postgres allows many NULLs in a UNIQUE column, and intake rows keep one per call.)
ALTER TABLE outbox ALTER COLUMN call_id DROP NOT NULL;
ALTER TABLE outbox ADD COLUMN kind text NOT NULL DEFAULT 'intake'
    CHECK (kind IN ('intake', 'correction'));

-- Who changed what, and when. Never edited or deleted by the application.
CREATE TABLE audit_log (
    id            bigserial PRIMARY KEY,
    user_id       bigint      NOT NULL REFERENCES users (id),
    action        text        NOT NULL CHECK (action IN ('correct_applicant', 'attach_applicant')),
    call_id       bigint      REFERENCES calls (id),
    applicant_id  bigint      REFERENCES applicants (id),
    changes       jsonb       NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;  -- same rule as migrations 006 and 007
