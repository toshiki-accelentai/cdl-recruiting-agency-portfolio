CREATE TABLE applicants (
    id           bigserial PRIMARY KEY,
    name         text        NOT NULL,
    phone_e164   text        NOT NULL,
    city         text        NOT NULL DEFAULT '',
    state        text        NOT NULL DEFAULT '',
    zip_code     text        NOT NULL DEFAULT '',
    experience   text        NOT NULL DEFAULT '',
    readiness    text        NOT NULL DEFAULT '',
    temperature  text        NOT NULL CHECK (temperature IN ('HOT', 'MEDIUM', 'WARM', 'COLD')),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE calls (
    id                      bigserial PRIMARY KEY,
    vapi_call_id            text        NOT NULL UNIQUE,
    applicant_id            bigint      NOT NULL REFERENCES applicants (id),
    preferred_callback_at   timestamptz,
    raw_payload             jsonb       NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now()
);
