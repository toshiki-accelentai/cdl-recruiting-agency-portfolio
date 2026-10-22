"""The extra fictional drivers for the public demo, as a plain table (data only; demo_seed.py turns each row into calls).

Every name is made up. Phone numbers use 555-0100 to 555-0199, which US numbering keeps for fiction.
A row is: name, phone, city, state, zip, experience, equipment, readiness, temperature, hours since the call,
hours until the requested callback (negative = overdue, None = no time asked), follow-up status, recruiter note,
how the Zoho save went, hours since an earlier call (None = called once).
"""

STATE_NAMES = {
    "TN": "Tennessee", "TX": "Texas", "OH": "Ohio", "AL": "Alabama", "IN": "Indiana", "NE": "Nebraska",
    "NV": "Nevada", "NC": "North Carolina", "MN": "Minnesota", "CA": "California", "MI": "Michigan",
    "NM": "New Mexico", "WI": "Wisconsin", "MD": "Maryland", "WA": "Washington", "GA": "Georgia",
    "IA": "Iowa", "KS": "Kansas", "PA": "Pennsylvania", "AR": "Arkansas", "UT": "Utah", "MO": "Missouri",
    "KY": "Kentucky", "OK": "Oklahoma", "AZ": "Arizona", "CO": "Colorado",
}

CALLBACK_WORDS = ("Tomorrow morning", "Any weekday after three", "Friday at noon", "Next Monday",
                  "This afternoon", "Mornings work best", "Tuesday around ten")

SENT, WAITING, FAILED = "sent", "waiting", "failed"

