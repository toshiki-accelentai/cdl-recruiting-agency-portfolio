"""Python port of the rules in workflow-src/cdl_helpers.js (phone, temperature, name, experience)."""
import re


def normalize_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", (value or "").strip())
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) != 11 or not digits.startswith("1"):
        return None
    return "+" + digits


def pick_phones(caller_id: str | None, spoken: str | None) -> tuple[str | None, str]:
    """Return (identity phone, callback phone).

    The caller ID (from the phone network) is the identity: a mistranscribed digit must never make
    a second applicant. Without a usable caller ID (web call, blocked number) the spoken number is
    the identity. The callback phone is the spoken number only when it differs from the identity.
    """
    caller = normalize_phone(caller_id or "")
    said = normalize_phone(spoken or "")
    identity = caller or said
    callback = said if said and said != identity else ""
    return identity, callback


# The VAPI tool sends the spaced spelling; VAPI's call analysis sends the underscore one.
TEMPERATURE_BY_READINESS = {
    "within 3 days": "HOT", "within_3_days": "HOT",
    "within 7 days": "MEDIUM", "within_7_days": "MEDIUM",
    "within 14 days": "WARM", "within_14_days": "WARM",
    "later": "COLD",
}


def classify_temperature(readiness: str | None) -> str | None:
    """HOT/MEDIUM/WARM/COLD for one of the fixed answers; None for anything else (never a silent COLD)."""
    return TEMPERATURE_BY_READINESS.get((readiness or "").strip().lower())


NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
SURNAME_PARTICLES = {"de", "del", "della", "la", "le", "da", "di", "du", "van", "von", "der", "den", "st", "st."}


def split_name(value: str) -> tuple[str, str]:
    """(first, last). A single word is the last name; empty is last name 'Unknown' (as in n8n).
    The last name starts at its first particle ('De La') and runs to the end, suffix ('Jr.') included."""
    parts = (value or "").split()
    if not parts:
        return "", "Unknown"
    end = len(parts)
    while end > 1 and parts[end - 1].lower() in NAME_SUFFIXES:
        end -= 1
    start = end - 1
    while start > 1 and parts[start - 1].lower() in SURNAME_PARTICLES:
        start -= 1
    return " ".join(parts[:start]), " ".join(parts[start:])


_NUM = r"(\d+(?:\.\d+)?)"
_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
_WORD_BEFORE_UNIT = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b(?=[\s-]*(?:years?|yrs?|months?)\b)")
_YEARS = r"(?:years?|yrs?)\b"


def _clean(n: float) -> float:
    n = round(n, 2)
    return int(n) if n == int(n) else n


def _range_or_single(text: str, unit: str) -> float | None:
    found = re.search(_NUM + r"\s*-\s*" + _NUM + r"\s*" + unit, text)
    if found:
        return (float(found.group(1)) + float(found.group(2))) / 2
    found = re.search(_NUM + r"\s*\+?\s*" + unit, text)
    return float(found.group(1)) if found else None


def parse_experience_years(value: str | None) -> float | None:
    """Years of experience, or None when the text cannot be read (None is not the same as 0).
    Port of cdl_helpers.js parseExperienceYears: years and months add up ('2 years 6 months' = 2.5)."""
    text = (value or "").strip().lower().replace("–", "-").replace("—", "-")
    text = _WORD_BEFORE_UNIT.sub(lambda m: str(_NUMBER_WORDS[m.group(1)]), text)
    text = re.sub(r"(\d)\s*to\s*(\d)", r"\1-\2", text)
    if re.search(r"no experience|just got|new cdl", text):
        return 0
    if re.search(r"(?:under|less than)\s*6\s*months?", text):
        return 0.25
    years = _range_or_single(text, _YEARS)
    months = _range_or_single(text, r"months?\b")
    if years is None and months is None:
        return None
    return _clean((years or 0) + (months or 0) / 12)


MAX_TRANSCRIPT_LINES = 500
MAX_LINE_LENGTH = 2000
SPEAKERS = {"bot": "agent", "assistant": "agent", "user": "driver"}
TEXT_LINE = re.compile(r"^\s*(AI|User)\s*:\s*(.+?)\s*$")


def build_transcript(messages, text) -> list[dict]:
    """Spoken lines only, as [{speaker, text, start}]. Falls back to VAPI's plain-text transcript."""
    lines = []
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        speaker = SPEAKERS.get(message.get("role"))
        spoken = message.get("message")
        spoken = spoken.strip() if isinstance(spoken, str) else ""
        if not speaker or not spoken:
            continue
        start = message.get("secondsFromStart")
        start = round(float(start), 1) if isinstance(start, (int, float)) and not isinstance(start, bool) else None
        lines.append({"speaker": speaker, "text": spoken[:MAX_LINE_LENGTH], "start": start})
    if not lines and isinstance(text, str):
        for raw in text.splitlines():
            found = TEXT_LINE.match(raw)
            if found:
                lines.append({"speaker": "agent" if found.group(1) == "AI" else "driver",
                              "text": found.group(2)[:MAX_LINE_LENGTH], "start": None})
    return lines[:MAX_TRANSCRIPT_LINES]
