-- B1: one row per call that must be synced to the CRM. Written in the same transaction as the
-- call, so a saved call can never exist without its "to do" row. The worker reads this table.
CREATE TABLE outbox (
    id               bigserial PRIMARY KEY,
    call_id          bigint      NOT NULL UNIQUE REFERENCES calls (id),
    applicant_id     bigint      NOT NULL REFERENCES applicants (id),
    status           text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    attempts         integer     NOT NULL DEFAULT 0,
    next_attempt_at  timestamptz NOT NULL DEFAULT now(),
    last_error       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    sent_at          timestamptz
);
-- The worker's query: "pending rows whose time has come".
CREATE INDEX outbox_due_idx ON outbox (next_attempt_at) WHERE status = 'pending';
