-- One applicant per phone number: repeat callers attach to the same row (A2).
ALTER TABLE applicants ADD CONSTRAINT applicants_phone_e164_key UNIQUE (phone_e164);
