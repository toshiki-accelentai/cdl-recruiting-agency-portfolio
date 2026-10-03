"""Python port of the rules in workflow-src/cdl_helpers.js (phone + temperature)."""
import re


def normalize_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", (value or "").strip())
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) != 11 or not digits.startswith("1"):
        return None
    return "+" + digits


def classify_temperature(readiness: str) -> str:
    text = (readiness or "").strip().lower()
    if re.search(r"3\s*days?|immediately|right away", text):
        return "HOT"
    if re.search(r"7\s*days?|one\s*week", text):
        return "MEDIUM"
    if re.search(r"14\s*days?|two\s*weeks?", text):
        return "WARM"
    return "COLD"
