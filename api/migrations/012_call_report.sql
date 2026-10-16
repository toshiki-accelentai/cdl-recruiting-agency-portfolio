-- C1e: what VAPI's end-of-call report gives us. The recording itself stays at VAPI; we keep only a flag
-- (has_recording) and ask VAPI for a fresh, short-lived link each time someone plays it.
-- transcript is a list of {speaker, text, start} so a click on a line can jump the audio.
-- caller_number is the caller ID of a call, kept even when no applicant was created for it.
ALTER TABLE calls
    ADD COLUMN summary            text,
    ADD COLUMN transcript         jsonb,
    ADD COLUMN has_recording      boolean NOT NULL DEFAULT false,
    ADD COLUMN report_received_at timestamptz,
    ADD COLUMN caller_number      text;
