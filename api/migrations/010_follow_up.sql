-- C1d: follow-up tracking lives on the applicant (one status per person, however many times they call).
-- follow_up_updated_at stays NULL until a recruiter first sets something; the dashboard compares it
-- with the latest call time to show "new call since last follow-up".
ALTER TABLE applicants
    ADD COLUMN follow_up_status text NOT NULL DEFAULT 'to_call'
        CHECK (follow_up_status IN ('to_call', 'called', 'no_answer', 'done')),
    ADD COLUMN follow_up_note text NOT NULL DEFAULT '',
    ADD COLUMN follow_up_updated_at timestamptz;

-- audit_log may now also record follow-up changes
ALTER TABLE audit_log DROP CONSTRAINT audit_log_action_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_action_check
    CHECK (action IN ('correct_applicant', 'attach_applicant', 'update_follow_up'));
