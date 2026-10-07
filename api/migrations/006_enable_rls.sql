-- Supabase exposes every table in the public schema over its REST API (PostgREST).
-- RLS on + zero policies = anon/authenticated clients can read and write nothing.
-- Our API and worker connect with the database password (owner role), which bypasses RLS.
ALTER TABLE applicants        ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls             ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox            ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
