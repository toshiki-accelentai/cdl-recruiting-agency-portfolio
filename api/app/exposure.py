"""What each role may see. Applied at the edge of every dashboard read, so no endpoint can forget it.

An admin sees everything. Anyone else (a recruiter, the public demo user) gets the same JSON with two kinds of
detail removed, wherever they appear in the answer:
  last_error          the worker's error text; it can carry Zoho's own wording or internal detail
  zoho_candidate_id   the raw record id in Zoho
Everyone still sees that a sync failed, how many tries it took, and whether the person has a Zoho record at all.
"""
ADMIN_ONLY_KEYS = frozenset({"last_error", "zoho_candidate_id"})


def for_user(user: dict, data):
    """`data` as this user may see it (the same object for an admin)."""
    if user.get("role") == "admin":
        return data
    return _strip(data)


def _strip(data):
    if isinstance(data, dict):
        return {key: _strip(value) for key, value in data.items() if key not in ADMIN_ONLY_KEYS}
    if isinstance(data, list):
        return [_strip(item) for item in data]
    return data
