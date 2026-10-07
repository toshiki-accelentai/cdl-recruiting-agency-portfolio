"""Schema-level guarantees that must hold on any host database (local Docker or Supabase)."""


def test_every_public_table_has_row_level_security_enabled(db):
    """Supabase exposes public tables over a REST API; RLS with no policies keeps them private."""
    rows = db.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity ORDER BY 1"
    ).fetchall()
    assert rows == [], f"tables without RLS: {[r[0] for r in rows]}"


def test_no_public_policies_exist(db):
    assert db.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'").fetchone()[0] == 0
