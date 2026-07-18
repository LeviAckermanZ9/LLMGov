import pytest
from app.core.pii import redact_pii, passes_luhn

def test_passes_luhn():
    # Valid 13-digit card number (derived: 4000000000006)
    assert passes_luhn("4000000000006") is True
    # Valid 16-digit card number (standard test Visa: 4111111111111111)
    assert passes_luhn("4111111111111111") is True
    assert passes_luhn("4111-1111-1111-1111") is True
    
    # Invalid card numbers
    assert passes_luhn("4111111111111112") is False
    assert passes_luhn("1234567890123456") is False

def test_redact_pii_no_pii():
    text = "Hello world, this is a normal sentence with no sensitive info."
    redacted, has_redacted = redact_pii(text)
    assert redacted == text
    assert has_redacted is False

def test_redact_pii_email():
    text = "Contact me at user.name+label@example.co.uk or support@test-domain.org."
    redacted, has_redacted = redact_pii(text)
    assert redacted == "Contact me at [EMAIL] or [EMAIL]."
    assert has_redacted is True

def test_redact_pii_phone():
    # Standard format
    assert redact_pii("Call 123-456-7890")[0] == "Call [PHONE]"
    # With country code
    assert redact_pii("My number is +1 (123) 456-7890")[0] == "My number is [PHONE]"
    # Dots format
    assert redact_pii("Reach at 123.456.7890")[0] == "Reach at [PHONE]"
    # Spaces format
    assert redact_pii("Dial 123 456 7890")[0] == "Dial [PHONE]"

def test_redact_pii_credit_card():
    # True positives (Luhn-valid cards)
    assert redact_pii("My card: 4111111111111111")[0] == "My card: [CREDIT_CARD]"
    assert redact_pii("Visa: 4111-1111-1111-1111")[0] == "Visa: [CREDIT_CARD]"
    assert redact_pii("Visa space: 4111 1111 1111 1111")[0] == "Visa space: [CREDIT_CARD]"
    assert redact_pii("13-digit: 4000000000006")[0] == "13-digit: [CREDIT_CARD]"

def test_redact_pii_ssn():
    text = "Sensitive data: SSN 123-45-6789."
    redacted, has_redacted = redact_pii(text)
    assert redacted == "Sensitive data: SSN [SSN]."
    assert has_redacted is True

def test_redact_pii_ipv4():
    text = "The server is hosted at 192.168.1.254."
    redacted, has_redacted = redact_pii(text)
    assert redacted == "The server is hosted at [IP_ADDRESS]."
    assert has_redacted is True

def test_redact_pii_false_positives():
    # 1. Dates (should not match phone or SSN)
    text_date = "The document was created on 2026-07-18."
    redacted, has_redacted = redact_pii(text_date)
    assert redacted == text_date
    assert has_redacted is False

    # 2. Short numeric sequences / Zip codes (should not match CC or phone)
    text_zip = "The zip code is 90210 and quantity is 12345."
    redacted, has_redacted = redact_pii(text_zip)
    assert redacted == text_zip
    assert has_redacted is False

    # 3. Three-part software versions (should not match IP)
    text_version = "Using python version 3.11.9 here."
    redacted, has_redacted = redact_pii(text_version)
    assert redacted == text_version
    assert has_redacted is False

    # 4. Large currency amounts (should not match CC or phone)
    text_currency = "Total amount is $1,000,000.00."
    redacted, has_redacted = redact_pii(text_currency)
    assert redacted == text_currency
    assert has_redacted is False

    # 5. Luhn-invalid 13-16 digit order/tracking IDs (should not match CC)
    text_order_16 = "Your order ID is 1234567890123456."
    redacted, has_redacted = redact_pii(text_order_16)
    assert redacted == text_order_16
    assert has_redacted is False

    text_order_16_dash = "Your tracking code is 1234-5678-9012-3456."
    redacted, has_redacted = redact_pii(text_order_16_dash)
    assert redacted == text_order_16_dash
    assert has_redacted is False

    text_order_13 = "Your package ID is 1234567890123."
    redacted, has_redacted = redact_pii(text_order_13)
    assert redacted == text_order_13
    assert has_redacted is False
