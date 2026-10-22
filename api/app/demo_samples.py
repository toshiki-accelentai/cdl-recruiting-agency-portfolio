"""The two real sample calls shown on the demo server (live calls 10 and 11, placed 2026-10-22 by the owner).

Everything said in them is fictional (Carlos Rivera, a Fresno ZIP, the callback number 559-555-0127). The words and
timestamps are copied exactly from the stored transcripts so the text matches the audio. The audio files live outside
git (see recordings.DEMO_RECORDING_FILES).
"""

INTAKE_SUMMARY = 'Carlos Rivera called Frontline CDL Staffing inquiring about a driving job. He provided his name, location (Fresno, CA, 93706), over six years of tractor-trailer experience, and availability to start within seven days. A senior recruiter will call him tomorrow at 2 PM at 559-555-0127 to discuss job options, pay, home time, and benefits.'

INTAKE_LINES = [('agent', 'Hey. Thanks for calling Frontline CDL Staffing. Are you calling about a driving job today?', 1.4),
 ('driver', 'Yeah. Hi. I saw you guys were looking for drivers.', 7.3),
 ('agent',
  'Awesome. I can help with that. Just need a few quick details so a senior recruiter can call you back with job '
  "options that fit you. First, what's your full name?",
  13.4),
 ('driver', 'Uh, my name is Carlos Rivera.', 23.0),
 ('agent', "Thanks, Carlos. City and state are you in? What's your ZIP code?", 26.5),
 ('driver', 'Fresno, California. 9 3 7 0 6.', 32.1),
 ('agent',
  'Got it. Fresno, California, 9 3 7 0 6. Did I get that ZIP right? How much tractor trailer experience do you have?',
  37.1),
 ('driver', 'A little over 6 years. Mostly drive', 46.5),
 ('agent',
  'Thanks. 9 3 7 0 6. Is that ZIP correct? And on experience, I heard a little over 6 years of tractor trailer. Did '
  'I get that right?',
  53.2),
 ('driver', "Yes. That's right.", 64.3),
 ('agent',
  'Great. How soon are you ready to start a new driving job? Within the next 3 days? 7 days, 14 days, or later.',
  67.5),
 ('driver', 'Before I go on, what does it pay?', 81.2),
 ('agent',
  "That's a great question. I don't have pay details on hand. But the recruiter will cover pay, home time, and "
  'benefits on the callback. Can I grab just a couple more details so they can reach you? How soon are you ready to '
  'start? Within the next 3 days? 7 days, 14 days, or later.',
  86.3),
 ('driver', 'About a week, so, uh, 7 days.', 104.2),
 ('agent',
  "Perfect. What's the best phone number for a senior recruiter to call you on? I'll read it back to confirm.",
  109.5),
 ('driver', '5 5 9 5 5 5 0 1 2 7.', 116.5),
 ('agent',
  "Thanks. Let me read that back to make sure I've got it right. 5 5 9 5 5 5 0 1 2 7. Is that the best number to "
  'reach you?',
  124.0),
 ('driver', "Yes. That's it.", 133.7),
 ('agent',
  'Great. And what would be a good time for a senior recruiter to call you? Anytime Monday through Friday, between 9 '
  'AM and 5 PM.',
  136.4),
 ('driver', 'Tomorrow afternoon. Around 2.', 145.4),
 ('agent', 'Got it. Would 2 or 3 work better for you?', 150.4),
 ('driver', '2 is good.', 154.4),
 ('agent', 'Let me check that for you. Please hold on a moment.', 157.6),
 ('agent',
  "Let me save that for you. Perfect. You're all set. A senior recruiter from frontline CDL Staffing will call you "
  'tomorrow at 2 to go over driving positions that match your experience. Including home time, pay, and benefits. If '
  "you missed the call, just call us back and we'll get you rescheduled. Is there anything else I can help you with "
  'today?',
  161.7),
 ('driver', "No. That's all.", 180.5)]

HANGUP_SUMMARY = 'The user called Frontline CDL Staffing inquiring about a driving job they saw advertised. The AI confirmed they could help and requested a few details to have a senior recruiter call the user back.'

HANGUP_LINES = [('agent', 'Hey. Thanks for calling Frontline CDL Staffing. You calling about a driving job today?', 1.7),
 ('driver', 'Yes. Hi. I saw you guys were looking for drivers.', 7.3),
 ('agent',
  'Awesome. I can help with that. Just need a few quick details so a senior recruiter can call you back',
  19.7)]
