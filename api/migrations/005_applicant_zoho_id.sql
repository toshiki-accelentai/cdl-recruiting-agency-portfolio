-- B1: remember which Zoho candidate an applicant became (set by the outbox worker).
ALTER TABLE applicants ADD COLUMN zoho_candidate_id text;
