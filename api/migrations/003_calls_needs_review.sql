-- A call may exist without an applicant (e.g. unusable phone): never lose the lead (A2).
ALTER TABLE calls ALTER COLUMN applicant_id DROP NOT NULL;
ALTER TABLE calls ADD COLUMN needs_review boolean NOT NULL DEFAULT false;
ALTER TABLE calls ADD COLUMN review_reason text;
