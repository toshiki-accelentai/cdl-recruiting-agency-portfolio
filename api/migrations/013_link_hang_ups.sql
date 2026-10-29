-- Calls that ended before the agent saved details ("no_intake") used to stay unlinked even when the caller ID
-- belonged to a known applicant (for example a cancel request). Link those to the applicant, matched on the main
-- phone only, the same rule the end-of-call report uses from now on. Anything else stays unlinked.
UPDATE calls c
SET applicant_id = a.id
FROM applicants a
WHERE c.applicant_id IS NULL
  AND c.review_reason = 'no_intake'
  AND c.caller_number IS NOT NULL
  AND a.phone_e164 = c.caller_number;
