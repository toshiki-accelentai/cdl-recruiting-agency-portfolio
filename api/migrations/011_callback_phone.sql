-- C1f: phone_e164 is now the caller ID when there is one (the applicant's identity).
-- callback_phone is the number the driver said out loud, kept only when it differs from phone_e164.
ALTER TABLE applicants ADD COLUMN callback_phone text NOT NULL DEFAULT '';
