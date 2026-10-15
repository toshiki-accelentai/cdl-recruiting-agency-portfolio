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


def classify_temperature(readiness: str) -> str:
    text = (readiness or "").strip().lower()
    if re.search(r"3\s*days?|immediately|right away", text):
        return "HOT"
    if re.search(r"7\s*days?|one\s*week", text):
        return "MEDIUM"
    if re.search(r"14\s*days?|two\s*weeks?", text):
        return "WARM"
    return "COLD"


def split_name(value: str) -> tuple[str, str]:
    """(first, last). A single word is the last name; empty is last name 'Unknown' (as in n8n)."""
    parts = (value or "").split()
    if not parts:
        return "", "Unknown"
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


_NUM = r"(\d+(?:\.\d+)?)"


def _clean(n: float) -> float:
    n = round(n, 2)
    return int(n) if n == int(n) else n


def parse_experience_years(value: str) -> float:
    """Port of cdl_helpers.js parseExperienceYears, except 'X years Y months' = X + Y/12
    (the JS version reads only the months: '3 years 8 months' -> 0.67)."""
    text = (value or "").strip().lower().replace("–", "-").replace("—", "-")
    if not text or re.search(r"no experience|just got|new cdl", text):
        return 0
    if re.search(r"under\s*6\s*months?", text):
        return 0.25
    both = re.search(_NUM + r"\s*\+?\s*years?\s*(?:and\s*)?" + _NUM + r"\s*months?", text)
    if both:
        return _clean(float(both.group(1)) + float(both.group(2)) / 12)
    month_range = re.search(_NUM + r"\s*-\s*" + _NUM + r"\s*months?", text)
    if month_range:
        return _clean((float(month_range.group(1)) + float(month_range.group(2))) / 24)
    months = re.search(_NUM + r"\s*months?", text)
    if months:
        return _clean(float(months.group(1)) / 12)
    year_range = re.search(_NUM + r"\s*-\s*" + _NUM + r"\s*years?", text)
    if year_range:
        return _clean((float(year_range.group(1)) + float(year_range.group(2))) / 2)
    years = re.search(_NUM + r"\s*\+?\s*years?", text)
    return _clean(float(years.group(1))) if years else 0
