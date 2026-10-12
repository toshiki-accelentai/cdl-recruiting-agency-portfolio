-- Dashboard logins. Two roles: recruiter (the demo login on the resume) and admin (owner only).
-- session_version is bumped whenever a password changes; every cookie carries the version it was
-- issued under, so a bump logs everyone out at once.
CREATE TABLE users (
    id               bigserial PRIMARY KEY,
    username         text        NOT NULL UNIQUE,
    password_hash    text        NOT NULL,
    role             text        NOT NULL CHECK (role IN ('recruiter', 'admin')),
    session_version  integer     NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- Same rule as migration 006: Supabase exposes public tables over REST, so RLS on + no policies.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