ROSTER = [
    # hot: ready within three days
    ("Terrance Washington", "+19015550112", "Memphis", "TN", "38118", "9 years", "tanker", "tomorrow", "HOT", 3, 5, "to_call", "", SENT, None),
    ("Maria Gonzales", "+17135550138", "Houston", "TX", "77029", "4 years", "reefer", "in 2 days", "HOT", 8, 20, "to_call", "", WAITING, None),
    ("Brandon Whitaker", "+16145550121", "Columbus", "OH", "43207", "12 years", "OTR", "today", "HOT", 14, -5, "to_call", "", SENT, None),
    ("Latoya Freeman", "+12055550173", "Birmingham", "AL", "35217", "5 years", "flatbed", "in 3 days", "HOT", 28, -26, "to_call", "", SENT, None),
    ("Curtis Hayes", "+13175550149", "Indianapolis", "IN", "46241", "7 years", "dry van", "tomorrow", "HOT", 52, None, "called", "Spoke Tuesday, sending the route list.", SENT, None),
    ("Hector Villanueva", "+19155550166", "El Paso", "TX", "79905", "3 years", "dump", "in 3 days", "HOT", 90, None, "done", "Placed with a local aggregate hauler.", SENT, None),
    # medium: ready within a week
    ("Samantha Reilly", "+14025550184", "Omaha", "NE", "68107", "2 years", "local", "in 5 days", "MEDIUM", 5, 30, "to_call", "", SENT, None),
    ("Dmitri Petrov", "+17025550155", "Las Vegas", "NV", "89115", "10 years", "OTR", "next week", "MEDIUM", 11, 48, "to_call", "", SENT, 120),
    ("Aaliyah Jenkins", "+17045550192", "Charlotte", "NC", "28208", "1 year", "dry van", "in 7 days", "MEDIUM", 20, 26, "to_call", "", FAILED, None),
    ("Wyatt Larson", "+16125550108", "Minneapolis", "MN", "55411", "6 years", "reefer", "next week", "MEDIUM", 36, None, "no_answer", "Voicemail left, try after lunch.", SENT, None),
    ("Anh Nguyen", "+19165550177", "Sacramento", "CA", "95815", "8 years", "tanker", "in 7 days", "MEDIUM", 60, None, "called", "Wants regional only, home weekends.", SENT, None),
    ("Rashad Coleman", "+13135550135", "Detroit", "MI", "48210", "3 years", "flatbed", "in 5 days", "MEDIUM", 75, 12, "to_call", "", SENT, None),
    ("Gloria Mendez", "+15055550161", "Albuquerque", "NM", "87105", "5 years", "dry van", "next week", "MEDIUM", 110, None, "no_answer", "Second try tomorrow.", SENT, 150),
    ("Travis Kowalski", "+14145550118", "Milwaukee", "WI", "53204", "4 years", "dump", "in 7 days", "MEDIUM", 140, None, "done", "Hired by a local fleet.", SENT, None),
    ("Imani Carter", "+14105550146", "Baltimore", "MD", "21224", "2 years", "local", "in 5 days", "MEDIUM", 160, None, "called", "Asked to hear about night shifts.", SENT, None),
    ("Jesse Whitehorse", "+15095550183", "Spokane", "WA", "99217", "9 years", "OTR", "next week", "MEDIUM", 200, None, "to_call", "", SENT, None),
    # warm: ready within two weeks
    ("Pedro Alvarado", "+19565550129", "Laredo", "TX", "78041", "6 years", "reefer", "in 10 days", "WARM", 9, 72, "to_call", "", SENT, None),
    ("Katie O'Donnell", "+15135550151", "Cincinnati", "OH", "45214", "1 year", "local", "in 2 weeks", "WARM", 24, None, "to_call", "", SENT, None),
    ("Darnell Griffin", "+19125550134", "Savannah", "GA", "31408", "11 years", "tanker", "in 10 days", "WARM", 46, None, "called", "Call again after his current run ends.", SENT, None),
    ("Sunita Patel", "+15155550165", "Des Moines", "IA", "50313", "3 years", "dry van", "in 2 weeks", "WARM", 85, None, "no_answer", "No answer, voicemail left.", SENT, None),
    ("Randy Pruitt", "+13165550172", "Wichita", "KS", "67213", "14 years", "flatbed", "in 10 days", "WARM", 120, None, "done", "Took a dedicated route job.", SENT, None),
    ("Francisco Medina", "+12095550113", "Stockton", "CA", "95206", "7 years", "OTR", "in 2 weeks", "WARM", 150, None, "to_call", "", SENT, 210),
    ("Deborah Lindqvist", "+14125550156", "Pittsburgh", "PA", "15233", "5 years", "reefer", "in 10 days", "WARM", 190, None, "called", "Interested in weekly home time.", SENT, None),
    ("Isaiah Thornton", "+15015550181", "Little Rock", "AR", "72204", "2 years", "local", "in 2 weeks", "WARM", 250, None, "no_answer", "", SENT, None),
    # cold: ready later
    ("Nate Bergstrom", "+18015550167", "Salt Lake City", "UT", "84104", "15 years", "OTR", "next month", "COLD", 18, None, "to_call", "", SENT, None),
    ("Yolanda Ruiz", "+18165550140", "Kansas City", "MO", "64120", "3 years", "dry van", "after the holidays", "COLD", 55, None, "called", "Check back in November.", SENT, None),
    ("Calvin Hughes", "+15025550125", "Louisville", "KY", "40214", "6 years", "tanker", "in 5 weeks", "COLD", 100, None, "done", "Not looking until spring.", SENT, None),
    ("Omar Haddad", "+13145550190", "St. Louis", "MO", "63118", "4 years", "reefer", "next month", "COLD", 170, None, "no_answer", "", SENT, 240),
    ("Bethany Sutter", "+18655550114", "Knoxville", "TN", "37917", "2 years", "local", "next month", "COLD", 220, None, "to_call", "", SENT, None),
    ("Gary Tillman", "+14055550148", "Oklahoma City", "OK", "73108", "20 years", "OTR", "in 6 weeks", "COLD", 300, None, "called", "Retiring from his carrier in December.", SENT, None),
]

# Calls that never became an applicant: kept and flagged for a person to look at.
# (hours since the call, who called, why it was flagged, what the agent saw)
UNSAVED_CALLS = [
    (9, "+14805550171", "missing_name", "Caller asked about driving jobs but hung up before giving a name.",
     [("agent", "Thanks for calling Frontline CDL Staffing. Are you calling about a driving job today?"),
      ("driver", "Yeah, I want to know about driving jobs."),
      ("agent", "Awesome, I can help with that. First, what's your full name?"),
      ("driver", "Actually, never mind. I'll call back later.")]),
    (33, "+13035550185", "invalid_phone", "Caller gave a callback number with too few digits, so no applicant was created.",
     [("agent", "Thanks for calling Frontline CDL Staffing. Are you calling about a driving job today?"),
      ("driver", "Yes, I'm a CDL driver looking for work."),
      ("agent", "What's the best phone number for a recruiter to call you on?"),
      ("driver", "Three oh three, five five five, one eight."),
      ("agent", "That sounds like it's missing a few digits. Could you say the whole number again?"),
      ("driver", "Sorry, my battery's dying. I'll try again later.")]),
]
