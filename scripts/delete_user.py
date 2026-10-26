"""Runs INSIDE the cdl-api container (piped to `python -` over ssh): remove ONE dashboard login.

    python - demo            # dry run: shows what would be removed, removes nothing
    python - demo --apply    # removes it, in one transaction (all or nothing)

Matches the username EXACTLY (no wildcards, no case folding). Refuses:
  - a name that is not a login,
  - an admin login (this tool only removes recruiter logins, so the owner cannot lock themselves out),
  - a login that has change-history rows (the history table is never deleted from; lock such a login with
    `python -m app.users_cli rotate` instead).
A removed login cannot sign in, and a session it already has stops working on its next request, because the
session cookie is checked against the users table every time. Never prints a password or a hash.
"""
import os
import sys

import psycopg


def run(conn, username, apply=False):
    with conn.transaction():
        row = conn.execute("SELECT id, username, role, created_at::date FROM users WHERE username = %s FOR UPDATE",
                           (username or "",)).fetchone()
        if row is None:
            raise ValueError(f"no login named {username!r} (exact match only)")
        user_id, name, role, created = row
        if role != "recruiter":
            raise ValueError(f"{name!r} has the role {role}; this tool only removes recruiter logins")
        history = conn.execute("SELECT count(*) FROM audit_log WHERE user_id = %s", (user_id,)).fetchone()[0]
        if history:
            raise ValueError(f"{name!r} has {history} change-history rows, which are never deleted; "
                             "lock the login with `python -m app.users_cli rotate` instead")
        if apply:
            deleted = conn.execute("DELETE FROM users WHERE id = %s", (user_id,)).rowcount
            if deleted != 1:
                raise RuntimeError(f"expected to remove 1 login, matched {deleted}; rolled back")
    remaining = [r[0] for r in conn.execute("SELECT username FROM users ORDER BY username")]
    return {"username": name, "role": role, "created": str(created), "history_rows": history,
            "applied": apply, "logins_that_stay": [u for u in remaining if u != name]}


def main(argv):
    args = [a for a in argv if a != "--apply"]
    apply = "--apply" in argv
    if len(args) != 1:
        print("usage: python - <username> [--apply]")
        return 2
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        try:
            result = run(conn, args[0], apply)
        except ValueError as exc:
            print(f"refused: {exc}")
            return 1
    print(("REMOVED " if apply else "DRY RUN, nothing removed. Would remove ") + str(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
