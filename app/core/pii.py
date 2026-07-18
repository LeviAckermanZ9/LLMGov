import re
from typing import Tuple

# Regex patterns for common PII types
EMAIL_REGEX = re.compile(
    r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
)

# Phone formats: e.g., +1 (123) 456-7890, 123-456-7890, 123.456.7890, etc.
PHONE_REGEX = re.compile(
    r'(?<!\w)(?:\+\d{1,3}[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)'
)

# Credit Cards: 13-16 digits with optional spaces or hyphens starting and ending with a digit
CREDIT_CARD_REGEX = re.compile(
    r'\b(?:\d[- ]*){12,15}\d\b'
)

# US SSN: XXX-XX-XXXX
SSN_REGEX = re.compile(
    r'\b\d{3}-\d{2}-\d{4}\b'
)

# IPv4 Address (octets restricted to 0-255)
IPV4_REGEX = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

def passes_luhn(card_number: str) -> bool:
    """
    Check if the card number passes the Luhn algorithm.
    """
    digits = [int(d) for d in card_number if d.isdigit()]
    if not digits:
        return False
    
    # Luhn algorithm implementation
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
        
    return total % 10 == 0

def redact_pii(text: str) -> Tuple[str, bool]:
    """
    Detects and redacts common PII identifiers (emails, phone numbers, credit cards, SSNs, IPs).
    Returns a tuple of (redacted_text, has_redacted).
    """
    if not text:
        return text, False

    redacted = text
    has_redacted = False

    # 1. Redact Emails
    redacted, count_email = EMAIL_REGEX.subn("[EMAIL]", redacted)
    if count_email > 0:
        has_redacted = True

    # 2. Redact SSNs
    redacted, count_ssn = SSN_REGEX.subn("[SSN]", redacted)
    if count_ssn > 0:
        has_redacted = True

    # 3. Redact Credit Cards with Luhn Check
    cc_redacted = False
    def redact_cc(match: re.Match) -> str:
        nonlocal cc_redacted
        matched_str = match.group(0)
        digits_only = "".join(c for c in matched_str if c.isdigit())
        if passes_luhn(digits_only):
            cc_redacted = True
            return "[CREDIT_CARD]"
        return matched_str

    redacted = CREDIT_CARD_REGEX.sub(redact_cc, redacted)
    if cc_redacted:
        has_redacted = True

    # 4. Redact Phone Numbers
    redacted, count_phone = PHONE_REGEX.subn("[PHONE]", redacted)
    if count_phone > 0:
        has_redacted = True

    # 5. Redact IPv4
    redacted, count_ipv4 = IPV4_REGEX.subn("[IP_ADDRESS]", redacted)
    if count_ipv4 > 0:
        has_redacted = True

    return redacted, has_redacted
